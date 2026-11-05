"""Free-text extraction for Tunisian Darija, Arabizi, Arabic, and mixed French."""
import json
import logging
import os
import re
import unicodedata
from datetime import date

from . import darija

LOGGER = logging.getLogger(__name__)
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
DIAC = re.compile(r"[\u064B-\u0652\u0640]")
GLUED_UNIT = re.compile(
    r"(?<![a-z\d])(\d+(?:\.\d+)?)(kgs?|kilos?|kilograms?|litres?|liters?|l|tons?|tonnes?|كيلو|كغ|لتر|طن)(?![a-z])"
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).translate(AR_DIGITS).lower()
    text = DIAC.sub("", text)
    for source, target in (
        ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"),
        ("ؤ", "و"), ("ئ", "ي"),
    ):
        text = text.replace(source, target)
    text = re.sub(r"(?<!\d)[.,]|[،,;!?؟:'’]", " ", text)
    # "2kg" / "20kilo" / "5l" -> "2 kg" (only when the number is not part of an Arabizi word like "3andi")
    text = GLUED_UNIT.sub(r"\1 \2", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalized_words(words: str) -> set[str]:
    return {normalize(word) for word in words.split()}


NUMBER_WORDS: dict[str, float] = {}
for value, words in {
    1: "wahed wahd waheda wahda وحد واحد وحده واحده",
    2: "jouj zouz zoz joj جوج زوج زوز",
    3: "tlata tleta tlat talata ثلاثة تلاتة ثلاثه تلاثه",
    4: "arba3a arb3a arba3 اربعه اربعة",
    5: "khamsa khamssa خمسه خمسة",
    6: "sta setta sitta سته ستة ستا",
    7: "seb3a sab3a سبعه سبعة",
    8: "tmenya tmanya tmenia ثمانيه ثمانية تمنيه تمنية تمانية",
    9: "ts3a tis3a تسعه تسعة",
    10: "3chra achra ashra 3achra عشره عشرة",
    20: "3achrin 3ichrin عشرين عشرون",
}.items():
    for word in words.split():
        NUMBER_WORDS[normalize(word)] = float(value)

UNIT_GROUPS = {
    "litre": "litre liter litres liters l لتر لتره لترين",
    "kg": "kilo kilos kilogram kilograms kg كيلو كيلوجرام كغ",
    "quintal": "qintar qantar quintal quintaux قنطار قناطير",
    "ton": "ton tonne tons tonnes طن أطنان",
    "crate": "crate crates cajoua cajouet gajoua gajouet gajwet gajwa gajouet قاجوة قاجوات قاجوه قاجوات",
    "box": "box boxes carton cartons صندوق صناديق كرتونه",
    "basket": "basket baskets qoffa qoffet qfaf قفه قفة قفاف قفف",
    "piece": "piece pieces habba habba حبه حبة حبات",
    "bottle": "bottle bottles qaroura قاروره قارورة قارورات",
    "hour": "hour hours h heure heures sa3a sw3at sa3at ساعات ساعة سوايع",
    "day": "day days jour jours youm iyem ayam ayem ايام يوم",
    "week": "week weeks semaine semaines jem3a jemaa جمعه جمعة اسبوع اسابيع",
}
UNIT_LOOKUP = {
    normalize(word): unit
    for unit, aliases in UNIT_GROUPS.items()
    for word in aliases.split()
}

FILLER_WORDS = _normalized_words(
    "ismi smiti esmi 3andi andi عندي عندي ana أنا انا men من de du des from "
    "n3ich na3ich nعيش نعيش ساكنة ساكن ساكنين ولاية الولاية مدينة المدينة "
    "dafter دفتر "
    "kamalt kammalt 7asselt hassalt khdemt khdmet خدمت نخدم نبيع nbi3 bi3 "
    "el al le la les un une منّو متاعه متاع متاعي متاعك "
    "قداش قداش شنية شنوة شنوّة شنو قوليلي قولي احكيلي عند عندها "
    "lyoum today aujourd hui اليوم توّا توة نهار "
    "bonjour bonsoir salut kifech kif 7al كيفاش كيف الحال الحال لاباس "
    "ma moch mech موش مش ما ميسالش "
    "fhemtekch fhemtech fhemtek نفهمتكش فهمتكش "
    "ghalta ghalet غلطت "
    "merci shokran شكرا شكرا ليك بالسلامة سلام "
    "9addech 9addach 9adeh chnowa chnoua chnia chneya بقداه نبيعهم "
    "price prix soum سعر السعر نبيع نبيعها nbi3hom 9adeh 9addeh 9addach بقداه "
    "دينار دينارات tnd dt تاريخ الجني date harvest harvest-date نوع نوعية صنف جودة "
    "quality variety variete ممتاز ممتازة "
    "w و ya يا fi في fel في ال fil b "
    # English / French / Darija "I want to sell ..." phrasing
    "i im want wanna would like to sell selling have got my some of the a an and about around "
    "je j d veux voudrais vendre vends ai avoir mon ma mes environ "
    "nheb n7eb nhab nhib n7ib bghit نحب حاب حابة نحبش بش باش "
    "عسلامة عسلامه مرحبا اهلا aslema 3aslema marhba ahla "
)
CORRECTION_WORDS = _normalized_words("ghalta ghaltet غلطت موش مش لا")
GREETING_WORDS = _normalized_words("bonjour bonsoir salut سلام عسلامه مرحبا اهلا kifech kif")
GOODBYE_WORDS = _normalized_words("بالسلامة مع السلامه bye goodbye")
UNCLEAR_WORDS = _normalized_words("ma fhemtekch ma fhemtch fhemtekch ما فهمتش مافهمتش")
PRICE_WORDS = _normalized_words("9addech 9addach 9adeh b9adeh nbi3 nbi3hom prix price soum نبيع نبيعهم سعر السعر قداش بقداه")
NAME_MARKERS = _normalized_words("ismi smiti esmi اسمي سميتي")
LOCATION_MARKERS = _normalized_words("men de from من fi fel f في ولاية الولاية مدينة المدينة wilaya")
REQUIRED = ["product", "quantity", "unit", "village", "variety", "harvest_date", "price_tnd", "photo_verified"]


def _number(token: str) -> float | None:
    try:
        value = float(token)
        return value if value.is_integer() else value
    except ValueError:
        return NUMBER_WORDS.get(token)


def _extract_name(text: str) -> str | None:
    words = re.sub(r"[،,;!?؟]", " ", text).split()
    for index, word in enumerate(words[:-1]):
        if normalize(word) in NAME_MARKERS:
            name = words[index + 1].strip(" .،,!?؟")
            return name[:80] or None
    return None


def _extract_village(normalized: str) -> str | None:
    tokens = normalized.split()
    for index, token in enumerate(tokens[:-1]):
        if token in LOCATION_MARKERS and tokens[index + 1] not in PRODUCT_ALIASES:
            candidate = []
            for part in tokens[index + 1:]:
                if part in FILLER_WORDS or part in UNIT_LOOKUP or _number(part) is not None or re.match(r"\d", part):
                    break
                candidate.append(part)
                if len(candidate) == 4:
                    break
            if candidate:
                return " ".join(candidate)[:120]
    return None


PRODUCT_PHRASES = {
    "olive oil": "زيت زيتون", "huile d olive": "زيت زيتون", "huile olive": "زيت زيتون",
    "pomme de terre": "بطاطا", "pommes de terre": "بطاطا",
}
PRODUCT_ALIASES = {}
for _arabic, _words in {
    "طماطم": "tmatem tomatem tomates tomate tomato tomatoes",
    "تمر": "dates dattes datte",
    "زيتون": "olives olive",
    "زيت": "oil huile",
    "عسل": "honey miel",
    "رمان": "pomegranate pomegranates grenade grenades",
    "بطاطا": "potato potatoes patate patates",
    "بصل": "onion onions oignon oignons",
    "فلفل": "pepper peppers piment piments poivron poivrons",
    "برتقال": "orange oranges",
    "ليم": "lemon lemons citron citrons",
    "كرموس": "fig figs figue figues",
    "لوز": "almond almonds amande amandes",
    "قمح": "wheat ble",
    "شعير": "barley orge",
    "عنب": "grapes grape raisin raisins",
    "تفاح": "apple apples pomme pommes",
    "دلاع": "watermelon pasteque",
    "بطيخ": "melon melons",
    "فراولو": "strawberry strawberries fraise fraises",
    "جزر": "carrot carrots carotte carottes",
    "ثوم": "garlic ail",
    "بيض": "eggs egg oeufs oeuf",
    "حليب": "milk lait",
    "كسكسي": "couscous",
    "هريسة": "harissa",
}.items():
    for _word in _words.split():
        PRODUCT_ALIASES[normalize(_word)] = _arabic


def _product_text(normalized: str) -> str | None:
    for phrase, arabic in PRODUCT_PHRASES.items():
        normalized = re.sub(rf"\b{phrase}\b", arabic.replace(" ", "_"), normalized)
    tokens = normalized.split()
    for index, token in enumerate(tokens):
        if token in NAME_MARKERS:
            tokens = tokens[index + 2:]
            break
    for index, token in enumerate(tokens):
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token in LOCATION_MARKERS and following not in PRODUCT_ALIASES and "_" not in following:
            tokens = tokens[:index]
            break
    product_tokens = [
        token for token in tokens
        if token not in FILLER_WORDS
        and token not in UNIT_LOOKUP
        and token not in NUMBER_WORDS
        and _number(token) is None
        and not re.fullmatch(r"\d+(?:\.\d+)?", token)
    ]
    product = " ".join(product_tokens).strip()
    aliases = PRODUCT_ALIASES
    product_tokens = [aliases.get(token, token).replace("_", " ") for token in product.split()]
    return " ".join(product_tokens)[:120] or None


def _extract_date(text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})(?!\d)", text)
    if not match:
        return None
    raw = match.group(1)
    try:
        if "-" in raw and raw[:4].isdigit():
            return date.fromisoformat(raw).isoformat()
        day, month, year = re.split(r"[/-]", raw)
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def _extract_variety(text: str) -> str | None:
    match = re.search(
        r"(?:نوع(?:ية)?|صنف|جودة|quality|variety|variete)\s*[:：]?\s*([\w\u0600-\u06ff-]{2,40}(?:\s+(?!ممتاز|ممتازة|باهي|باهية)[\w\u0600-\u06ff-]{2,40})?)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def parse_rules(text: str, previous: dict | None = None) -> dict:
    normalized = normalize(text)
    tokens = normalized.split()
    result: dict = {}
    quantity_pairs: list[tuple[float, str]] = []
    bare_numbers: list[float] = []
    hour_values: list[float] = []
    day_values: list[float] = []

    for index, token in enumerate(tokens):
        value = _number(token)
        if value is None:
            implicit_unit = UNIT_LOOKUP.get(token)
            if implicit_unit and implicit_unit not in {"hour", "day", "week"} and (
                index == 0 or _number(tokens[index - 1]) is None
            ):
                quantity_pairs.append((1, implicit_unit))
            continue
        next_unit = UNIT_LOOKUP.get(tokens[index + 1]) if index + 1 < len(tokens) else None
        if next_unit == "hour":
            hour_values.append(value)
        elif next_unit == "day":
            day_values.append(value)
        elif next_unit == "week":
            day_values.append(value * 7)
        elif next_unit:
            quantity_pairs.append((value, next_unit))
        else:
            bare_numbers.append(value)

    correction = any(token in CORRECTION_WORDS for token in tokens)
    if correction and bare_numbers:
        result["quantity"] = bare_numbers[-1]
        result["unit"] = quantity_pairs[-1][1] if quantity_pairs else (previous or {}).get("unit")
    elif quantity_pairs:
        result["quantity"], result["unit"] = quantity_pairs[-1]
    elif bare_numbers and previous and previous.get("unit"):
        result["quantity"] = bare_numbers[-1]
        result["unit"] = previous["unit"]

    if hour_values:
        result["hours"] = hour_values[-1]
    if day_values:
        result["days"] = day_values[-1]
    if result.get("hours") and result.get("days"):
        result["hours"] *= result["days"]

    name = _extract_name(text)
    if name:
        result["maker_name"] = name
    village = _extract_village(normalized)
    if village:
        result["village"] = village

    harvest_date = _extract_date(text)
    if harvest_date:
        result["harvest_date"] = harvest_date
    variety = _extract_variety(text)
    if variety:
        result["variety"] = variety
    product = _product_text(normalized)
    if product and product != harvest_date and (not variety or normalize(product) != normalize(variety)):
        result["product"] = product

    if any(token in PRICE_WORDS for token in tokens):
        currency_index = next(
            (i for i, token in enumerate(tokens) if token in {"دينار", "دينارات", "tnd", "dt"}),
            None,
        )
        if currency_index is not None and currency_index > 0:
            price_value = _number(tokens[currency_index - 1])
            if price_value is not None:
                result["price_tnd"] = price_value
    return validate_data(result)


def validate_data(data: dict) -> dict:
    allowed = {
        "product": (str, 120),
        "unit": (str, 40),
        "maker_name": (str, 80),
        "village": (str, 120),
        "variety": (str, 80),
        "quality": (str, 80),
        "harvest_date": (str, 20),
        "notes": (str, 300),
        "intent": (str, 40),
    }
    clean: dict = {}
    for key, (kind, max_length) in allowed.items():
        value = data.get(key)
        if isinstance(value, kind) and value.strip() and len(value.strip()) <= max_length:
            clean[key] = value.strip()
    if not clean.get("village") and isinstance(data.get("location"), str):
        location = data["location"].strip()
        if location and len(location) <= 120:
            clean["village"] = location
    numeric_ranges = {
        "quantity": (0, 1_000_000),
        "price_tnd": (0, 10_000_000),
        "days": (0, 3650),
        "hours": (0, 100_000),
        "hours_per_day": (0, 24),
    }
    for key, (minimum, maximum) in numeric_ranges.items():
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and minimum < value <= maximum:
            clean[key] = float(value) if isinstance(value, float) else value
    return clean


def _clean_json(raw: str) -> dict:
    parsed = json.loads(re.sub(r"```(?:json)?|```", "", raw).strip())
    if not isinstance(parsed, dict):
        raise ValueError("The language model response must be a JSON object")
    return parsed


def parse_llm(text: str, previous: dict | None = None) -> dict:
    from . import llm

    provider = llm.active_provider()
    if provider == "none":
        return {}

    context = json.dumps(previous or {}, ensure_ascii=False)
    prompt = f"Previous record: {context}\nNew farmer message: {text}"

    try:
        raw_text, _used = llm.chat(
            darija.EXTRACTION_SYSTEM,
            prompt,
            max_tokens=400,
            json_format=True,
        )
        return validate_data(_clean_json(raw_text))
    except Exception as exc:
        LOGGER.warning(
            "LLM extraction unavailable (%s via %s); using local parsing",
            type(exc).__name__,
            provider,
        )
        return {}


def extract(text: str, previous: dict | None = None) -> dict:
    data = parse_rules(text, previous)
    model_data = parse_llm(text, previous)
    intent = model_data.get("intent")
    if isinstance(intent, str) and intent in {
        "sale", "price_question", "greeting", "goodbye", "product_listing", "unclear", "other",
    }:
        data.setdefault("intent", intent)
    if "hours" not in data and data.get("days") and data.get("hours_per_day"):
        data["hours"] = data["days"] * data["hours_per_day"]
    return validate_data(data)


def apply_answer(field: str, text: str, parsed: dict, previous: dict) -> dict:
    answer = dict(parsed)
    if field == "village":
        if any(key in answer for key in ("quantity", "unit", "variety", "harvest_date", "price_tnd")):
            return validate_data(answer)
        answer.pop("product", None)
        answer["village"] = _extract_village(normalize(text)) or text.strip()[:120]
    elif field in {"variety", "quality"}:
        answer.pop("product", None)
        answer[field] = answer.get(field) or text.strip()[:80]
    elif field == "harvest_date":
        answer.pop("product", None)
        harvest_date = answer.get("harvest_date") or _extract_date(text)
        if harvest_date:
            answer["harvest_date"] = harvest_date
    elif field == "price_tnd":
        answer.pop("product", None)
        if not answer.get("price_tnd"):
            for token in normalize(text).split():
                amount = _number(token)
                if amount is not None and amount > 0:
                    answer["price_tnd"] = amount
                    break
        answer.pop("quantity", None)
    elif field == "quantity":
        if not answer.get("quantity"):
            for token in normalize(text).split():
                amount = _number(token)
                if amount is not None and amount > 0:
                    answer["quantity"] = amount
                    break
    elif field == "unit":
        unit = answer.get("unit") or next(
            (UNIT_LOOKUP[token] for token in normalize(text).split() if token in UNIT_LOOKUP),
            None,
        )
        if unit:
            answer["unit"] = unit
            explicit_quantity = any(_number(token) is not None for token in normalize(text).split())
            if previous.get("quantity") and not explicit_quantity:
                answer.pop("quantity", None)
    elif field == "product":
        answer["product"] = answer.get("product") or text.strip()[:120]
    return validate_data(answer)


def is_greeting(text: str) -> bool:
    return any(token in GREETING_WORDS for token in normalize(text).split())


def is_goodbye(text: str) -> bool:
    normalized = normalize(text)
    return any(phrase in normalized for phrase in ("بالسلامة", "بالسلامه", "مع السلامة", "مع السلامه", "bye", "goodbye"))


def is_unclear(text: str) -> bool:
    normalized = normalize(text)
    return any(phrase in normalized for phrase in ("ma fhemtekch", "ma fhemtch", "ما فهمتش", "مافهمتش"))


def is_price_question(text: str) -> bool:
    return any(token in PRICE_WORDS for token in normalize(text).split())


def missing(data: dict) -> list[str]:
    missing_fields = []
    for key in REQUIRED:
        if key == "village" and (data.get("village") or data.get("location")):
            continue
        if key == "variety" and (data.get("variety") or data.get("quality")):
            continue
        if key == "photo_verified" and data.get("photo_verified") is True:
            continue
        if key == "photo_verified":
            missing_fields.append(key)
            continue
        if data.get(key) in (None, ""):
            missing_fields.append(key)
    return missing_fields


def finalize_hours(data: dict) -> dict:
    if not data.get("hours") and data.get("days") and data.get("hours_per_day"):
        data["hours"] = data["days"] * data["hours_per_day"]
    return data


def next_question(data: dict) -> str | None:
    missing_fields = [field for field in missing(data) if field != "photo_verified"]
    if not missing_fields:
        return None
    if missing_fields[0] == "product":
        return darija.choose("question_product")
    if missing_fields[0] == "quantity":
        return darija.choose("question_quantity")
    questions = {
        "unit": "question_unit",
        "village": "question_location",
        "variety": "question_variety",
        "harvest_date": "question_harvest",
        "price_tnd": "question_price",
    }
    return darija.choose(questions[missing_fields[0]])


def reply_for(text: str, data: dict) -> tuple[str, bool]:
    """Generate a reply for the given transcript and state.

    Returns (reply_text, used_template) where *used_template* is True
    when the LLM was unavailable and a canned Darija template was used.
    """
    if is_goodbye(text):
        fallback = darija.choose("goodbye")
    elif is_unclear(text):
        fallback = darija.choose("not_understood")
    elif is_price_question(text):
        fallback = darija.choose("price_unavailable")
        question = next_question(data)
        if question:
            fallback = f"{fallback} {question}"
    elif is_greeting(text) and not data.get("product") and not data.get("quantity"):
        fallback = darija.choose("greeting")
    else:
        question = next_question(data)
        if question:
            fallback = question
        else:
            unit = {
                "crate": "قاجوات",
                "basket": "قفاف",
                "piece": "حبات",
                "kg": "كيلو",
                "quintal": "قنطار",
                "ton": "طن",
                "litre": "لتر",
                "box": "صناديق",
                "bottle": "قوارير",
            }.get(str(data.get("unit")), "")
            fallback = (
                f"عندك {data.get('quantity')} {unit} من {data.get('product')}."
                f" إنت في {data.get('village')}. السوم اللي قلتِ عليه {data.get('price_tnd')} دينار، "
                "أما ما عنديش تقدير سوق موثوق."
            )
    return darija.generate_reply(text, data, fallback)
