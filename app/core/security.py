import time
from collections import defaultdict
from threading import Lock
from flask import request
from app.core.exceptions import RateLimitException
from app.core.config import settings

# Thread-safe in-memory sliding window rate limiter
_request_records = defaultdict(list)
_lock = Lock()


def check_rate_limit(key: str = None, limit: int = None, window_seconds: int = 60):
    """
    Sliding window rate limiter per client IP or key.
    """
    if not settings.RATE_LIMIT_PER_MINUTE or settings.RATE_LIMIT_PER_MINUTE <= 0:
        return
        
    client_ip = key or request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    max_requests = limit or settings.RATE_LIMIT_PER_MINUTE
    now = time.time()
    window_start = now - window_seconds
    
    with _lock:
        timestamps = _request_records[client_ip]
        # Purge timestamps outside sliding window
        valid_timestamps = [t for t in timestamps if t > window_start]
        
        if len(valid_timestamps) >= max_requests:
            raise RateLimitException(
                message=f"Rate limit exceeded: maximum {max_requests} requests per minute.",
                details={"client_ip": client_ip, "limit": max_requests, "retry_after_seconds": int(window_seconds - (now - valid_timestamps[0]))}
            )
            
        valid_timestamps.append(now)
        _request_records[client_ip] = valid_timestamps
