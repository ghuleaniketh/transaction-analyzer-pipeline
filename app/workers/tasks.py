from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.job import Job
from app.models.transaction import Transaction
from app.models.job_summary import JobSummary
from app.pipeline.pipeline_runner import run_pipeline


def process_job(job_id: str, csv_content: str):
    """
    Real worker task: runs the full pipeline on the uploaded CSV, persists
    cleaned Transaction rows and a JobSummary, and updates the Job's status.
    LLM-level failures are already handled inside run_pipeline (rows fall back
    to 'Uncategorised', summary falls back to a minimal default) — this function
    only needs to handle truly unrecoverable failures, e.g. an unparseable CSV.
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is None:
            return

        job.status = "processing"
        db.commit()

        result = run_pipeline(csv_content)

        for row in result["transactions"]:
            transaction = Transaction(
                job_id=job.id,
                txn_id=row.get("txn_id"),
                date=row.get("date"),
                merchant=row.get("merchant"),
                amount=row.get("amount"),
                currency=row.get("currency"),
                status=row.get("status"),
                category=row.get("category"),
                account_id=row.get("account_id"),
                notes=row.get("notes"),
                is_anomaly=row.get("is_anomaly", False),
                anomaly_reason=row.get("anomaly_reason"),
                llm_category=row.get("category") if not row.get("llm_failed") else None,
                llm_failed=row.get("llm_failed", False),
            )
            db.add(transaction)

        summary_data = result["summary"]
        job_summary = JobSummary(
            job_id=job.id,
            total_spend_inr=summary_data["total_spend_by_currency"].get("INR"),
            total_spend_usd=summary_data["total_spend_by_currency"].get("USD"),
            top_merchants=summary_data["top_merchants"],
            anomaly_count=summary_data["anomaly_count"],
            narrative=summary_data["narrative"],
            risk_level=summary_data["risk_level"],
        )
        db.add(job_summary)

        job.row_count_raw = result["row_count_raw"]
        job.row_count_clean = result["row_count_clean"]
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is not None:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
        raise

    finally:
        db.close()