"""
Pydantic schemas for text extraction results.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class ExtractionBase(BaseModel):
    document_id: str = Field(..., max_length=36)
    page_number: int = Field(..., gt=0)
    extraction_method: str = Field(..., max_length=50)  # native_pdf, ocr_tesseract, etc.
    raw_text: Optional[str] = None
    normalized_text: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=100.0)  # OCR confidence, NULL for native extraction
    language: Optional[str] = Field(None, max_length=10)  # e.g., 'eng', 'fra'
    extraction_metadata: Optional[Dict[str, Any]] = None


class ExtractionCreate(ExtractionBase):
    pass


class ExtractionResponse(ExtractionBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExtractionResult(BaseModel):
    document_id: str
    status: str
    page_count: int
    extractions: List[ExtractionResponse]


class ExtractionSummary(BaseModel):
    document_id: str
    status: str
    page_count: int
    total_characters: int
    total_words: int
    extraction_methods: Dict[str, int]  # Count of pages by extraction method