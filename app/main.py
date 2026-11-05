import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

from . import certificate, darija, db, extract, llm, pricing, stt, tts, vision
from .buyer_page import render_buyer
from .twilio_ivr import router as twilio_router

LOGGER = logging.getLogger(__name__)
STATIC = os.path.join(os.path.dirname(__file__), "static")


# ---------------------------------------------------------------------------
# Lifespan: warm up Ollama at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Warm up the Ollama model in a background task at startup."""
    provider = llm.active_provider()
    if provider == "ollama" and llm.ollama_model():
        async def _warmup():
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, llm.warmup_ollama)
            if result["ok"]:
                LOGGER.info(
                    "✅ Ollama model %s warm — loaded in %.2fs",
                    result["model"],
                    result["load_seconds"],
                )
            else:
                LOGGER.error(
                    "❌ Ollama warmup failed after %.2fs: %s",
                    result.get("load_seconds", 0),
                    result.get("error", "unknown"),
                )

        asyncio.create_task(_warmup())
    else:
        LOGGER.info("LLM provider: %s (no Ollama warmup needed)", provider)
    yield


app = FastAPI(
    title="Dafter",
    description="A voice-first assistant for Tunisian women farmers.",
    lifespan=lifespan,
)
app.include_router(twilio_router)


class LogIn(BaseModel):
    transcript: str
    piece_id: str | None = None
    location: str | None = None


def refresh(d: dict) -> dict:
    extract.finalize_hours(d)
    v = pricing.verification(d)
    d["verification"], d["ratio"] = v["status"], v["ratio"]
    return d


def view(d: dict, transcript: str = "") -> dict:
    q = extract.next_question(d)
    missing = extract.missing(d)
    photo_prompt = missing == ["photo_verified"] and not d.get("photo_prompted")
    if photo_prompt:
        d["photo_prompted"] = True

    # reply_for now returns (reply_text, used_template)
    reply_text, used_template = extract.reply_for(transcript, d)
    reply = tts.speakable(reply_text)

    result = {
        "piece": d,
        "missing": missing,
        "question": q,
        "reply": reply,
        "reply_speech": reply,
        "reply_ar": reply,
        "price": pricing.price(d),
        "canIssue": not missing,
        "photoPrompt": photo_prompt,
    }

    # Step 6: Stop silent fallbacks — flag degraded mode
    if used_template:
        result["degraded"] = True
        result["reason"] = "LLM unavailable; used a local Darija template instead."
    else:
        result["degraded"] = False

    return result


@app.post("/api/log")
def log(body: LogIn):
    pid = body.piece_id or db.create()
    d = db.get(pid)
    if d is None:
        raise HTTPException(404, "unknown piece")
    if body.location and len(body.location.strip()) <= 120 and not d.get("village"):
        d["village"] = body.location.strip()
    awaiting = d.pop("awaiting_field", None)
    new = extract.extract(body.transcript, d)
    if awaiting:
        new = extract.apply_answer(awaiting, body.transcript, new, d)
    if "product" in new and d.get("product") and extract.normalize(new["product"]) != extract.normalize(d["product"]):
        for key in ("quantity", "unit", "price_tnd"):
            d.pop(key, None)
    for k, v in new.items():
        d[k] = v  # newest statement wins (she can correct herself)
    d["id"] = pid
    d.setdefault("transcripts", []).append(body.transcript)
    refresh(d)
    missing_fields = extract.missing(d)
    if missing_fields:
        d["awaiting_field"] = missing_fields[0]
    response = view(d, body.transcript)
    db.save(pid, d)
    return response


@app.get("/api/status")
def status():
    model = llm.ollama_model()
    provider = llm.active_provider()
    ollama_ok, _ = llm.ollama_reachable()
    ollama_available = False
    if ollama_ok and model:
        try:
            response = httpx.get(
                llm.ollama_host() + "/api/tags",
                timeout=1.5,
            )
            response.raise_for_status()
            ollama_available = any(
                item.get("name") == model
                for item in response.json().get("models", [])
            )
        except (httpx.HTTPError, ValueError):
            LOGGER.info("Ollama status probe unavailable")
    edge_available = tts.available()
    tts_mode = os.getenv("DAFTER_TTS_MODE", "browser").strip().lower()
    return {
        "stt": stt.available(),
        "browser_stt": True,
        "tts": tts_mode == "edge" and edge_available,
        "edge_tts_available": edge_available,
        "tts_mode": tts_mode,
        "browser_tts": True,
        "llm": provider if provider != "none" else None,
        "llm_provider": provider,
        "ollama_model": model,
        "ollama_available": ollama_available,
        "certificate_configured": len(os.getenv("DAFTER_SECRET", "").strip()) >= 32,
        "staticLayers": True,
        "mode": "ai" if provider != "none" else "offline",
    }


