from app.pipeline.parser import parse_csv
from app.pipeline.cleaning import (
    remove_exact_duplicates,
    fill_missing_txn_id,
    normalize_date,
    strip_currency_symbol,
    normalize_status,
    normalize_currency,
    fill_missing_category,
)
from app.pipeline.anomaly import detect_statistical_outliers, detect_currency_mismatch
from app.pipeline.llm_client import classify_batch, generate_summary
from app.pipeline.retry import retry_with_backoff


def run_pipeline(csv_content: str) -> dict:
    rows = parse_csv(csv_content)
    row_count_raw = len(rows)

    rows = remove_exact_duplicates(rows)
    row_count_clean = len(rows)

    rows = fill_missing_txn_id(rows)

    for row in rows:
        row["date"] = normalize_date(row.get("date", ""))
        row["amount"] = strip_currency_symbol(row.get("amount", ""))
        row["status"] = normalize_status(row.get("status", ""))
        row["currency"] = normalize_currency(row.get("currency", ""))
        row["is_anomaly"] = False
        row["anomaly_reason"] = None
        row["llm_failed"] = False

    rows = detect_statistical_outliers(rows)
    rows = detect_currency_mismatch(rows)
    anomaly_count = sum(1 for r in rows if r["is_anomaly"])

    uncategorized = [r for r in rows if not (r.get("category") or "").strip()]

    if uncategorized:
        try:
            classifications = retry_with_backoff(classify_batch, uncategorized)
            for row in rows:
                txn_id = row.get("txn_id")
                if txn_id in classifications:
                    row["category"] = classifications[txn_id]
        except Exception:
            for row in uncategorized:
                row["llm_failed"] = True

    for row in rows:
        row["category"] = fill_missing_category(row.get("category", ""))

    # Narrative summary: single LLM call, retried. Falls back to a minimal
    # summary if the LLM is unavailable even after retries.
    try:
        summary = retry_with_backoff(generate_summary, rows, anomaly_count)
    except Exception:
        summary = {
            "total_spend_by_currency": {},
            "top_merchants": [],
            "anomaly_count": anomaly_count,
            "narrative": None,
            "risk_level": None,
        }

    return {
        "row_count_raw": row_count_raw,
        "row_count_clean": row_count_clean,
        "transactions": rows,
        "summary": summary,
    }