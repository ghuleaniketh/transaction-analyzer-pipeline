from datetime import datetime
import uuid


def normalize_date(raw_date: str) -> str | None:
    """
    Converts a date string in one of three known formats into ISO 8601 (YYYY-MM-DD):
      - DD-MM-YYYY   (dash-separated, day first)   e.g. "04-09-2024" -> "2024-09-04"
      - YYYY/MM/DD   (slash-separated, year first)  e.g. "2024/02/05" -> "2024-02-05"
      - YYYY-MM-DD   (dash-separated, year first)   e.g. "2024-07-15" -> already ISO, no-op
    Returns None if the input is empty or doesn't match any known format.
    """
    raw_date = raw_date.strip()
    if not raw_date:
        return None

    # YYYY-MM-DD: dash-separated, first segment is 4 digits -> already ISO.
    if "-" in raw_date and len(raw_date.split("-")[0]) == 4:
        return raw_date

    # DD-MM-YYYY: dash-separated, first segment is day (1-2 digits).
    if "-" in raw_date:
        dt = datetime.strptime(raw_date, "%d-%m-%Y")
        return dt.strftime("%Y-%m-%d")

    # YYYY/MM/DD: slash-separated, year first.
    if "/" in raw_date:
        dt = datetime.strptime(raw_date, "%Y/%m/%d")
        return dt.strftime("%Y-%m-%d")

    return None

def strip_currency_symbol(raw_amount: str) -> float | None:
    """
    Removes currency symbols and whitespace from an amount string, returns a float.
    Handles "$11325.79" -> 11325.79, "10882.55" -> 10882.55 (no-op).
    Returns None if the value can't be parsed as a number.
    """
    if not raw_amount:
        return None

    cleaned = raw_amount.strip().replace("$", "").replace(",", "").strip()

    try:
        return float(cleaned)
    except ValueError:
        return None

def normalize_status(raw_status: str) -> str | None:
    """Uppercases status values: 'success' -> 'SUCCESS'."""
    if not raw_status:
        return None
    return raw_status.strip().upper()


def normalize_currency(raw_currency: str) -> str | None:
    """Uppercases currency values: 'inr' -> 'INR'."""
    if not raw_currency:
        return None
    return raw_currency.strip().upper()


def fill_missing_category(raw_category: str) -> str:
    """Returns the category as-is if present, otherwise 'Uncategorised'."""
    if not raw_category or not raw_category.strip():
        return "Uncategorised"
    return raw_category.strip()

def remove_exact_duplicates(rows: list[dict]) -> list[dict]:
    """
    Removes rows that are exact duplicates based on transaction content
    (txn_id, date, merchant, amount, currency, status, category, account_id).
    Deliberately excludes 'notes' from the comparison — notes is free-text
    commentary, not part of transaction identity, and shouldn't drive dedup logic.
    Keeps the first occurrence of each duplicate set.
    """
    seen = set()
    result = []

    dedup_fields = ["txn_id", "date", "merchant", "amount", "currency", "status", "category", "account_id"]

    for row in rows:
        key = tuple(row.get(field) for field in dedup_fields)
        if key not in seen:
            seen.add(key)
            result.append(row)

    return result


def fill_missing_txn_id(rows: list[dict]) -> list[dict]:
    """
    Generates a synthetic txn_id for any row where the source txn_id was blank,
    so every row has a stable identifier to map results back to throughout
    the rest of the pipeline (anomaly detection, LLM classification, storage).
    Synthetic IDs are prefixed so they're visually distinguishable from real ones.
    """
    for row in rows:
        if not row.get("txn_id") or not row["txn_id"].strip():
            row["txn_id"] = f"GENERATED-{uuid.uuid4().hex[:8].upper()}"
    return rows