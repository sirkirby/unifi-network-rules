"""Queue implementation for processing API operations sequentially."""

import asyncio
import logging
from typing import Callable, Any, Dict, Optional, List
import time
import weakref

LOGGER = logging.getLogger(__name__)

class QueuedOperation:
    """Represents a queued operation with retry and metadata."""
    
    def __init__(self, operation_func: Callable, args: tuple, kwargs: dict, future: asyncio.Future, 
                 is_priority: bool = False, max_retries: int = 3):
        self.operation_func = operation_func
        self.args = args
        self.kwargs = kwargs
        self.future = future
        self.is_priority = is_priority
        self.max_retries = max_retries
        self.retry_count = 0
        self.created_time = time.time()
        self.last_attempt_time = 0
        self.error_history: List[str] = []

    def can_retry(self) -> bool:
        """Check if this operation can be retried."""
        return self.retry_count < self.max_retries
        
    def should_retry_now(self, backoff_seconds: float = 2.0) -> bool:
        """Check if enough time has passed for a retry."""
        if not self.can_retry():
            return False
        if self.retry_count == 0:
            return True
        time_since_last_attempt = time.time() - self.last_attempt_time
        backoff_time = backoff_seconds * (2 ** (self.retry_count - 1))  # Exponential backoff
        return time_since_last_attempt >= backoff_time
        
    def record_attempt(self, error: Optional[str] = None):
        """Record an attempt and optional error."""
        self.retry_count += 1
        self.last_attempt_time = time.time()
        if error:
            self.error_history.append(f"Attempt {self.retry_count}: {error}")

    @property
    def age_seconds(self) -> float:
        """Get the age of this operation in seconds."""
        return time.time() - self.created_time

