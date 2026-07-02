import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.job import Job
from app.models.transaction import Transaction
from app.models.job_summary import JobSummary
from typing import Optional

from app.schemas.job import (
    JobUploadResponse,
    JobStatusResponse,
    JobResultsResponse,
    JobListItem,
)
from app.redis_conn import queue
from app.workers.tasks import process_job


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/upload", response_model=JobUploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    print("upload_csv called with file:", file.filename)
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw_bytes = await file.read()
    try:
        csv_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")

    if not csv_content.strip():
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")

    job = Job(
        id=uuid.uuid4(),
        filename=file.filename,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    queue.enqueue(process_job, str(job.id), csv_content)

    return JobUploadResponse(job_id=job.id, status=job.status)


@router.get("/", response_model=list[JobListItem])
def list_jobs(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Job).order_by(Job.created_at.desc())
    if status is not None:
        query = query.filter(Job.status == status)
    jobs = query.all()

    return [
        JobListItem(
            job_id=j.id,
            status=j.status,
            filename=j.filename,
            created_at=j.created_at,
        )
        for j in jobs
    ]


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    summary = None
    if job.status == "completed":
        summary = {
            "row_count_raw": job.row_count_raw,
            "row_count_clean": job.row_count_clean,
        }

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        filename=job.filename,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        summary=summary,
    )


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed yet (current status: {job.status})",
        )

    transactions = db.query(Transaction).filter(Transaction.job_id == job.id).all()

    transactions_out = [
        {
            "id": str(t.id),
            "txn_id": t.txn_id,
            "date": t.date.isoformat() if t.date else None,
            "merchant": t.merchant,
            "amount": float(t.amount) if t.amount is not None else None,
            "currency": t.currency,
            "status": t.status,
            "category": t.category,
            "account_id": t.account_id,
            "notes": t.notes,
            "is_anomaly": t.is_anomaly,
            "anomaly_reason": t.anomaly_reason,
            "llm_category": t.llm_category,
            "llm_failed": t.llm_failed,
        }
        for t in transactions
    ]

    anomalies_out = [t for t in transactions_out if t["is_anomaly"]]

    breakdown = {}
    for t in transactions_out:
        cat = t["category"] or "Uncategorised"
        entry = breakdown.setdefault(cat, {"total_amount": 0.0, "count": 0})
        if t["amount"] is not None:
            entry["total_amount"] += t["amount"]
        entry["count"] += 1

    category_breakdown = sorted(
        [
            {"category": cat, "total_amount": round(data["total_amount"], 2), "count": data["count"]}
            for cat, data in breakdown.items()
        ],
         key=lambda c: c["total_amount"],
        reverse=True,
    )

    summary = db.query(JobSummary).filter(JobSummary.job_id == job.id).first()
    summary_out = None
    if summary is not None:
        summary_out = {
            "total_spend_inr": float(summary.total_spend_inr) if summary.total_spend_inr is not None else None,
            "total_spend_usd": float(summary.total_spend_usd) if summary.total_spend_usd is not None else None,
            "top_merchants": summary.top_merchants,
            "anomaly_count": summary.anomaly_count,
            "narrative": summary.narrative,
            "risk_level": summary.risk_level,
        }

    return {
        "job_id": str(job.id),
        "status": job.status,
        "transactions": transactions_out,
        "anomalies": anomalies_out,
        "category_breakdown": category_breakdown,
        "summary": summary_out,
    }