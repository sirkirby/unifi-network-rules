"""Queue implementation for processing API operations sequentially."""

import asyncio
import logging
from typing import Callable, Any, Awaitable, Dict, Tuple, Optional

LOGGER = logging.getLogger(__name__)

class ApiOperationQueue:
    """Queue for processing API operations sequentially."""
    
    def __init__(self, delay_between_requests: float = 0.5):
        """Initialize the API operation queue.
        
        Args:
            delay_between_requests: Delay in seconds between processing requests
        """
        # Use a priority queue to enable some operations to be processed faster
        self.regular_queue = asyncio.Queue()
        self.priority_queue = asyncio.Queue()  # For toggle operations that need quick response
        self.delay = delay_between_requests
        self.processing_task = None
        self.running = False
        # Track queue stats for diagnostics
        self.operations_processed = 0
        self.last_operation_time = 0
    
    async def start(self):
        """Start the queue processor."""
        if self.running:
            return
            
        self.running = True
        self.processing_task = asyncio.create_task(self._process_queue())
        LOGGER.debug("API operation queue processor started")
    
    async def stop(self):
        """Stop the queue processor."""
        if not self.running:
            return
            
        self.running = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        LOGGER.debug("API operation queue processor stopped")
    
    async def add_operation(self, operation_func: Callable, *args, is_priority: bool = False, **kwargs) -> asyncio.Future:
        """Add an API operation to the queue.
        
        Args:
            operation_func: The operation function to call
            *args: Arguments to pass to the operation function
            is_priority: Whether this is a high-priority operation (like toggle)
            **kwargs: Keyword arguments to pass to the operation function
            
        Returns:
            Future that will contain the result of the operation
        """
        future = asyncio.get_event_loop().create_future()
        
        # Select the appropriate queue based on priority
        queue = self.priority_queue if is_priority else self.regular_queue
        
        # Add operation to the queue
        await queue.put((operation_func, args, kwargs, future))
        
        # Log with priority information
        LOGGER.debug("API operation added to %s queue: %s", 
                   "priority" if is_priority else "regular", 
                   operation_func.__name__)
        
        return future
    
    async def _process_queue(self):
        """Process items in the queue with a delay between each."""
        while self.running:
            try:
                # Check priority queue first, then regular queue
                # This ensures toggle operations are processed quickly
                operation_func = None
                args = None
                kwargs = None
                future = None
                
                try:
                    # First check if there's anything in the priority queue (non-blocking)
                    if not self.priority_queue.empty():
                        operation_func, args, kwargs, future = await asyncio.wait_for(
                            self.priority_queue.get(), timeout=0.1
                        )
                        # Use a shorter delay for priority operations
                        current_delay = max(0.2, self.delay / 2)
                        queue_type = "priority"
                    else:
                        # Then check regular queue with timeout
                        operation_func, args, kwargs, future = await asyncio.wait_for(
                            self.regular_queue.get(), timeout=1.0
                        )
                        current_delay = self.delay
                        queue_type = "regular"
                        
                except asyncio.TimeoutError:
                    # No items in queue, continue the loop
                    continue
                
                if not operation_func:
                    continue
                
                # Process the operation
                LOGGER.debug(f"Processing API operation from {queue_type} queue: {operation_func.__name__}")
                try:
                    result = await operation_func(*args, **kwargs)
                    future.set_result(result)
                    # Track stats
                    self.operations_processed += 1
                    import time
                    self.last_operation_time = time.time()
                except Exception as err:
                    LOGGER.error(f"Error in API operation {operation_func.__name__}: {err}")
                    future.set_exception(err)
                
                # Mark task as done in the appropriate queue
                if queue_type == "priority":
                    self.priority_queue.task_done()
                else:
                    self.regular_queue.task_done()
                
                # Add delay before processing next item - shorter for priority queue
                await asyncio.sleep(current_delay)
                
            except asyncio.CancelledError:
                break
            except Exception as err:
                LOGGER.error(f"Unexpected error in queue processor: {err}")
                await asyncio.sleep(1.0)  # Sleep to avoid tight loop on error 