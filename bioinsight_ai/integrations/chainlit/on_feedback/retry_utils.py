"""
Retry utilities for feedback operations.

This module provides retry decorators and circuit breaker patterns for
resilient DynamoDB operations with exponential backoff.
"""

import asyncio
import time
from functools import wraps
from typing import Any, Callable, Optional, Type, Union, Tuple
from enum import Enum

from botocore.exceptions import ClientError, BotoCoreError
from log_helper.logger import get_logger

logger = get_logger()


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit breaker implementation for fault tolerance.
    
    Prevents cascading failures by failing fast when error threshold is exceeded.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to track for failures
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to apply circuit breaker to a function."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self._call(func, *args, **kwargs)
        return wrapper
    
    async def _call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker logic."""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        return (
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
    
    def _on_success(self):
        """Handle successful operation."""
        self.failure_count = 0
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
            logger.info("Circuit breaker reset to CLOSED")
    
    def _on_failure(self):
        """Handle failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_exceptions: Tuple[Type[Exception], ...] = (ClientError, BotoCoreError)
):
    """
    Decorator for retry logic with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        retry_exceptions: Exception types that should trigger retries
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retry_exceptions as e:
                    last_exception = e
                    
                    # Check if this is a retryable error
                    if not _is_retryable_error(e):
                        logger.warning(f"Non-retryable error in {func.__name__}: {e}")
                        raise
                    
                    if attempt == max_attempts - 1:
                        logger.error(f"Max retry attempts ({max_attempts}) exceeded for {func.__name__}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )
                    
                    # Add jitter to prevent thundering herd
                    if jitter:
                        import random
                        delay *= (0.5 + random.random() * 0.5)
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    
                    await asyncio.sleep(delay)
                except Exception as e:
                    # Non-retryable exception, fail immediately
                    logger.error(f"Non-retryable exception in {func.__name__}: {e}")
                    raise
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator


def _is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error is retryable.
    
    Args:
        error: Exception to check
        
    Returns:
        bool: True if error should be retried, False otherwise
    """
    if isinstance(error, ClientError):
        error_code = error.response.get('Error', {}).get('Code', '')
        
        # Retryable AWS errors
        retryable_codes = {
            'ThrottlingException',
            'ProvisionedThroughputExceededException',
            'RequestLimitExceeded',
            'InternalServerError',
            'ServiceUnavailable',
            'RequestTimeout',
            'RequestTimeoutException'
        }
        
        return error_code in retryable_codes
    
    if isinstance(error, BotoCoreError):
        # Network-related errors are generally retryable
        return True
    
    return False


def create_dynamodb_circuit_breaker() -> CircuitBreaker:
    """
    Create a circuit breaker specifically configured for DynamoDB operations.
    
    Returns:
        CircuitBreaker: Configured circuit breaker for DynamoDB
    """
    return CircuitBreaker(
        failure_threshold=5,
        recovery_timeout=60,
        expected_exception=(ClientError, BotoCoreError, CircuitBreakerOpenError)
    )


# Global circuit breaker instance for DynamoDB operations
dynamodb_circuit_breaker = create_dynamodb_circuit_breaker()