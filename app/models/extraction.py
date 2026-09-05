from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, JSON, Float, UUID as PGUUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class DocumentTextExtraction(Base):
    __tablename__ = "document_text_extractions"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    extraction_method = Column(String(50), nullable=False)  # native_pdf, ocr_tesseract, etc.
    raw_text = Column(Text, nullable=True)
    normalized_text = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)  # OCR confidence, NULL for native extraction
    language = Column(String(10), nullable=True)  # e.g., 'eng', 'fra'
    extraction_metadata = Column(JSON, nullable=True)  # Additional extraction signals
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Ensure unique extraction per document, page, and method (for idempotency)
    __table_args__ = (
        # Unique constraint on document_id, page_number, and extraction_method
        # Note: We'll rely on application-level idempotency for simplicity, but we can add a unique constraint if needed.
        {},
    )

    def __repr__(self):
        return f"<DocumentTextExtraction(document_id={self.document_id}, page_number={self.page_number}, method={self.extraction_method})>"