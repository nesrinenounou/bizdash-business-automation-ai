import logging, os, time
import httpx

log = logging.getLogger("notify")


def send_new_order(payload: dict, retries: int = 3) -> bool:
    """POST the order to the n8n webhook, with retry/backoff. Returns success."""
    url = os.getenv("N8N_WEBHOOK_URL")
    if not url:
        return False
    for attempt in range(retries):
        try:
            httpx.post(url, json=payload, timeout=10).raise_for_status()
            return True
        except Exception as exc:
            log.warning("n8n webhook attempt %s failed: %s", attempt + 1, exc)
            time.sleep(2 ** attempt)
    return False