class ApiOperationQueue:
    """Queue for processing API operations sequentially with retry and persistence."""
    
    def __init__(self, delay_between_requests: float = 0.5, max_queue_size: int = 1000, 
                 operation_timeout: float = 300.0):
        """Initialize the API operation queue.
        
        Args:
            delay_between_requests: Delay in seconds between processing requests
            max_queue_size: Maximum number of operations to queue (prevents memory issues)
            operation_timeout: Maximum age for operations before they're considered stale
        """
        # Use separate queues for different priorities
        self.priority_queue = asyncio.Queue(maxsize=max_queue_size // 2)
        self.regular_queue = asyncio.Queue(maxsize=max_queue_size // 2)
        
        # Retry queue for failed operations
        self.retry_queue: List[QueuedOperation] = []
        
        self.delay = delay_between_requests
        self.processing_task = None
        self.retry_task = None
        self.running = False
        self.max_queue_size = max_queue_size
        self.operation_timeout = operation_timeout
        
        # Track queue stats for diagnostics
        self.operations_processed = 0
        self.operations_failed = 0
        self.operations_retried = 0
        self.operations_dropped = 0
        self.last_operation_time = 0
        
        # Prevent memory leaks
        self._weak_futures: weakref.WeakSet = weakref.WeakSet()
    
    async def start(self):
        """Start the queue processor."""
        if self.running:
            return
            
        self.running = True
        self.processing_task = asyncio.create_task(self._process_queue())
        self.retry_task = asyncio.create_task(self._process_retry_queue())
        LOGGER.debug("API operation queue processor started")
    
    async def stop(self):
        """Stop the queue processor."""
        if not self.running:
            return
            
        self.running = False
        
        # Cancel processing tasks
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
                
        if self.retry_task:
            self.retry_task.cancel()
            try:
                await self.retry_task
            except asyncio.CancelledError:
                pass
                
        # Complete any remaining futures with cancellation
        self._complete_pending_futures_on_shutdown()
        
        LOGGER.debug("API operation queue processor stopped")
    
    def _complete_pending_futures_on_shutdown(self):
        """Complete pending futures when shutting down to prevent hanging operations."""
        # Complete futures in regular queue
        try:
            while not self.regular_queue.empty():
                try:
                    operation = self.regular_queue.get_nowait()
                    if isinstance(operation, tuple) and len(operation) >= 4:
                        future = operation[3]
                        if not future.done():
                            future.set_exception(RuntimeError("Queue shutdown"))
                    self.regular_queue.task_done()
                except asyncio.QueueEmpty:
                    break
        except Exception as err:
            LOGGER.debug("Error completing regular queue futures on shutdown: %s", err)
            
        # Complete futures in priority queue
        try:
            while not self.priority_queue.empty():
                try:
                    operation = self.priority_queue.get_nowait()
                    if isinstance(operation, tuple) and len(operation) >= 4:
                        future = operation[3]
                        if not future.done():
                            future.set_exception(RuntimeError("Queue shutdown"))
                    self.priority_queue.task_done()
                except asyncio.QueueEmpty:
                    break
        except Exception as err:
            LOGGER.debug("Error completing priority queue futures on shutdown: %s", err)
            
        # Complete futures in retry queue
        for queued_op in self.retry_queue:
            if not queued_op.future.done():
                queued_op.future.set_exception(RuntimeError("Queue shutdown"))
        self.retry_queue.clear()
    
    async def add_operation(self, operation_func: Callable, *args, is_priority: bool = False, 
                          max_retries: int = 3, **kwargs) -> asyncio.Future:
        """Add an API operation to the queue with retry support.
        
        Args:
            operation_func: The operation function to call
            *args: Arguments to pass to the operation function
            is_priority: Whether this is a high-priority operation (like toggle)
            max_retries: Maximum number of retry attempts for this operation
            **kwargs: Keyword arguments to pass to the operation function
            
        Returns:
            Future that will contain the result of the operation
        """
        future = asyncio.get_event_loop().create_future()
        self._weak_futures.add(future)
        
        # Check if queues are full and drop oldest operations if needed
        selected_queue = self.priority_queue if is_priority else self.regular_queue
        if selected_queue.full():
            LOGGER.warning("Queue is full, dropping oldest operation to make room")
            try:
                # Try to remove the oldest operation (FIFO)
                old_operation = selected_queue.get_nowait()
                if isinstance(old_operation, tuple) and len(old_operation) >= 4:
                    old_future = old_operation[3]
                    if not old_future.done():
                        old_future.set_exception(RuntimeError("Queue overflow - operation dropped"))
                self.operations_dropped += 1
                selected_queue.task_done()
            except asyncio.QueueEmpty:
                pass  # Queue became empty between full check and get
        
        # Create queued operation wrapper
        queued_op = QueuedOperation(operation_func, args, kwargs, future, is_priority, max_retries)
        
        # Add operation to the appropriate queue
        try:
            await selected_queue.put((operation_func, args, kwargs, future, queued_op))
            
            # Log with priority and retry information
            LOGGER.debug("API operation added to %s queue: %s (max_retries=%d)", 
                       "priority" if is_priority else "regular", 
                       operation_func.__name__, max_retries)
        except asyncio.QueueFull:
            # This shouldn't happen due to our pre-check, but handle it gracefully
            LOGGER.error("Queue still full after cleanup, rejecting operation: %s", operation_func.__name__)
            future.set_exception(RuntimeError("Queue full - operation rejected"))
            self.operations_dropped += 1
        
        return future
    
    async def _process_queue(self):
        """Process items in the queue with a delay between each."""
        while self.running:
            try:
                # Check priority queue first, then regular queue
                queued_item = None
                queue_type = None
                
                try:
                    # First check if there's anything in the priority queue (non-blocking)
                    if not self.priority_queue.empty():
                        queued_item = await asyncio.wait_for(
                            self.priority_queue.get(), timeout=0.1
                        )
                        # Use a shorter delay for priority operations
                        current_delay = max(0.2, self.delay / 2)
                        queue_type = "priority"
                    else:
                        # Then check regular queue with timeout
                        queued_item = await asyncio.wait_for(
                            self.regular_queue.get(), timeout=1.0
                        )
                        current_delay = self.delay
                        queue_type = "regular"
                        
                except asyncio.TimeoutError:
                    # No items in queue, continue the loop
                    continue
                
                if not queued_item or len(queued_item) < 5:
                    continue
                
                operation_func, args, kwargs, future, queued_op = queued_item
                
                # Process the operation
                await self._execute_operation(queued_op, queue_type)
                
                # Mark task as done in the appropriate queue
                if queue_type == "priority":
                    self.priority_queue.task_done()
                else:
                    self.regular_queue.task_done()
                
                # Add delay before processing next item
                await asyncio.sleep(current_delay)
                
            except asyncio.CancelledError:
                break
            except Exception as err:
                LOGGER.error(f"Unexpected error in queue processor: {err}")
                await asyncio.sleep(1.0)  # Sleep to avoid tight loop on error 
                
    async def _process_retry_queue(self):
        """Process the retry queue for failed operations."""
        while self.running:
            try:
                # Process retry queue every 5 seconds
                await asyncio.sleep(5.0)
                
                if not self.retry_queue:
                    continue
                    
                # Find operations ready for retry
                ready_for_retry = []
                expired_operations = []
                
                for queued_op in self.retry_queue[:]:  # Create a copy to iterate safely
                    if queued_op.age_seconds > self.operation_timeout:
                        expired_operations.append(queued_op)
                    elif queued_op.should_retry_now():
                        ready_for_retry.append(queued_op)
                
                # Remove expired operations
                for expired_op in expired_operations:
                    self.retry_queue.remove(expired_op)
                    if not expired_op.future.done():
                        error_msg = f"Operation expired after {expired_op.age_seconds:.1f}s"
                        LOGGER.error("Dropping expired operation %s: %s", 
                                   expired_op.operation_func.__name__, error_msg)
                        expired_op.future.set_exception(RuntimeError(error_msg))
                    self.operations_dropped += 1
                
                # Retry ready operations
                for retry_op in ready_for_retry:
                    self.retry_queue.remove(retry_op)
                    await self._execute_operation(retry_op, "retry")
                    
            except asyncio.CancelledError:
                break
            except Exception as err:
                LOGGER.error(f"Unexpected error in retry processor: {err}")
                await asyncio.sleep(1.0)
    
    async def _execute_operation(self, queued_op: QueuedOperation, queue_type: str):
        """Execute a queued operation with error handling and retry logic."""
        if queued_op.future.done():
            # Future was already completed (possibly cancelled)
            return
            
        LOGGER.debug(f"Processing API operation from {queue_type} queue: {queued_op.operation_func.__name__} "
                    f"(attempt {queued_op.retry_count + 1}/{queued_op.max_retries + 1})")
        
        try:
            result = await queued_op.operation_func(*queued_op.args, **queued_op.kwargs)
            queued_op.future.set_result(result)
            self.operations_processed += 1
            self.last_operation_time = time.time()
            
            # Log successful retry if this was a retry
            if queued_op.retry_count > 0:
                LOGGER.info("Operation %s succeeded after %d retries", 
                           queued_op.operation_func.__name__, queued_op.retry_count)
                self.operations_retried += 1
                
        except Exception as err:
            error_msg = str(err)
            queued_op.record_attempt(error_msg)
            
            # Check if this is a retryable error
            is_retryable = self._is_retryable_error(err)
            
            if is_retryable and queued_op.can_retry():
                # Add to retry queue
                LOGGER.warning("Operation %s failed (attempt %d/%d), will retry: %s", 
                             queued_op.operation_func.__name__, 
                             queued_op.retry_count, 
                             queued_op.max_retries + 1, 
                             error_msg)
                self.retry_queue.append(queued_op)
            else:
                # Permanent failure or max retries exceeded
                if queued_op.retry_count >= queued_op.max_retries:
                    LOGGER.error("Operation %s failed permanently after %d attempts: %s", 
                               queued_op.operation_func.__name__, 
                               queued_op.retry_count + 1, 
                               error_msg)
                else:
                    LOGGER.error("Operation %s failed with non-retryable error: %s", 
                               queued_op.operation_func.__name__, error_msg)
                
                queued_op.future.set_exception(err)
                self.operations_failed += 1
                
    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        error_str = str(error).lower()
        
        # Don't retry authentication errors (these need manual intervention)
        if "401 unauthorized" in error_str or "403 forbidden" in error_str:
            return False
            
        # Don't retry client errors (400-499) except for rate limiting
        if "400 bad request" in error_str or "404 not found" in error_str:
            return False
            
        # Retry server errors (500-599), timeouts, and connection issues
        retryable_patterns = [
            "timeout", "connection", "network", "500 internal server error", 
            "502 bad gateway", "503 service unavailable", "504 gateway timeout",
            "429 too many requests"  # Rate limiting
        ]
        
        return any(pattern in error_str for pattern in retryable_patterns)
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics for diagnostics."""
        return {
            "operations_processed": self.operations_processed,
            "operations_failed": self.operations_failed,
            "operations_retried": self.operations_retried,
            "operations_dropped": self.operations_dropped,
            "priority_queue_size": self.priority_queue.qsize(),
            "regular_queue_size": self.regular_queue.qsize(),
            "retry_queue_size": len(self.retry_queue),
            "last_operation_time": self.last_operation_time,
            "running": self.running,
        } 