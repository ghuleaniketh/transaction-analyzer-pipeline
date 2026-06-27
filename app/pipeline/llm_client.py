import json

from app.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            from google import genai
        except ModuleNotFoundError as exc:
            raise RuntimeError("google-genai is required for LLM operations") from exc

        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client

VALID_CATEGORIES = [
    "Food", "Shopping", "Travel", "Transport",
    "Utilities", "Cash Withdrawal", "Entertainment", "Other",
]


def classify_batch(rows: list[dict]) -> dict[str, str]:
    """
    Takes a list of transaction rows missing a category, sends them to Gemini
    in a single batched call, and returns a dict mapping txn_id -> category.
    Rows with a blank/missing txn_id are skipped (can't map the result back).
    Raises an exception on API failure or malformed response — retry.py wraps
    this call with backoff, so this function itself stays simple and just fails loudly.
    """
    if not rows:
        return {}

    items = [
        {"index": i, "merchant": row.get("merchant", ""), "amount": row.get("amount")}
        for i, row in enumerate(rows)
    ]

    prompt = f"""Classify each transaction below into exactly one category from this list:
{", ".join(VALID_CATEGORIES)}

Transactions (JSON array, each with an "index"):
{json.dumps(items)}

Respond with ONLY a JSON array of objects, one per transaction, covering EVERY index
from 0 to {len(items) - 1} with no gaps and no omissions, like:
[{{"index": 0, "category": "Food"}}, ...]
No other text, no markdown formatting, just the raw JSON array.
"""

    client = _get_client()
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
    )

    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`").lstrip("json").strip()

    parsed = json.loads(raw_text)

    index_to_category = {item["index"]: item["category"] for item in parsed}

    result = {}
    for i, row in enumerate(rows):
        txn_id = row.get("txn_id")
        if txn_id and i in index_to_category:
            result[txn_id] = index_to_category[i]

    return result

def generate_summary(rows: list[dict], anomaly_count: int) -> dict:
    """
    Makes a single LLM call to produce a structured narrative summary of the
    full cleaned dataset. Returns a dict with total_spend_by_currency,
    top_merchants, anomaly_count, narrative, and risk_level.
    Raises on API failure or malformed response — caller wraps with retry_with_backoff.
    """
    # Pre-compute the hard numbers ourselves rather than asking the LLM to do arithmetic —
    # LLMs are unreliable at precise sums; we give it the facts and ask it to narrate them.
    spend_by_currency: dict[str, float] = {}
    spend_by_merchant: dict[str, float] = {}

    for row in rows:
        currency = row.get("currency")
        amount = row.get("amount")
        merchant = row.get("merchant")
        if currency and amount is not None:
            spend_by_currency[currency] = spend_by_currency.get(currency, 0) + amount
        if merchant and amount is not None:
            spend_by_merchant[merchant] = spend_by_merchant.get(merchant, 0) + amount

    top_merchants = sorted(spend_by_merchant.items(), key=lambda x: x[1], reverse=True)[:3]

    prompt = f"""Given this financial transaction summary data:
- Total spend by currency: {json.dumps(spend_by_currency)}
- Top merchants by spend: {json.dumps(top_merchants)}
- Number of flagged anomalies: {anomaly_count}
- Total transactions: {len(rows)}

Write a JSON object with exactly these fields:
- "narrative": a 2-3 sentence plain-English summary of the spending patterns
- "risk_level": one of "low", "medium", "high" based on the anomaly count relative to total transactions

Respond with ONLY the raw JSON object, no markdown, no other text.
"""

    client = _get_client()
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
    )

    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`").lstrip("json").strip()

    llm_part = json.loads(raw_text)

    return {
        "total_spend_by_currency": spend_by_currency,
        "top_merchants": [{"merchant": m, "total": round(t, 2)} for m, t in top_merchants],
        "anomaly_count": anomaly_count,
        "narrative": llm_part.get("narrative"),
        "risk_level": llm_part.get("risk_level"),
    }