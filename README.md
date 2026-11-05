# Dafter (دفتر)

A local-first, voice-oriented assistant for Tunisian farm products. It uses Ollama for chat, browser speech synthesis by default, and never fabricates market-price data or claims a photo was checked when it was not.

## Quick start on Windows

1. Double-click `setup.bat` once. It installs Python and Ollama if missing, downloads the chat model (`qwen2.5:1.5b`), installs the Python packages, and starts Dafter.
2. Optional, for photo verification and certificates: double-click `get-vision.bat`. It downloads `qwen3-vl:2b` (about 2 GB, retries automatically if the connection drops) and enables it in `.env`.
3. Afterwards, start Dafter with `run.bat`; use `restart.bat` after changing code.


## Run on Windows

Double-click `run.bat`. It creates `.env` from `.env.example` if needed, installs the small application dependencies, starts the server, and opens `http://127.0.0.1:8000`.

Ollama must be running and the configured model must be installed. Dafter defaults to `qwen2.5:1.5b`, which is already installed on this machine and is better suited to limited memory:

```powershell
ollama pull qwen2.5:1.5b
ollama list
```

You also have `qwen2.5:7b` installed. It can be selected in `.env` if you have enough free memory; in a local API test it exceeded the 60-second response timeout on this machine. No Anthropic, Azure, or OpenAI key is needed for chat or browser speech.

## Free speech and vision options

- **Chat:** local Qwen through Ollama.
- **Text to speech:** browser `speechSynthesis`; voice choices are shown in the picker when the browser provides them. The specific `ar-TN-ReemNeural` voice is not guaranteed by browser speech. The optional `edge-tts` internet service can be enabled with `DAFTER_TTS_MODE=edge`, but it is unofficial, can return HTTP 403, and is not required.
- **Speech recognition:** browser speech recognition when supported. To record and transcribe on the server instead, install `faster-whisper`; its model is downloaded locally. Browser recognition availability varies by browser/device.
- **Image verification:** install a vision-capable Ollama model (for example `ollama pull qwen2.5vl:3b`) and set `OLLAMA_VISION_MODEL=qwen2.5vl:3b`. Plain `qwen2.5:7b` is not a vision model. Without a verifier, Dafter explicitly marks photos unverified and blocks certificate issuance rather than claiming that a photo matches.
- **Pricing:** no real-time market data source is configured. Dafter reports that fact and asks the farmer for her desired price; it does not invent an estimate.

The app requests location after the start-button tap. If permission is granted, it uses OpenStreetMap Nominatim reverse geocoding. If not, it asks for a location by voice/text.

## Environment

Copy `.env.example` to `.env` to change Ollama, speech, or optional-provider settings. `DAFTER_SECRET` can remain blank: Dafter generates a random signing secret and saves it to `.env` when the first certificate is requested. Keep `.env` private. Set `DAFTER_BASE_URL` to a public HTTPS URL before publishing certificate links; the default is local-only.

## Run tests

From `dafter`:

```powershell
python -m pytest -q
```

## HTTP smoke tests

With the server running at `http://127.0.0.1:8000`, use `curl.exe` on Windows:

```powershell
curl.exe -i http://127.0.0.1:8000/
curl.exe -i http://127.0.0.1:8000/api/status
curl.exe -i http://127.0.0.1:8000/api/tts/health
curl.exe -i -X POST http://127.0.0.1:8000/api/tts -H "Content-Type: application/json" -d "{\"text\":\"مرحبا بيك\",\"rate\":1}"
curl.exe -i -X POST http://127.0.0.1:8000/api/log -H "Content-Type: application/json" -d "{\"transcript\":\"Andi zouz gajouet tmatem b 9adeh nbi3hom\"}"
curl.exe -i -X POST http://127.0.0.1:8000/api/transcribe -F "file=@recording.webm"
```

`/api/tts` returns audio bytes on success and a JSON error with a non-2xx status on failure. In browser-speech mode, the UI speaks through the device instead of requiring a paid speech API. Ollama errors and the configured model are visible from `/api/status` and server logs.

## Manual scenario checklist

1. Double-click `run.bat`; verify the page is served by FastAPI at `http://127.0.0.1:8000`, not opened as a `file://` URL. Tap **اضغط باش نبداو**, allow location if desired, and check the greeting appears in Franco-Arabic and Arabic and is spoken. Confirm the selected voice is one actually offered by the browser.
2. Record **“Andi zouz gajouet tmatem b 9adeh nbi3hom”**, or enter it in the text box. Verify it extracts 2 crates of tomatoes. Browser STT itself depends on browser support; the exact text entry also tests extraction independently.
3. Check that the paper resume displays the product and quantity, uses the detected location when available, and says no verified market estimate is configured. Confirm no made-up TND amount is spoken.
4. Answer each requested field in turn: location, product variety/quality, harvest date, and expected price. Verify only one missing field is asked about at a time.
5. Upload/take a real product photo. With `OLLAMA_VISION_MODEL` configured, verify that a matching product can pass and a mismatch is rejected. Without it, verify the photo is clearly marked unverified and certificate issuance remains blocked.
6. After all required fields and a verified photo are present, issue a certificate; check its QR/link and buyer page include the product, quantity, price expectation, location, date, and image. Confirm the spoken completion in the browser.
7. Test the voice picker, speed slider, continuous mode, and stop button. Browser voice and speech-recognition availability varies by device.
