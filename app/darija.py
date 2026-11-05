"""Tunisian Darija dialogue templates and prompts."""
import logging
import os
import random
import re

LOGGER = logging.getLogger(__name__)

TEMPLATES = {
    "greeting": [
        "وعليكم السلام، لاباس؟ قوليلي شنية تحبي تسجّلي.",
        "مرحبا بيك، تفضّلي احكيلي على المنتوج متاعك.",
        "مرحبا بيك، شنية نعاونك فيه توّا؟",
    ],
    "question_product": [
        "شنية المنتوج اللي تحبي تحكيلي عليه؟",
        "تفضّلي، شنية الحاجة اللي تحبي تسجّليها؟",
        "مالا قوليلي، على شنية باش نحكيو؟",
    ],
    "question_quantity": [
        "قدّاش عندك منّو، وباشنوّة وحدة؟",
        "قدّاش الكمية؟ قوليلي زادة الوحدة، يعيشك.",
        "شنية الكمية وباشنوّة تقيسيها؟",
    ],
    "question_unit": [
        "قدّاش الكمية؟ وباللتر ولا بالكيلو ولا بوحدة أخرى؟",
        "شنية الوحدة متاع الكمية؟",
        "قوليلي الكمية ووحدتها، يعيشك.",
    ],
    "question_location": [
        "وين ساكنة؟ قوليلي اسم البلاصة ولا الولاية، يعيشك.",
        "في أنهي ولاية ولا مدينة موجودة السلعة؟",
    ],
    "question_variety": [
        "شنية صنف المنتوج ولا جودتو؟",
        "قوليلي على النوعية ولا الجودة متاعو، يعيشك.",
    ],
    "question_harvest": [
        "نهار قداش جنيتي المنتوج؟ قوليلي التاريخ.",
        "وقتاش صار الجني؟ قوليلي التاريخ بالنهار والشهر والسنة.",
    ],
    "question_price": [
        "قدّاش تحبي تبيعيه؟ قوليلي السعر بالدينار، وإذا ما تعرفيش نخلّيوه فارغ.",
        "شنية السوم اللي تحبي عليه؟ ما عنديش توا أسعار سوق موثوقة باش نخمنلك.",
    ],
    "question_photo": [
        "تنجم تصوّرلي السلعة؟ نحتاج تصويرة واضحة باش نتحقق منها.",
        "يعيشك ابعثي تصويرة حقيقية للمنتوج باش نكملو.",
    ],
    "photo_mismatch": [
        "التصويرة ما تطابقتش مع المنتوج اللي حكيتلي عليه. ميسالش، عاودي صوّرلي السلعة وحدها وبوضوح.",
        "سامحيني، ما نجمتش نأكد اللي في التصويرة هو نفس المنتوج. جرّبي تصويرة أخرى واضحة.",
    ],
    "photo_unverified": [
        "التصويرة وصلت، أما ما نجمتش نتحقق منها في هالتطبيق. ما نجمش نعمل شهادة قبل ما نتأكدوا من المنتوج.",
    ],
    "question_other": [
        "تحبي تزيدي معلومة أخرى؟",
        "فمّا تفصيل آخر تحبي تسجّليه؟",
        "نزيدو معلومة أخرى ولا هكّا يكفي؟",
    ],
    "confirmation": [
        "وصلتني المعلومات، يعيشك. تحبي تزيدي تفصيل آخر؟",
        "سجّلت التفاصيل، تفضّلي. نزيدو حاجة أخرى؟",
        "واضحة، يعيشك. تحبي تحكيلي على تفصيل آخر؟",
    ],
    "price": [
        "باش نعاونك في السعر، يلزم نعرفو أسعار السوق والجودة. قدّاش معروض عليك؟",
        "ما نحبّش نخمنلك في السعر. شنية الأسعار اللي لقيتيها في السوق؟",
        "السعر يتبدّل حسب الجودة والسوق. قدّاش قالولك عليه؟",
    ],
    "price_unavailable": [
        "ما عنديش توا بيانات سوق موثوقة باش نقترحلك سوم، وما نحبّش نخمن.",
        "السوم يتبدّل وما عنديش مصدر سوق حيّ توا، لذلك ما نجمش نعطيك تقدير موثوق.",
    ],
    "not_understood": [
        "ميسالش، ما فهمتش شنية تقصدي. جرّبي قوليها بطريقة أخرى.",
        "ياخي نعاودوها بالراحة؟ قوليلي شنية تحبي تسجّلي.",
        "ما وصلنيش قصدك، يعيشك عاودي احكيلي.",
    ],
    "try_again": [
        "جرّبي مرّة أخرى، واحكيلي بالراحة.",
        "ميسالش، عاودي قوليلي شنية صار.",
        "نعاودوها؟ تفضّلي احكيلي من جديد.",
    ],
    "goodbye": [
        "يعيشك، بالسلامة.",
        "شكرا ليك، بالسلامة.",
        "ربي يعينك، بالسلامة.",
    ],
    "server_error": [
        "صار مشكل في الاتصال. جرّبي مرّة أخرى بعد شوية.",
        "ما نجمتش نوصل للمعلومات توّا. عاودي بعد شوية، يعيشك.",
    ],
    "photo_error": [
        "ما نجمتش نحلّل التصويرة توّا. جرّبي تصويرة أخرى.",
        "التصويرة ما وصلتش واضحة. عاودي جرّبي، يعيشك.",
    ],
    "transcription_error": [
        "ما سمعتكش مليح. جرّبي احكي أقرب للميكرو ولا اكتبيلي.",
        "الصوت ما توضّحليش. عاودي احكي بالراحة ولا اكتبيلي.",
    ],
    "tts_error": [
        "الصوت موش متاح.",
    ],
}

