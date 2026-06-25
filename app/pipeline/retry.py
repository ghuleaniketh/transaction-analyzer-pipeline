import time


def retry_with_backoff(func, *args, max_retries: int = 3, base_delay: float = 1.0, **kwargs):
    """
    Calls func(*args, **kwargs), retrying up to max_retries times on any exception,
    with exponential backoff between attempts (1s, 2s, 4s by default).
    Re-raises the last exception if all attempts fail — the caller decides
    what "all retries failed" means for their context (e.g. marking a batch llm_failed).
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)

    raise last_exception