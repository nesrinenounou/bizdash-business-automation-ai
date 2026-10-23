"""Summarise + classify a customer message.
Uses the Anthropic API when ANTHROPIC_API_KEY is set, otherwise a keyword fallback."""
import json, logging, os, re
import httpx

log = logging.getLogger("ai")
CATEGORIES = ["complaint", "billing", "support", "sales", "other"]
KEYWORDS = {
    "complaint": ["problème", "probleme","problem", "retard", "cassé", "mauvais", "refund", "late", "broken", "complaint", "مشكل", "تأخر"],
    "billing": ["facture", "paiement", "invoice", "payment", "charge", "فاتورة", "دفع"],
    "support": ["aide", "help", "bug", "erreur", "error", "how do", "comment", "مساعدة"],
    "sales": ["prix", "devis", "tarif", "price", "quote", "buy", "acheter", "سعر"],
}
URGENT = ["urgent", "asap", "immédiatement", "immediately", "now", "عاجل"]


def _fallback(message: str) -> dict:
    low = message.lower()
    category = next((c for c, ws in KEYWORDS.items() if any(w in low for w in ws)), "other")
    priority = "high" if any(w in low for w in URGENT) or category == "complaint" else "normal"
    first = re.split(r"(?<=[.!?؟])\s", message.strip())[0]
    return {"summary": first[:160], "category": category, "priority": priority}


def analyze(message: str) -> dict:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return _fallback(message)
    prompt = (
        "Summarise this customer message in one short sentence (same language) and classify it. "
        f"Reply ONLY with JSON: {{\"summary\": str, \"category\": one of {CATEGORIES}, \"priority\": \"high\"|\"normal\"}}.\n\n"
        f"Message:\n{message}"
    )
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.getenv("AI_MODEL", "claude-sonnet-4-6"), "max_tokens": 300,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=20,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        if data.get("category") not in CATEGORIES:
            data["category"] = "other"
        data["priority"] = "high" if data.get("priority") == "high" else "normal"
        return {k: str(data[k]) for k in ("summary", "category", "priority")}
    except Exception as exc:  # never block an order because the AI is down
        log.warning("AI call failed, using fallback: %s", exc)
        return _fallback(message)
