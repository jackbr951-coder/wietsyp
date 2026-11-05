"""Free online Tunisian Arabic speech with a disk cache and optional offline voice."""
import asyncio
import hashlib
import importlib.metadata
import json
import logging
import os
import re
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "tts_cache"
TIMEOUT_SECONDS = 20  # Step 7: increased from 10 to 20
RETRIES = 3  # Step 7: increased from 2 to 3
BACKOFF_BASE = 0.5  # Step 7: exponential backoff base


@dataclass(frozen=True)
class Synthesis:
    audio: bytes
    voice: str
    media_type: str
    cache_hit: bool = False


class TTSError(RuntimeError):
    def __init__(self, message_ar: str, message_en: str, hint: str, voice: str = ""):
        super().__init__(message_en)
        self.message_ar = message_ar
        self.message_en = message_en
        self.hint = hint
        self.voice = voice


def available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        try:
            import pyttsx3  # noqa: F401
            return True
        except ImportError:
            return False


def edge_tts_version() -> str | None:
    try:
        return importlib.metadata.version("edge-tts")
    except importlib.metadata.PackageNotFoundError:
        return None


def voices() -> list[str]:
    candidates = [
        os.getenv("DAFTER_TTS_VOICE", "").strip(),
        "ar-TN-ReemNeural",
        "ar-TN-HediNeural",
        "ar-SA-ZariyahNeural",
    ]
    return list(dict.fromkeys(voice for voice in candidates if voice))


def _under_100(value: int) -> str:
    ones = {
        1: "واحد", 2: "زوز", 3: "ثلاثة", 4: "أربعة", 5: "خمسة",
        6: "ستة", 7: "سبعة", 8: "ثمانية", 9: "تسعة",
    }
    tens = {
        10: "عشرة", 20: "عشرين", 30: "ثلاثين", 40: "أربعين",
        50: "خمسين", 60: "ستين", 70: "سبعين", 80: "ثمانين", 90: "تسعين",
    }
    if value < 10:
        return {0: "صفر", **ones}[value]
    if value < 20:
        return {
            10: "عشرة", 11: "حداش", 12: "طناش", 13: "تلطاش", 14: "أربعطاش",
            15: "خمسطاش", 16: "سطاش", 17: "سبعطاش", 18: "ثمنطاش", 19: "تسعطاش",
        }[value]
    ten, one = divmod(value, 10)
    if one == 0:
        return tens[ten * 10]
    return f"{ones[one]} و {tens[ten * 10]}"


def number_words(value: int) -> str:
    if not isinstance(value, int) or not 0 <= value <= 9999:
        raise ValueError("Tunisian number words support integers from 0 to 9999")
    if value < 100:
        return _under_100(value)

    parts: list[str] = []
    thousands, remainder = divmod(value, 1000)
    if thousands:
        parts.append({1: "ألف", 2: "ألفين"}.get(thousands, f"{_under_100(thousands)} آلاف"))
    hundreds, remainder = divmod(remainder, 100)
    if hundreds:
        parts.append({
            1: "مية", 2: "ميتين", 3: "ثلاثمية", 4: "أربعمية", 5: "خمسمية",
            6: "ستمية", 7: "سبعمية", 8: "ثمانمية", 9: "تسعمية",
        }[hundreds])
    if remainder:
        parts.append(_under_100(remainder))
    return " و ".join(parts)


def _spoken_number(raw: str) -> str:
    try:
        value = int(raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    except ValueError:
        return raw
    if 0 <= value <= 9999:
        return number_words(value)
    return raw


def _sentences(text: str, limit: int = 200) -> list[str]:
    sentences: list[str] = []
    for sentence in re.split(r"(?<=[.!؟?؛])\s*", text.strip()):
        sentence = sentence.strip()
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit + 1)
            if cut <= 0:
                cut = limit
            sentences.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            sentences.append(sentence)
    return sentences


