"""Twilio-style phone-call webhooks using the shared Darija dialogue."""
import html
import logging

import httpx
from fastapi import APIRouter, Form
from fastapi.responses import Response

from . import darija, db, extract, stt, tts

router = APIRouter(prefix="/twilio")
LOGGER = logging.getLogger(__name__)
VOICE = 'voice="Polly.Zeina" language="arb"'
_calls: dict[str, str] = {}  # CallSid -> piece id (use Redis/DB in production)


def twiml(body: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")


def say(t: str) -> str:
    return f"<Say {VOICE}>{html.escape(t)}</Say>"


def record() -> str:
    return '<Record action="/twilio/recording" maxLength="40" playBeep="true" trim="trim-silence"/>'


@router.post("/voice")
def voice(CallSid: str = Form("")):
    _calls[CallSid] = db.create()
    return twiml(say(darija.choose("greeting")) + record())


@router.post("/recording")
def recording(CallSid: str = Form(""), RecordingUrl: str = Form("")):
    pid = _calls.get(CallSid) or db.create()
    _calls[CallSid] = pid
    try:
        audio = httpx.get(RecordingUrl + ".wav", timeout=20).content
        text = stt.transcribe(audio, "rec.wav")
    except Exception as exc:
        LOGGER.warning("Phone-call transcription failed (%s)", type(exc).__name__)
        return twiml(say(darija.choose("transcription_error")) + record())
    d = db.get(pid) or {}
    d.update(extract.extract(text, d))
    d["id"] = pid
    extract.finalize_hours(d)
    d["verification"] = "self_reported"
    db.save(pid, d)
    reply = tts.speakable(extract.reply_for(text, d))
    if extract.is_goodbye(text) or not extract.next_question(d):
        return twiml(say(reply) + "<Hangup/>")
    return twiml(say(reply) + record())
