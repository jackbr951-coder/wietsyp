"""Unified LLM provider interface for Ollama and Anthropic."""
import logging
import os
import time

import httpx

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def ollama_host() -> str:
    return (
        os.getenv("OLLAMA_HOST")
        or os.getenv("OLLAMA_URL")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "").strip()


def ollama_timeout() -> float:
    raw = os.getenv("OLLAMA_TIMEOUT") or os.getenv("OLLAMA_TIMEOUT_SECONDS") or "180"
    try:
        return float(raw)
    except ValueError:
        return 180.0


def ollama_keep_alive() -> str:
    return os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip()


def active_provider() -> str:
    """Return 'anthropic', 'ollama', or 'none'."""
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit in ("anthropic", "ollama"):
        return explicit
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if ollama_model():
        return "ollama"
    return "none"


def anthropic_model() -> str:
    return os.getenv("DAFTER_LLM_MODEL", "claude-3-5-haiku-latest").strip()


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

def ollama_reachable() -> tuple[bool, str]:
    """Check whether the Ollama server responds. Returns (ok, error_msg)."""
    try:
        r = httpx.get(f"{ollama_host()}/api/tags", timeout=3.0)
        r.raise_for_status()
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def ollama_model_loaded() -> tuple[bool, dict]:
    """Check /api/ps to see if our model is loaded. Returns (loaded, info)."""
    try:
        r = httpx.get(f"{ollama_host()}/api/ps", timeout=3.0)
        r.raise_for_status()
        data = r.json()
        models = data.get("models", [])
        target = ollama_model()
        for m in models:
            name = m.get("name", "")
            if name == target or name.startswith(target.split(":")[0]):
                return True, m
        return False, {"models": [m.get("name") for m in models]}
    except Exception as exc:
        return False, {"error": f"{type(exc).__name__}: {exc}"}


def warmup_ollama() -> dict:
    """Send a tiny prompt to load the model into memory. Returns timing info."""
    model = ollama_model()
    if not model:
        return {"ok": False, "error": "OLLAMA_MODEL not set"}

    keep_alive = ollama_keep_alive()
    LOGGER.info("Warming up Ollama model %s (keep_alive=%s)...", model, keep_alive)
    start = time.perf_counter()

    try:
        r = httpx.post(
            f"{ollama_host()}/api/chat",
            timeout=ollama_timeout(),
            json={
                "model": model,
                "stream": False,
                "keep_alive": keep_alive,
                "messages": [{"role": "user", "content": "مرحبا"}],
            },
        )
        r.raise_for_status()
        elapsed = round(time.perf_counter() - start, 2)
        LOGGER.info("Ollama model %s loaded in %.2fs", model, elapsed)
        return {"ok": True, "model": model, "load_seconds": elapsed}
    except Exception as exc:
        elapsed = round(time.perf_counter() - start, 2)
        msg = f"{type(exc).__name__}: {exc}"
        LOGGER.error("Ollama warmup failed after %.2fs: %s", elapsed, msg)
        return {"ok": False, "model": model, "load_seconds": elapsed, "error": msg}


def ollama_chat(system: str, user_content: str, **kwargs) -> str:
    """Send a chat request to Ollama and return the response text."""
    model = ollama_model()
    if not model:
        raise RuntimeError("OLLAMA_MODEL not set")

    json_body = {
        "model": model,
        "stream": False,
        "keep_alive": ollama_keep_alive(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        **kwargs,
    }

    r = httpx.post(
        f"{ollama_host()}/api/chat",
        timeout=ollama_timeout(),
        json=json_body,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def ollama_test_latency(prompt: str = "مرحبا، قوليلي شنية حالك؟") -> dict:
    """Run a single timed call to Ollama. Returns timing info."""
    model = ollama_model()
    start = time.perf_counter()
    try:
        r = httpx.post(
            f"{ollama_host()}/api/chat",
            timeout=ollama_timeout(),
            json={
                "model": model,
                "stream": False,
                "keep_alive": ollama_keep_alive(),
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        elapsed = round(time.perf_counter() - start, 2)
        reply = r.json()["message"]["content"].strip()
        return {"ok": True, "seconds": elapsed, "reply_length": len(reply)}
    except Exception as exc:
        elapsed = round(time.perf_counter() - start, 2)
        return {"ok": False, "seconds": elapsed, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Anthropic helpers
# ---------------------------------------------------------------------------

def anthropic_chat(system: str, user_content: str, max_tokens: int = 160) -> str:
    """Send a chat request to Anthropic and return the response text."""
    import anthropic

    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=key, timeout=30, max_retries=1)
    response = client.messages.create(
        model=anthropic_model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    ).strip()


# ---------------------------------------------------------------------------
# Unified chat dispatch
# ---------------------------------------------------------------------------

def chat(system: str, user_content: str, max_tokens: int = 160, **kwargs) -> tuple[str, str]:
    """
    Dispatch to the active provider.
    Returns (reply_text, provider_used).
    Raises RuntimeError if no provider is available.
    """
    provider = active_provider()

    if provider == "anthropic":
        reply = anthropic_chat(system, user_content, max_tokens=max_tokens)
        return reply, "anthropic"

    if provider == "ollama":
        extra = {}
        if kwargs.get("json_format"):
            extra["format"] = "json"
        reply = ollama_chat(system, user_content, **extra)
        return reply, "ollama"

    raise RuntimeError(f"No LLM provider available (LLM_PROVIDER={provider})")
