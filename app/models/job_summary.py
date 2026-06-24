import uuid
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.models.base import Base


class JobSummary(Base):
    __tablename__ = "job_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, unique=True)

    total_spend_inr = Column(Numeric(14, 2), nullable=True)
    total_spend_usd = Column(Numeric(14, 2), nullable=True)

    top_merchants = Column(JSONB, nullable=True)   
    anomaly_count = Column(Integer, nullable=True)
    narrative = Column(Text, nullable=True)
    risk_level = Column(String, nullable=True)     