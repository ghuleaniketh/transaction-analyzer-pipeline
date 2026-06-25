import json
from google import genai

from app.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

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