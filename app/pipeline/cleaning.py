from datetime import datetime
import uuid


def normalize_date(raw_date: str) -> str | None:
    
    raw_date = raw_date.strip()
    if not raw_date:
        return None

    if "-" in raw_date and len(raw_date.split("-")[0]) == 4:
        return raw_date

    if "-" in raw_date:
        try:
            dt = datetime.strptime(raw_date, "%d-%m-%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    if "/" in raw_date:
        try:
            dt = datetime.strptime(raw_date, "%Y/%m/%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    return None



def strip_currency_symbol(raw_amount: str) -> float | None:
    
    if not raw_amount:
        return None

    cleaned = raw_amount.strip().replace("$", "").replace(",", "").strip()

    try:
        return float(cleaned)
    except ValueError:
        return None



def normalize_status(raw_status: str) -> str | None:
    if not raw_status:
        return None
    return raw_status.strip().upper()




def normalize_currency(raw_currency: str) -> str | None:
    
    if not raw_currency:
        return None
    return raw_currency.strip().upper()




def fill_missing_category(raw_category: str) -> str:
    if not raw_category or not raw_category.strip():
        return "Uncategorised"
    return raw_category.strip()



def remove_exact_duplicates(rows: list[dict]) -> list[dict]:
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
    for row in rows:
        if not row.get("txn_id") or not row["txn_id"].strip():
            row["txn_id"] = f"GENERATED-{uuid.uuid4().hex[:8].upper()}"
    return rows