from html import escape

CSS = """
:root{color-scheme:light;--ink:#39261d;--paper:#f7ecdb;--card:#fff9ef;--muted:#674b3c;--gold:#dda13b}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--ink:#fff1dc;--paper:#2a1c1b;--card:#38241f;--muted:#e4c4a4;--gold:#edb951}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.55 system-ui,sans-serif}
main{max-width:620px;margin:0 auto;padding:32px 20px 56px}.card{background:var(--card);border:1px solid #a7622240;border-radius:20px;padding:24px;box-shadow:0 12px 34px #43281622}
h1{font-size:clamp(1.7rem,6vw,2.5rem);margin:.2em 0}.muted{color:var(--muted)}
dl{display:grid;grid-template-columns:minmax(110px,auto) 1fr;gap:10px 18px;margin:24px 0}
dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere;font-weight:600}.price{border-radius:14px;background:var(--gold);padding:16px;margin-top:22px}
audio,img{width:100%;margin-top:8px}img{border-radius:14px;max-height:420px;object-fit:cover}.bad{border:2px solid #a83227;padding:22px;border-radius:14px}
"""


def _shell(inner: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Dafter product record</title>"
        f"<style>{CSS}</style></head><body><main>{inner}</main></body></html>"
    )


def render_buyer(payload, valid: bool) -> str:
    if not payload or not valid:
        return _shell(
            "<section class='bad'><h1>This record could not be verified</h1>"
            "<p>The signature does not match the data. The link may be damaged or altered.</p></section>"
        )

    fields = payload.get("fields")
    if not isinstance(fields, list):
        fields = [
            {"key": key, "value": payload[key]}
            for key in ("product", "quantity", "unit", "maker", "village", "variety", "harvest_date", "date")
            if payload.get(key) not in (None, "")
        ]
    rows = "".join(
        f"<dt>{escape(str(field.get('key', '')))}</dt><dd>{escape(str(field.get('value', '')))}</dd>"
        for field in fields
        if isinstance(field, dict) and field.get("value") is not None
    )
    story = (
        f"<p class='muted'>A voice note from the farmer</p>"
        f"<audio controls src='/api/pieces/{escape(str(payload.get('id', '')))}"
        "/story.audio'></audio>"
        if payload.get("story")
        else ""
    )
    price = payload.get("price")
    price_markup = ""
    if isinstance(price, dict):
        currency = escape(str(price.get("currency", "TND")))
        note = escape(str(price.get("note", "")))
        amount = price.get("amount")
        heading = (
            f"<strong>Farmer's price expectation: {escape(str(amount))} {currency}</strong><br>"
            if amount is not None else "<strong>No verified market-price estimate available</strong><br>"
        )
        price_markup = f"<div class='price'>{heading}{note}</div>"
    photo = (
        f"<img src='/api/pieces/{escape(str(payload.get('id', '')))}/photo' alt='Product photo'>"
        if payload.get("photo")
        else ""
    )

    return _shell(
        "<article class='card'>"
        f"<p class='muted'>Dafter product record · {escape(str(payload.get('id', '')))}</p>"
        f"<h1>{escape(str(payload.get('product', 'Product record')))}</h1>"
        f"<p>Recorded for {escape(str(payload.get('maker') or 'the farmer'))}</p>"
        f"<dl>{rows}</dl>{photo}{story}{price_markup}"
        "<p class='muted'>This record is signed. A signature confirms the data has not changed; "
        "it does not independently verify the information.</p></article>"
    )