# ---------------------------------------------------------------------------
# Step 5: /api/health — comprehensive health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Full health check: Ollama, model loaded, LLM latency, Edge TTS."""
    report: dict = {"timestamp": time.time()}

    # --- Ollama reachable ---
    ollama_ok, ollama_err = llm.ollama_reachable()
    report["ollama_reachable"] = ollama_ok
    if ollama_err:
        report["ollama_error"] = ollama_err

    # --- Model loaded (from /api/ps) ---
    if ollama_ok:
        loaded, ps_info = llm.ollama_model_loaded()
        report["ollama_model_loaded"] = loaded
        report["ollama_model"] = llm.ollama_model()
        report["ollama_ps"] = ps_info
    else:
        report["ollama_model_loaded"] = False

    # --- LLM latency test ---
    provider = llm.active_provider()
    report["llm_provider"] = provider
    if provider == "ollama" and ollama_ok:
        loop = asyncio.get_event_loop()
        latency = await loop.run_in_executor(None, llm.ollama_test_latency)
        report["llm_latency"] = latency
    elif provider == "anthropic":
        start = time.perf_counter()
        try:
            reply = llm.anthropic_chat(
                "You are a test. Reply with one Arabic word.",
                "مرحبا",
                max_tokens=20,
            )
            elapsed = round(time.perf_counter() - start, 2)
            report["llm_latency"] = {"ok": True, "seconds": elapsed, "reply_length": len(reply)}
        except Exception as exc:
            elapsed = round(time.perf_counter() - start, 2)
            report["llm_latency"] = {"ok": False, "seconds": elapsed, "error": str(exc)}
    else:
        report["llm_latency"] = {"ok": False, "error": "no provider configured"}

    # --- Edge TTS test ---
    tts_result = await tts.health()
    report["edge_tts"] = tts_result

    return report


class TtsIn(BaseModel):
    text: str
    rate: float = 1.0


@app.post("/api/tts")
async def speak(body: TtsIn):
    try:
        result = await tts.synthesize_result(body.text[:4000], rate=body.rate)
        return Response(
            result.audio,
            media_type=result.media_type,
            headers={"X-Dafter-Voice": result.voice, "X-Dafter-Cache": str(result.cache_hit).lower()},
        )
    except tts.TTSError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error_ar": exc.message_ar,
                "error_en": exc.message_en,
                "hint": exc.hint,
                "voice": exc.voice,
                "fallback": "browser_speechSynthesis",
            },
        )
    except Exception as exc:
        LOGGER.exception("Unexpected TTS failure")
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error_ar": darija.tts_error_ar(),
                "error_en": f"Speech synthesis failed: {type(exc).__name__}",
                "hint": "Check edge-tts and network access to speech.platform.bing.com",
                "voice": "",
                "fallback": "browser_speechSynthesis",
            },
        )


@app.get("/api/tts/health")
async def tts_health():
    return await tts.health()


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    try:
        audio = await file.read()
        if not audio:
            raise HTTPException(422, "No audio received; record again.")
        return {"transcript": stt.transcribe(audio, file.filename or "audio.webm")}
    except RuntimeError as e:
        raise HTTPException(501, str(e))


