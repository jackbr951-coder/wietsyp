"""Represent farmer-reported prices without claiming to have market data."""


def price(data: dict) -> dict | None:
    amount = data.get("price_tnd")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
        return {
            "amount": None,
            "currency": "TND",
            "source": "unavailable",
            "note": "No verified live market-price source is configured; no estimate is available.",
        }
    return {
        "amount": round(float(amount), 2),
        "currency": "TND",
        "source": "farmer",
        "note": "Price expectation reported by the farmer; it is not a market estimate.",
    }


def verification(data: dict) -> dict:
    if data.get("vision", {}).get("verified") is True:
        return {"status": "photo_attached", "ratio": None}
    if data.get("photo"):
        return {"status": "photo_unverified", "ratio": None}
    return {"status": "self_reported", "ratio": None}
