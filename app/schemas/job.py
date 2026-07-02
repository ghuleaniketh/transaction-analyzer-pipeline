from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from datetime import datetime


class JobUploadResponse(BaseModel):
    job_id: UUID
    status: str


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    summary: Optional[dict] = None  


class JobListItem(BaseModel):
    job_id: UUID
    status: str
    filename: str
    created_at: datetime


class TransactionOut(BaseModel):
    id: UUID
    txn_id: Optional[str] = None
    date: Optional[str] = None  # ISO 8601 string
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    llm_category: Optional[str] = None
    llm_failed: bool


class CategoryBreakdown(BaseModel):
    category: str
    total_amount: float
    count: int


class JobSummaryOut(BaseModel):
    total_spend_inr: Optional[float] = None
    total_spend_usd: Optional[float] = None
    top_merchants: Optional[list] = None
    anomaly_count: Optional[int] = None
    narrative: Optional[str] = None
    risk_level: Optional[str] = None


class JobResultsResponse(BaseModel):
    job_id: UUID
    status: str
    transactions: list[TransactionOut]
    anomalies: list[TransactionOut]
    category_breakdown: list[CategoryBreakdown]
    summary: Optional[JobSummaryOut] = None