EXTRACTION_SYSTEM = """Extract only facts explicitly stated by the farmer. Return one JSON object with keys intent, product, quantity, unit, location, price_tnd, variety, quality, harvest_date, and missing_fields; also include maker_name, village, days, hours, hours_per_day, and notes when stated. Never invent or infer a missing fact. Understand Tunisian Darija in Arabic script and Arabizi, including 3=ع, 7=ح, 9=ق, 5=خ, 8=غ, and French mixes. Map numbers and measurement units to numbers and short normalized units; crates (قاجوة/قاجوات/gajouet) use unit "crate". Preserve unknown product names verbatim. missing_fields lists required fields not found in the message or previous record. Return JSON only."""

REPLY_SYSTEM = """إنتي معاونة تونسية طيّبة تحكي مع فلاحة تونسية. جاوبي بالدارجة التونسية وبالحروف العربية فقط، في جملة ولا زوز قصار، واسألي سؤال واحد برك. استعملي كلام بسيط وأرقام مكتوبة بالحروف. ما تخمّنيش في معلومة وما توعديش بنتيجة قانونية ولا مالية. ممنوع تخترعي أسعار سوق؛ كان ما فماش مصدر أسعار موثوق قولي هذا بوضوح. ممنوع تستعملي: هل، ماذا، لماذا، سوف، لقد، أريد، يمكنني. جاوبي على كلامها حسب المعلومات اللي عطاتهملك."""


def choose(key: str) -> str:
    choices = TEMPLATES.get(key)
    if not choices:
        raise KeyError(f"Unknown Darija template: {key}")
    return random.choice(choices)


def tts_error_ar() -> str:
    return choose("tts_error")


def generate_reply(transcript: str, state: dict, fallback: str) -> tuple[str, bool]:
    """Generate a reply using the active LLM provider.

    Returns (reply_text, used_template).
    ``used_template`` is True when the LLM was unavailable and a local
    template was returned instead.
    """
    from . import llm

    provider = llm.active_provider()
    user_content = f"كلامها: {transcript}\nالمعلومات المسجلة: {state}\nالرد المقترح: {fallback}"

    if provider == "anthropic":
        try:
            reply = llm.anthropic_chat(REPLY_SYSTEM, user_content, max_tokens=160)
            if _valid_reply(reply):
                return reply, False
            LOGGER.warning("Darija reply model returned invalid text; using a local template")
        except Exception as exc:
            LOGGER.warning("Darija reply model unavailable (%s); using a local template", type(exc).__name__)
    elif provider == "ollama":
        try:
            reply = llm.ollama_chat(REPLY_SYSTEM, user_content)
            if _valid_reply(reply):
                return reply, False
            LOGGER.warning("Darija reply model returned invalid text; using a local template")
        except Exception as exc:
            LOGGER.warning("Darija reply model unavailable (%s); using a local template", type(exc).__name__)

    return fallback, True


def _valid_reply(reply: str) -> bool:
    if not reply or len(reply) > 240:
        return False
    if re.search(r"[A-Za-z]", reply):
        return False
    if re.search(r"(?<![\u0600-\u06ff])(?:هل|ماذا|لماذا|سوف|لقد|أريد|يمكنني)(?![\u0600-\u06ff])", reply):
        return False
    return bool(re.fullmatch(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\s،؛؟.!؟٠-٩0-9]+", reply))
