
from urllib.parse import urlparse


def truncate_text(text: str, max_chars: int = 2000) -> str:
    """
    Truncate text to at most max_chars characters, adding '…' if truncated.
    """
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def extract_domain(url: str) -> str:
    """
    Extract a short 'domain' label from a URL for display.
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc or ""
    except Exception:  # noqa: BLE001
        return ""
