import uuid
from sqlalchemy import Column, String, Numeric, Boolean, ForeignKey, Date, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)

    txn_id = Column(String, nullable=True)       # some source rows have this blank
    date = Column(Date, nullable=True)            # normalized to ISO 8601
    merchant = Column(String, nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String, nullable=True)
    status = Column(String, nullable=True)
    category = Column(String, nullable=True)
    account_id = Column(String, nullable=True)

    is_anomaly = Column(Boolean, nullable=False, default=False)
    anomaly_reason = Column(String, nullable=True)   # e.g. "statistical_outlier", "currency_mismatch"

    llm_category = Column(String, nullable=True)
    llm_raw_response = Column(Text, nullable=True)
    llm_failed = Column(Boolean, nullable=False, default=False)