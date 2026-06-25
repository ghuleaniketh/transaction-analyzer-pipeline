from collections import defaultdict
from statistics import median

DOMESTIC_ONLY_MERCHANTS = {
    "Swiggy", "Ola", "IRCTC", "MakeMyTrip", "Zomato", "BookMyShow",
}

def detect_statistical_outliers(rows: list[dict]) -> list[dict]:
    """
    Flags rows where 'amount' exceeds 3x the median amount for that row's account_id.
    Expects rows where 'amount' is already a float (post-cleaning) and 'account_id' is set.
    Returns the same rows, with 'is_anomaly' and 'anomaly_reason' added/updated in place
    for any row that trips the outlier check. Rows already flagged by another check
    keep their existing flag (this function only adds, never removes, a flag).
    """
    # Group amounts by account to compute each account's median.
    amounts_by_account = defaultdict(list)
    for row in rows:
        if row.get("amount") is not None and row.get("account_id"):
            amounts_by_account[row["account_id"]].append(row["amount"])

    medians = {
        account_id: median(amounts)
        for account_id, amounts in amounts_by_account.items()
    }

    for row in rows:
        account_id = row.get("account_id")
        amount = row.get("amount")

        if account_id not in medians or amount is None:
            continue

        threshold = medians[account_id] * 3
        if amount > threshold:
            row["is_anomaly"] = True
            existing_reason = row.get("anomaly_reason")
            row["anomaly_reason"] = (
                "statistical_outlier" if not existing_reason
                else f"{existing_reason},statistical_outlier"
            )

    return rows

def detect_currency_mismatch(rows: list[dict]) -> list[dict]:
    """
    Flags rows where currency is USD but the merchant is a domestic-only brand
    (one that wouldn't realistically bill in USD). Mutates and returns the same
    rows, same accumulation pattern as detect_statistical_outliers.
    """
    for row in rows:
        currency = row.get("currency")
        merchant = row.get("merchant")

        if currency == "USD" and merchant in DOMESTIC_ONLY_MERCHANTS:
            row["is_anomaly"] = True
            existing_reason = row.get("anomaly_reason")
            row["anomaly_reason"] = (
                "currency_mismatch" if not existing_reason
                else f"{existing_reason},currency_mismatch"
            )

    return rows