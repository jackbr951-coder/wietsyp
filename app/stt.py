"""Speech-to-text using an optional hosted or local Whisper implementation."""
import io
import os
import tempfile
import logging

import httpx

PROMPT = "لهجة تونسية في الفلاحة والمنتوجات: زيت زيتون، تمر دڨلة، عسل، هريسة، تين، رمان، هندي، إكليل، لتر، كيلو، قنطار، صندوق، قفة، قارورة، سجنان، القيروان."
LOGGER = logging.getLogger(__name__)
_local = None


def _has_local() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) or _has_local()


def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    if not audio or len(audio) < 512:
        raise RuntimeError("ما سمعتكش، عاودي سجّلي رسالة صوتية أو اكتبيها.")
    if os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI
        f = io.BytesIO(audio)
        f.name = filename
        try:
            return OpenAI(timeout=30, max_retries=1).audio.transcriptions.create(
                model="whisper-1", file=f, language="ar", prompt=PROMPT
            ).text
        except Exception as exc:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            body = getattr(response, "text", "") if response else ""
            LOGGER.error(
                "Transcription upstream failure status=%s body=%r error_type=%s",
                status if status is not None else "unknown",
                str(body or exc)[:1000],
                type(exc).__name__,
            )
            raise RuntimeError(f"تعذّر تحويل الصوت: {str(exc)[:300]}") from exc
    if _has_local():
        global _local
        from faster_whisper import WhisperModel
        if _local is None:  # first call downloads the model once, then it is cached
            _local = WhisperModel(os.getenv("DAFTER_WHISPER_MODEL", "small"), compute_type="int8")
        suffix = os.path.splitext(filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as t:
            t.write(audio)
        try:
            segs, _ = _local.transcribe(t.name, language="ar", initial_prompt=PROMPT)
            transcript = " ".join(s.text.strip() for s in segs).strip()
            if not transcript:
                raise RuntimeError("ما سمعتكش، عاودي سجّلي رسالة صوتية أو اكتبيها.")
            return transcript
        finally:
            os.unlink(t.name)
    raise RuntimeError(
        "التعرّف المحلي على الصوت موش مركّب. ثبّتي faster-whisper، أو استعملي التعرّف الصوتي في المتصفح، أو اكتبي رسالتك."
    )