@app.post("/api/pieces/{pid}/photo")
async def photo(pid: str, file: UploadFile = File(...)):
    d = db.get(pid)
    if not d:
        raise HTTPException(404, "unknown piece")
    image = await file.read()
    if not image:
        raise HTTPException(422, "Empty image upload")
    mime = file.content_type or "image/jpeg"
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "Use a JPEG, PNG, or WebP product photo.")
    db.save_photo(pid, image, mime)
    res = vision.analyse(image, mime, d.get("product", ""))
    d["complexity"], d["vision"] = res["complexity"], res
    d["photo"], d["photo_verified"] = True, res.get("verified") is True
    d.pop("awaiting_field", None)
    refresh(d)
    missing_fields = extract.missing(d)
    if missing_fields:
        d["awaiting_field"] = missing_fields[0]
    db.save(pid, d)
    response = view(d) | {"vision": res, "photo_verified": d["photo_verified"]}
    if res.get("matches") is False:
        response["reply"] = response["reply_speech"] = response["reply_ar"] = darija.choose("photo_mismatch")
        response["question"] = darija.choose("question_photo")
    elif not d["photo_verified"]:
        response["reply"] = response["reply_speech"] = response["reply_ar"] = darija.choose("photo_unverified")
        response["question"] = darija.choose("question_photo")
    elif not extract.next_question(d):
        response["reply"] = response["reply_speech"] = response["reply_ar"] = (
            "يعطيك الصحة، التصويرة تطابقت مع المنتوج. تنجمي توا تصدري الشهادة."
        )
    return response


@app.get("/api/pieces/{pid}/photo")
def piece_photo(pid: str):
    image = db.get_photo(pid)
    if not image:
        raise HTTPException(404, "photo not found")
    return Response(image[0], media_type=image[1])


@app.post("/api/pieces/{pid}/story")
async def story(pid: str, file: UploadFile = File(...)):
    if not db.get(pid):
        raise HTTPException(404, "unknown piece")
    db.save_story(pid, await file.read(), file.content_type or "audio/webm")
    d = db.get(pid)
    d["has_story"] = True
    db.save(pid, d)
    return {"ok": True}


@app.get("/api/pieces/{pid}/story.audio")
def story_audio(pid: str):
    s = db.get_story(pid)
    if not s:
        raise HTTPException(404)
    return Response(s[0], media_type=s[1])


@app.post("/api/pieces/{pid}/certificate")
def issue(pid: str, request: Request):
    d = db.get(pid)
    if not d:
        raise HTTPException(404, "unknown piece")
    if extract.missing(d):
        raise HTTPException(422, f"missing: {extract.missing(d)}")
    if not db.get_photo(pid):
        raise HTTPException(422, "A product photo is required before issuing a certificate.")
    payload = {
        "id": pid,
        "maker": d.get("maker_name", ""),
        "village": d.get("village", ""),
        "product": d["product"],
        "quantity": d["quantity"],
        "unit": d["unit"],
        "price": pricing.price(d),
        "variety": d.get("variety") or d.get("quality"),
        "harvest_date": d.get("harvest_date"),
        "story": bool(d.get("has_story")),
        "photo": True,
        "date": date.today().isoformat(),
    }
    try:
        token = certificate.make_token(payload)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    d["token"] = token
    db.save(pid, d)
    base = os.getenv("DAFTER_BASE_URL") or str(request.base_url).rstrip("/")
    return {"token": token, "url": f"{base}/v/{token}", "qr_svg": certificate.qr_svg(token, base),
            "payload": payload}


@app.get("/v/{token:path}", response_class=HTMLResponse)
def buyer(token: str):
    payload, valid = certificate.verify_token(token)
    return render_buyer(payload, valid)


@app.get("/qr/{token:path}.svg")
def qr(token: str, request: Request):
    return Response(certificate.qr_svg(token, os.getenv("DAFTER_BASE_URL") or str(request.base_url)), media_type="image/svg+xml")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/static/el-kef-highlands.png")
def landscape_background():
    return FileResponse(os.path.join(STATIC, "el-kef-highlands.png"), media_type="image/png")


@app.get("/api/location/reverse")
async def reverse_location(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "accept-language": "ar"},
                headers={"User-Agent": "DafterFarmAssistant/1.0 (local app)"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("Reverse geocoding failed (%s)", type(exc).__name__)
        raise HTTPException(503, "تعذّر تحديد البلاصة؛ قوليلي الولاية بالصوت.") from exc
    address = payload.get("address", {})
    place = (
        address.get("city") or address.get("town") or address.get("village")
        or address.get("municipality") or address.get("state")
    )
    if not place:
        raise HTTPException(404, "ما لقيناش اسم البلاصة؛ قوليلي الولاية بالصوت.")
    return {"location": place, "display_name": payload.get("display_name", place)}


app.mount("/static", StaticFiles(directory=Path(STATIC)), name="static")
