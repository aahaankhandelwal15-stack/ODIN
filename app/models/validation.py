"""
Database models for validation results.
"""

from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, JSON, Float, Boolean, UUID as PGUUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class ValidationRun(Base):
    """
    Stores validation execution records.
    Each record represents one validation execution for a document.
    """
    __tablename__ = "validation_runs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    status = Column(String(50), nullable=False)  # pending, validating, completed, failed
    overall_quality_score = Column(Float, nullable=True)  # 0-100
    final_decision = Column(String(20), nullable=True)  # approved, flagged, failed
    config_snapshot = Column(JSON, nullable=True)  # Configuration used for this validation
    input_hash = Column(String(64), nullable=True)  # Hash of input data for idempotency
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    def __repr__(self):
        return f"<ValidationRun(document_id={self.document_id}, status={self.status}, score={self.overall_quality_score}, decision={self.final_decision})>"


class ValidationFinding(Base):
    """
    Stores individual validation findings.
    Each record represents one validation check performed during a validation run.
    """
    __tablename__ = "validation_findings"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    validation_run_id = Column(PGUUID(as_uuid=True), ForeignKey("validation_runs.id"), nullable=False, index=True)
    validator = Column(String(50), nullable=False)  # schema, table, numeric_consistency, etc.
    check_name = Column(String(100), nullable=False)  # Specific check performed
    status = Column(String(20), nullable=False)  # passed, failed, skipped, error
    severity = Column(String(20), nullable=False)  # info, warning, error, critical
    message = Column(Text, nullable=False)  # Human-readable description
    page_number = Column(Integer, nullable=True)  # Associated page number if applicable
    table_reference = Column(String(36), nullable=True)  # Reference to table extraction if applicable
    details = Column(JSON, nullable=True)  # Additional details about the check
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<ValidationRun(id={self.validation_run_id}, validator={self.validator}, check={self.check_name}, status={self.status})>"