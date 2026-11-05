import atexit
import asyncio
import os
import tempfile
import uuid

DB_PATH = os.path.join(tempfile.gettempdir(), f"dafter-tests-{uuid.uuid4().hex}.db")
os.environ["DAFTER_DB"] = DB_PATH
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OLLAMA_MODEL"] = ""
os.environ["DAFTER_SECRET"] = "test-secret-for-dafter-test-suite-only-123"

import pytest
from fastapi.testclient import TestClient

from app import certificate, darija, extract, tts
from app.main import app

client = TestClient(app)
atexit.register(lambda: [os.path.exists(path) and os.remove(path) for path in (DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm")])


def test_arabizi_free_text_extraction():
    data = extract.parse_rules("ismi Fatma, 3andi 40 litre zit zitouna men Sejnane")
    assert data["maker_name"] == "Fatma"
    assert data["product"] == "zit zitouna"
    assert data["quantity"] == 40
    assert data["unit"] == "litre"
    assert data["village"] == "sejnane"


@pytest.mark.parametrize(
    ("text", "quantity", "unit", "product"),
    [
        ("Andi zouz gajouet tmatem b 9adeh nbi3hom", 2, "crate", "طماطم"),
        ("عندي زوز قاجوات طماطم", 2, "crate", "طماطم"),
        ("عندي 3 قفف تمر", 3, "basket", "تمر"),
        ("عندي 20 كيلو زيتون", 20, "kg", "زيتون"),
        ("عندي قنطار عسل", None, "quintal", "عسل"),
        ("عندي 5 حبات رمان", 5, "piece", "رمان"),
        ("عندي 2 طن تمر", 2, "ton", "تمر"),
    ],
)
def test_tunisian_quantity_unit_phrases(text, quantity, unit, product):
    data = extract.parse_rules(text)
    if quantity is not None:
        assert data["quantity"] == quantity
    assert data["unit"] == unit
    assert data["product"] == product


def test_missing_fields_include_location_variety_harvest_price_and_verified_photo():
    assert extract.missing({"product": "طماطم", "quantity": 2, "unit": "crate"}) == [
        "village", "variety", "harvest_date", "price_tnd", "photo_verified",
    ]
    assert extract.next_question({"product": "طماطم", "quantity": 2, "unit": "crate"}) in (
        "وين ساكنة؟ قوليلي اسم البلاصة ولا الولاية، يعيشك.",
        "في أنهي ولاية ولا مدينة موجودة السلعة؟",
    )
    assert extract.missing({
        "product": "طماطم", "quantity": 2, "unit": "crate", "village": "نابل",
        "variety": "سندريلا", "harvest_date": "2026-11-04", "price_tnd": 1.5,
        "photo_verified": True,
    }) == []


def test_photo_prompt_waits_until_all_other_required_fields_are_collected():
    first = client.post(
        "/api/log",
        json={"transcript": "Andi zouz gajouet tmatem b 9adeh nbi3hom"},
    ).json()
    assert first["question"]
    assert first["photoPrompt"] is False
    pid = first["piece"]["id"]

    for transcript in ("نابل", "بلدي", "تاريخ الجني 2026-01-02", "3"):
        response = client.post("/api/log", json={"transcript": transcript, "piece_id": pid})
        assert response.status_code == 200
        result = response.json()

    assert result["missing"] == ["photo_verified"]
    assert result["question"] is None
    assert result["photoPrompt"] is True
    assert result["canIssue"] is False
    assert result["reply"]


def test_follow_up_answers_are_bound_to_the_requested_field():
    previous = {"product": "طماطم", "quantity": 2, "unit": "crate", "awaiting_field": "village"}
    parsed = extract.parse_rules("نابل", previous)
    location = extract.apply_answer("village", "نابل", parsed, previous)
    assert location["village"] == "نابل"
    assert "product" not in location

    price_state = {"product": "طماطم", "quantity": 2, "unit": "crate"}
    parsed_price = extract.parse_rules("3", price_state)
    answer = extract.apply_answer("price_tnd", "3", parsed_price, price_state)
    assert answer["price_tnd"] == 3
    assert "quantity" not in answer

    parsed_unit = extract.parse_rules("قاجوة", price_state)
    answer_unit = extract.apply_answer("unit", "قاجوة", parsed_unit, price_state)
    assert answer_unit["unit"] == "crate"
    assert "quantity" not in answer_unit


def test_arabic_free_text_extraction():
    data = extract.parse_rules("عندي تمر دڨلة 25 كيلو")
    assert data["product"] == "تمر دڨلة"
    assert data["quantity"] == 25
    assert data["unit"] == "kg"


def test_unlisted_product_and_correction():
    data = extract.parse_rules("7asselt 3asel 12 kilo")
    assert data["product"] == "3asel"
    assert data["quantity"] == 12
    assert data["unit"] == "kg"

    corrected = extract.parse_rules("غلطت، موش 40 لتر، 50", {"unit": "litre", "quantity": 40})
    assert corrected["quantity"] == 50
    assert corrected["unit"] == "litre"


def test_price_and_time_intents():
    assert extract.is_price_question("9addech nbi3 el zit?")
    assert extract.is_price_question("قداش نبيع الهريسة؟")
    assert extract.parse_rules("khdemt 6 sw3at lyoum")["hours"] == 6
    assert extract.is_greeting("bonjour, kifech el 7al")
    assert extract.is_goodbye("شكرا بالسلامة")
    assert extract.is_unclear("ma fhemtekch")


def test_speakable_numbers_and_sentence_lengths():
    assert tts.speakable("185 دينار") == "مية و خمسة و ثمانين دينار"
    spoken = tts.speakable("مرحبا. " + "كلمة " * 60)
    assert all(len(sentence) <= 200 for sentence in tts._sentences(spoken))
    assert tts.number_words(0) == "صفر"
    assert tts.number_words(9999)
    with pytest.raises(ValueError):
        tts.number_words(10000)


def test_tts_disk_cache_hit(monkeypatch, tmp_path):
    calls = []

    async def fake_synthesis(text, voice, rate):
        calls.append((text, voice, rate))
        return b"mock-mp3"

    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path / "tts_cache")
    monkeypatch.setenv("DAFTER_TTS_VOICE", "test-voice")
    monkeypatch.setattr(tts, "_synthesize_edge_voice", fake_synthesis)

    first = asyncio.run(tts.synthesize_result("مرحبا"))
    second = asyncio.run(tts.synthesize_result("مرحبا"))
    assert first.audio == second.audio == b"mock-mp3"
    assert not first.cache_hit and second.cache_hit
    assert len(calls) == 1


def test_tts_voice_fallback_order(monkeypatch, tmp_path):
    calls = []

    async def no_wait(_):
        return None

    async def fake_synthesis(text, voice, rate):
        calls.append(voice)
        if voice == "configured-voice":
            raise RuntimeError("voice unavailable")
        return b"mock-mp3"

    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path / "tts_cache")
    monkeypatch.setenv("DAFTER_TTS_VOICE", "configured-voice")
    monkeypatch.setattr(tts, "_synthesize_edge_voice", fake_synthesis)
    monkeypatch.setattr(tts.asyncio, "sleep", no_wait)

    result = asyncio.run(tts.synthesize_result("مرحبا"))
    assert result.voice == "ar-TN-ReemNeural"
    assert calls == ["configured-voice"] * 3 + ["ar-TN-ReemNeural"]
    assert tts.voices() == [
        "configured-voice", "ar-TN-ReemNeural", "ar-TN-HediNeural", "ar-SA-ZariyahNeural",
    ]


def test_tts_health_failure_is_json_not_500(monkeypatch):
    async def fail(text, force=False):
        raise tts.TTSError("الصوت موش متاح.", "HTTP 403", "HTTP 403 means the edge-tts version is outdated")

    monkeypatch.setattr(tts, "synthesize_result", fail)
    response = client.get("/api/tts/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["bytes"] == 0
    assert body["error"]["en"] == "HTTP 403"
    assert "outdated" in body["hint"]


def test_tts_post_failure_is_json_not_500(monkeypatch):
    async def fail(text, force=False):
        raise tts.TTSError("الصوت موش متاح.", "HTTP 403", "upgrade edge-tts")

    monkeypatch.setattr(tts, "synthesize_result", fail)
    response = client.post("/api/tts", json={"text": "مرحبا"})
    assert response.status_code == 503
    assert response.json()["error_ar"]


def test_all_darija_templates_avoid_msa_blocklist():
    forbidden = ("هل", "ماذا", "لماذا", "سوف", "لقد", "أريد", "يمكنني")
    for messages in darija.TEMPLATES.values():
        for reply in messages:
            assert darija._valid_reply(reply)
            assert not any(word in reply for word in forbidden)


def test_log_api_and_generic_certificate(monkeypatch):
    response = client.post(
        "/api/log",
        json={"transcript": "ismi Fatma 3andi 40 litre zit zitouna men Sejnane"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["piece"]["product"] == "zit zitouna"
    assert data["piece"]["quantity"] == 40
    assert data["piece"]["unit"] == "litre"
    assert data["reply"] == data["reply_speech"] == data["reply_ar"]
    assert data["canIssue"] is False

    pid = data["piece"]["id"]
    client.post("/api/log", json={"transcript": "نوعية ممتازة", "piece_id": pid})
    client.post("/api/log", json={"transcript": "تاريخ الجني 2026-01-02", "piece_id": pid})
    client.post("/api/log", json={"transcript": "السعر 3 دينار", "piece_id": pid})
    from app import vision

    monkeypatch.setattr(vision, "analyse", lambda *_args: {
        "source": "test", "description": "verified test image", "caveat": "",
        "verified": True, "matches": True, "quality": "clear", "complexity": "verified",
    })
    from PIL import Image
    import io

    image = io.BytesIO()
    Image.effect_noise((32, 32), 20).save(image, "PNG")
    client.post(
        f"/api/pieces/{pid}/photo",
        files={"file": ("sample.png", image.getvalue(), "image/png")},
    )
    certificate_response = client.post(f"/api/pieces/{pid}/certificate")
    assert certificate_response.status_code == 200
    cert = certificate_response.json()
    page = client.get(f"/v/{cert['token']}").text
    assert "zit zitouna" in page
    assert "40" in page
    assert "not independently verify" in page
    assert client.get(f"/qr/{cert['token']}.svg").status_code == 200
    assert certificate.verify_token(cert["token"])[1]


def test_photo_offline_description():
    from PIL import Image
    import io

    pid = client.post("/api/log", json={"transcript": "عندي عسل 12 كيلو"}).json()["piece"]["id"]
    image = io.BytesIO()
    Image.effect_noise((200, 200), 60).save(image, "PNG")
    response = client.post(
        f"/api/pieces/{pid}/photo",
        files={"file": ("sample.png", image.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["vision"]["source"] == "unavailable"
    assert response.json()["vision"]["verified"] is False
    assert "200 by 200 pixels" in response.json()["vision"]["description"]


def test_requested_ten_inputs_print_darija_replies():
    messages = [
        "ismi Fatma, 3andi 40 litre zit zitouna men Sejnane",
        "عندي تمر دڨلة 25 كيلو",
        "7asselt 3asel 12 kilo",
        "9addech nbi3 el zit?",
        "ma fhemtekch",
        "غلطت، موش 40 لتر، 50",
        "bonjour, kifech el 7al",
        "قداش نبيع الهريسة؟",
        "khdemt 6 sw3at lyoum",
        "شكرا بالسلامة",
    ]
    first_piece = None
    for index, message in enumerate(messages):
        body = {"transcript": message}
        if index == 5:
            body["piece_id"] = first_piece
        response = client.post("/api/log", json=body)
        assert response.status_code == 200
        result = response.json()
        if index == 0:
            first_piece = result["piece"]["id"]
        reply = result["reply"]
        assert reply and reply == result["reply_speech"]
        assert darija._valid_reply(reply)
        print(f"{index + 1}. {message} -> {reply}")


def test_product_switch_resets_old_quantity():
    first = client.post("/api/log", json={"transcript": "3andi 40 litre zit zitouna"}).json()
    pid = first["piece"]["id"]
    dates = client.post(
        "/api/log",
        json={"transcript": "عندي تمر دڨلة 25 كيلو", "piece_id": pid},
    ).json()["piece"]
    assert dates["product"] == "تمر دڨلة"
    assert dates["quantity"] == 25
    assert dates["unit"] == "kg"


def test_certificate_signature_rejects_tampering():
    token = certificate.make_token({"id": "sample", "product": "honey"})
    assert certificate.verify_token(token)[1]
    body, signature = token.split(".")
    altered_body = b'{"id":"sample","product":"olive oil"}'
    tampered = f"{certificate._b64(altered_body)}.{signature}"
    assert body != tampered.split(".")[0]
    assert certificate.verify_token(tampered)[1] is False
