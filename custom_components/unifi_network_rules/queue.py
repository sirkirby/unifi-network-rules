"""Queue implementation for processing API operations sequentially."""

import asyncio
import logging
from typing import Callable, Any, Awaitable, Dict, Tuple

LOGGER = logging.getLogger(__name__)

class ApiOperationQueue:
    """Queue for processing API operations sequentially."""
    
    def __init__(self, delay_between_requests: float = 0.5):
        """Initialize the API operation queue.
        
        Args:
            delay_between_requests: Delay in seconds between processing requests
        """
        self.queue = asyncio.Queue()
        self.delay = delay_between_requests
        self.processing_task = None
        self.running = False
    
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
    
    async def add_operation(self, operation_func: Callable, *args, **kwargs) -> asyncio.Future:
        """Add an API operation to the queue.
        
        Args:
            operation_func: The operation function to call
            *args, **kwargs: Arguments to pass to the operation function
            
        Returns:
            Future that will contain the result of the operation
        """
        future = asyncio.get_event_loop().create_future()
        await self.queue.put((operation_func, args, kwargs, future))
        LOGGER.debug(f"API operation added to queue: {operation_func.__name__}")
        return future
    
    async def _process_queue(self):
        """Process items in the queue with a delay between each."""
        while self.running:
            try:
                # Wait for an item or timeout to check if we're still running
                try:
                    operation_func, args, kwargs, future = await asyncio.wait_for(
                        self.queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process the operation
                LOGGER.debug(f"Processing API operation: {operation_func.__name__}")
                try:
                    result = await operation_func(*args, **kwargs)
                    future.set_result(result)
                except Exception as err:
                    LOGGER.error(f"Error in API operation {operation_func.__name__}: {err}")
                    future.set_exception(err)
                
                # Mark task as done
                self.queue.task_done()
                
                # Add delay before processing next item
                await asyncio.sleep(self.delay)
                
            except asyncio.CancelledError:
                break
            except Exception as err:
                LOGGER.error(f"Unexpected error in queue processor: {err}")
                await asyncio.sleep(1.0)  # Sleep to avoid tight loop on error 