def speakable(text: str) -> str:
    """Make a short, Arabic-first spoken string and keep sentences under 200 characters."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", str(text))
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"`{1,3}|[*_~>#]", " ", text)
    text = re.sub(r"\b(?:TND|DT)\b", " دينار ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bUSD\b|\$", " دولار ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bEUR\b|€", " أورو ", text, flags=re.IGNORECASE)
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    text = re.sub(r"(?<![\w])(\d{1,5})(?![\w])", lambda match: _spoken_number(match.group(1)), text)
    text = re.sub(r"[A-Za-z]+", " ", text)
    text = re.sub(
        r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F]",
        " ",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip(" ،;:.-")
    return " ".join(_sentences(text))


def _cache_path(text: str, voice: str, rate: str) -> Path:
    key = hashlib.sha256(
        json.dumps([text, voice, rate], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CACHE_DIR / f"{key}.mp3"


def _read_cache(path: Path) -> bytes | None:
    try:
        audio = path.read_bytes()
        return audio if audio else None
    except FileNotFoundError:
        return None


def _write_cache(path: Path, audio: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as temp:
            temp.write(audio)
            temporary_path = Path(temp.name)
        os.replace(temporary_path, path)
    except OSError as exc:
        LOGGER.warning("Could not write TTS cache (%s)", type(exc).__name__)
        try:
            temporary_path.unlink(missing_ok=True)
        except (NameError, OSError):
            pass


async def _synthesize_edge_voice(text: str, voice: str, rate: str) -> bytes:
    import edge_tts

    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    if not audio:
        raise RuntimeError("Edge TTS returned no audio")
    return bytes(audio)


def _is_http_403(error: Exception) -> bool:
    return getattr(error, "status", None) == 403 or getattr(error, "status_code", None) == 403 or "403" in str(error)


def _upstream_status_and_body(error: Exception) -> tuple[int | None, str]:
    response = getattr(error, "response", None)
    status = (
        getattr(response, "status_code", None)
        or getattr(error, "status_code", None)
        or getattr(error, "status", None)
    )
    body = getattr(response, "text", None) or getattr(error, "body", None)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if not isinstance(body, str):
        body = ""
    return status if isinstance(status, int) else None, body[:1000]


def _error_hint(error: Exception | None) -> str:
    if error is None:
        return "Install edge-tts: pip install -U edge-tts"
    if _is_http_403(error):
        return "HTTP 403 means the edge-tts version is outdated; upgrade edge-tts: pip install -U edge-tts"
    message = str(error).lower()
    if any(term in message for term in ("timeout", "timed out", "connect", "network", "dns", "speech.platform.bing.com")):
        return "No internet or the firewall blocks speech.platform.bing.com"
    if "edge_tts" in message or "no module named" in message:
        return "Install edge-tts: pip install -U edge-tts"
    return "Check internet access to speech.platform.bing.com and update edge-tts: pip install -U edge-tts"


def _make_error(error: Exception | None, voice: str = "") -> TTSError:
    from .darija import tts_error_ar

    hint = _error_hint(error)
    message = str(error) if error else "No online or installed Arabic offline speech voice is available"
    return TTSError(tts_error_ar(), f"Speech synthesis failed: {message}", hint, voice)


def _arabic_pyttsx3_voice(engine):
    for voice in engine.getProperty("voices"):
        description = " ".join(
            str(value) for value in (voice.id, voice.name, getattr(voice, "languages", []))
        ).lower()
        if "arab" in description or re.search(r"\bar\b", description):
            return voice
    return None


def _offline_synthesize(text: str) -> tuple[bytes, str]:
    import pyttsx3

    engine = pyttsx3.init()
    voice = _arabic_pyttsx3_voice(engine)
    if voice is None:
        raise RuntimeError("No Arabic voice is installed for pyttsx3")
    engine.setProperty("voice", voice.id)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
        path = Path(temp.name)
    try:
        engine.save_to_file(text, str(path))
        engine.runAndWait()
        audio = path.read_bytes()
        if not audio:
            raise RuntimeError("pyttsx3 returned no audio")
        return audio, str(voice.id)
    finally:
        path.unlink(missing_ok=True)


async def synthesize_result(text: str, force: bool = False, rate: float = 1.0) -> Synthesis:
    spoken = speakable(text)[:4000]
    if not spoken:
        raise _make_error(ValueError("No speakable Arabic text was provided"))
    base_rate = os.getenv("DAFTER_TTS_RATE", "-10%")
    try:
        base_percent = int(base_rate.strip().rstrip("%"))
    except ValueError:
        LOGGER.warning("Invalid DAFTER_TTS_RATE=%r; using -10%%", base_rate)
        base_percent = -10
    requested_percent = round((max(0.5, min(2.0, rate)) - 1) * 100)
    voice_rate = f"{max(-50, min(50, base_percent + requested_percent)):+d}%"
    last_error: Exception | None = None

    try:
        import edge_tts  # noqa: F401
    except ImportError as exc:
        last_error = exc
        # Step 7: log full exception
        LOGGER.warning("edge-tts not installed: %s", traceback.format_exc())
    else:
        for voice in voices():
            path = _cache_path(spoken, voice, voice_rate)
            if not force:
                cached = _read_cache(path)
                if cached:
                    return Synthesis(cached, voice, "audio/mpeg", True)
            for attempt in range(RETRIES + 1):
                try:
                    audio = await asyncio.wait_for(
                        _synthesize_edge_voice(spoken, voice, voice_rate),
                        timeout=TIMEOUT_SECONDS,
                    )
                    _write_cache(path, audio)
                    return Synthesis(audio, voice, "audio/mpeg")
                except Exception as exc:
                    last_error = exc
                    status, body = _upstream_status_and_body(exc)
                    # Step 7: log FULL exception with traceback
                    LOGGER.warning(
                        "Edge TTS failure attempt=%d/%d voice=%s status=%s "
                        "error_type=%s body=%r\n%s",
                        attempt + 1,
                        RETRIES + 1,
                        voice,
                        status if status is not None else "unknown",
                        type(exc).__name__,
                        body or str(exc)[:1000],
                        traceback.format_exc(),
                    )
                    if _is_http_403(exc) or attempt == RETRIES:
                        break
                    # Step 7: exponential backoff
                    await asyncio.sleep(BACKOFF_BASE * (2 ** attempt))
            if _is_http_403(last_error):
                break

    try:
        audio, offline_voice = await asyncio.to_thread(_offline_synthesize, spoken)
        return Synthesis(audio, offline_voice, "audio/wav")
    except (ImportError, RuntimeError, OSError) as exc:
        if last_error is None:
            last_error = exc
        else:
            LOGGER.warning(
                "Offline Arabic TTS fallback unavailable (%s)\n%s",
                type(exc).__name__,
                traceback.format_exc(),
            )
    raise _make_error(last_error, voices()[0] if voices() else "")


async def synthesize(text: str) -> bytes:
    return (await synthesize_result(text)).audio


async def health() -> dict:
    from time import perf_counter

    started = perf_counter()
    try:
        result = await synthesize_result("مرحبا بيك، يعيشك.", force=True)
        return {
            "ok": True,
            "voice": result.voice,
            "bytes": len(result.audio),
            "ms": round((perf_counter() - started) * 1000),
            "edge_tts_version": edge_tts_version(),
            "error": None,
            "hint": None,
        }
    except Exception as exc:
        from .darija import tts_error_ar

        return {
            "ok": False,
            "voice": getattr(exc, "voice", "") or (voices()[0] if voices() else ""),
            "bytes": 0,
            "ms": round((perf_counter() - started) * 1000),
            "edge_tts_version": edge_tts_version(),
            "error": {
                "ar": getattr(exc, "message_ar", None) or tts_error_ar(),
                "en": getattr(exc, "message_en", str(exc)),
            },
            "hint": getattr(exc, "hint", _error_hint(exc)),
        }
