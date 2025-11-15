# -*- coding: utf-8 -*-
import logging
import random
import time
from functools import wraps
from typing import Callable

LOG = logging.getLogger(__name__)

TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
    Exception,  # We'll filter by message; keep broad but with logging
)

def with_backoff(max_tries: int = 6, base: float = 0.5, max_sleep: float = 15.0):
    """
    Exponential backoff decorator.
    Sleeps: base * 2^(n-1) + jitter, capped by max_sleep.
    """
    def deco(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            tries = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except TRANSIENT_EXCEPTIONS as e:
                    tries += 1
                    if tries >= max_tries:
                        LOG.error("Retry exhausted for %s: %s", fn.__name__, e)
                        raise
                    sleep_s = min(max_sleep, (base * (2 ** (tries - 1))) + random.random())
                    LOG.warning("Transient error in %s (try %d/%d): %s; sleeping %.2fs",
                                fn.__name__, tries, max_tries, e, sleep_s)
                    time.sleep(sleep_s)
        return wrapper
    return deco
