
import os
from typing import Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from a .env file if present.
load_dotenv()


def get_env(name: str) -> Optional[str]:
    return os.getenv(name)


def get_openai_client() -> OpenAI:
    api_key = get_env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Please set it in a .env file or environment variable."
        )
    return OpenAI(api_key=api_key)


def get_perplexity_api_key() -> str:
    api_key = get_env("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PERPLEXITY_API_KEY is missing. Please set it in a .env file or environment variable."
        )
    return api_key


def validate_config() -> Tuple[bool, str]:
    """
    Quick sanity check used by the UI.
    Returns (ok, error_message_if_any).
    """
    missing = []
    if not get_env("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not get_env("PERPLEXITY_API_KEY"):
        missing.append("PERPLEXITY_API_KEY")

    if missing:
        return False, f"Missing environment variables: {', '.join(missing)}"
    return True, ""
