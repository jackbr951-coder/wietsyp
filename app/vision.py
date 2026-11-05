"""Describe visible details in a submitted farm or food product photo."""
import base64
import io
import json
import logging
import os
import re

from PIL import Image

LOGGER = logging.getLogger(__name__)
PROMPT = """Look at this photo of a farm or food product. Describe only visible details in a short neutral sentence. Do not infer quantity, weight, origin, freshness, safety, or market value. Return JSON with keys description and caveat."""
VERIFY_PROMPT = """Check whether the photo visibly contains the stated product. Return JSON only with: matches (true, false, or null if uncertain), quality (a short description of visible appearance only, or null), description, caveat. Do not infer safety, freshness, origin, or quantity. Product: """


def heuristic(image_bytes: bytes) -> dict:
    with Image.open(io.BytesIO(image_bytes)) as image:
        width, height = image.size
    return {
        "source": "unavailable",
        "description": f"Received a {width} by {height} pixels image; this installation has no configured image-understanding model, so the product is unverified.",
        "caveat": "No product match or quality assessment was performed.",
        "verified": False,
        "matches": None,
        "quality": None,
        "complexity": "unverified",
    }


def _shrink(image_bytes: bytes, mime: str, max_side: int = 768) -> tuple[bytes, str]:
    """Downscale large phone photos so a small local vision model answers quickly."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            image.thumbnail((max_side, max_side))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, mime


ARABIC_PRODUCT_NAMES = {
    "طماطم": "tomatoes", "تمر": "dates (date fruit)", "زيتون": "olives", "زيت": "oil",
    "زيت زيتون": "olive oil", "عسل": "honey", "رمان": "pomegranates", "بطاطا": "potatoes",
    "بصل": "onions", "فلفل": "peppers", "برتقال": "oranges", "ليم": "lemons", "كرموس": "figs",
    "لوز": "almonds", "قمح": "wheat", "شعير": "barley", "عنب": "grapes", "تفاح": "apples",
    "دلاع": "watermelon", "بطيخ": "melon", "فراولو": "strawberries", "جزر": "carrots",
    "ثوم": "garlic", "بيض": "eggs", "حليب": "milk", "كسكسي": "couscous", "هريسة": "harissa",
}


def _product_label(product: str) -> str:
    product = (product or "").strip()
    english = ARABIC_PRODUCT_NAMES.get(product) or next(
        (name for arabic, name in ARABIC_PRODUCT_NAMES.items() if product.startswith(arabic)), None
    )
    return f"{product} ({english})" if english else product


def analyse(image_bytes: bytes, mime: str, product: str = "") -> dict:
    image_bytes, mime = _shrink(image_bytes, mime)
    product = _product_label(product)
    key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("OLLAMA_VISION_MODEL", "").strip()
    if key or model:
        try:
            if key:
                import anthropic

                response = anthropic.Anthropic(api_key=key, timeout=30, max_retries=1).messages.create(
                    model=os.getenv("DAFTER_LLM_MODEL", "claude-3-5-haiku-latest"),
                    max_tokens=220,
                    system=VERIFY_PROMPT + product,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime,
                                    "data": base64.b64encode(image_bytes).decode(),
                                },
                            },
                            {"type": "text", "text": "Verify this product photo."},
                        ],
                    }],
                )
                raw = "".join(
                    block.text for block in response.content
                    if getattr(block, "type", None) == "text"
                )
                source = "claude-vision"
            else:
                import httpx

                response = httpx.post(
                    os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
                    timeout=float(os.getenv("OLLAMA_VISION_TIMEOUT_SECONDS", "180")),
                    json={
                        "model": model,
                        "stream": False,
                        "format": "json",
                        "messages": [
                            {"role": "system", "content": VERIFY_PROMPT + product},
                            {
                                "role": "user",
                                "content": "Verify this product photo.",
                                "images": [base64.b64encode(image_bytes).decode()],
                            },
                        ],
                    },
                )
                response.raise_for_status()
                raw = response.json()["message"]["content"]
                source = "ollama-vision"
            result = json.loads(re.sub(r"```(?:json)?|```", "", raw).strip())
            description = result.get("description")
            caveat = result.get("caveat")
            matches = result.get("matches")
            quality = result.get("quality")
            if (
                not isinstance(description, str) or not description.strip() or len(description) > 400
                or matches not in (True, False, None)
                or (quality is not None and not isinstance(quality, str))
            ):
                raise ValueError("The vision response did not contain the required verification fields")
            return {
                "source": source,
                "description": description.strip(),
                "caveat": caveat.strip()[:400] if isinstance(caveat, str) else "",
                "verified": matches is True,
                "matches": matches,
                "quality": quality.strip()[:200] if isinstance(quality, str) else None,
                "complexity": "verified" if matches is True else "unverified",
            }
        except Exception as exc:
            LOGGER.warning("Photo verification failed (%s)", type(exc).__name__)
    return heuristic(image_bytes)
