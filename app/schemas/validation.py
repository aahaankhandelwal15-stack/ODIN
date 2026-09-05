"""
Pydantic schemas for validation results.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class ValidationRunBase(BaseModel):
    document_id: str = Field(..., max_length=36)
    status: str = Field(..., max_length=50)  # pending, validating, completed, failed
    overall_quality_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    final_decision: Optional[str] = Field(None, max_length=20)  # approved, flagged, failed
    config_snapshot: Optional[Dict[str, Any]] = None
    input_hash: Optional[str] = Field(None, max_length=64)


class ValidationRunCreate(ValidationRunBase):
    pass


class ValidationRunResponse(ValidationRunBase):
    id: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ValidationFindingBase(BaseModel):
    validation_run_id: str = Field(..., max_length=36)
    validator: str = Field(..., max_length=50)
    check_name: str = Field(..., max_length=100)
    status: str = Field(..., max_length=20)  # passed, failed, skipped, error
    severity: str = Field(..., max_length=20)  # info, warning, error, critical
    message: str = Field(...)  # Human-readable description
    page_number: Optional[int] = None
    table_reference: Optional[str] = Field(None, max_length=36)
    details: Optional[Dict[str, Any]] = None


class ValidationFindingCreate(ValidationFindingBase):
    pass


class ValidationFindingResponse(ValidationFindingBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ValidationResult(BaseModel):
    document_id: str
    status: str
    overall_quality_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    final_decision: Optional[str] = None
    findings: List[ValidationFindingResponse] = []
    checks_run: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None


class ValidationSummary(BaseModel):
    document_id: str
    status: str
    overall_quality_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    final_decision: Optional[str] = None
    validation_run_id: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    findings_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0