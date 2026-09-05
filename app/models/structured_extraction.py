"""
Database models for structured table and chart extraction results.
"""

from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, JSON, Float, Boolean, UUID as PGUUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class DocumentTableExtraction(Base):
    """
    Stores structured table extraction results.
    Each record represents one extracted table from a document page.
    """
    __tablename__ = "document_table_extractions"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    table_index = Column(Integer, nullable=False)  # Index of table on the page (0-based)

    # Extraction metadata
    extraction_method = Column(String(50), nullable=False)  # opencv_plus_ocr, etc.
    row_count = Column(Integer, nullable=False)
    column_count = Column(Integer, nullable=False)

    # Structured data storage
    # We'll store the table data as JSON array of arrays: [["cell11", "cell12"], ["cell21", "cell22"]]
    table_data = Column(JSON, nullable=False)

    # Cell-level metadata (optional)
    cell_metadata = Column(JSON, nullable=True)  # Detailed info per cell if needed

    # Confidence and quality metrics
    extraction_confidence = Column(Float, nullable=True)  # Overall confidence 0-1
    structure_confidence = Column(Float, nullable=True)   # Confidence in table structure

    # Traceability
    source_artifact_reference = Column(Text, nullable=True)  # Reference to preprocessing artifact
    extraction_metadata = Column(JSON, nullable=True)  # Additional extraction signals

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Ensure unique extraction per document, page, and table index (for idempotency)
    __table_args__ = (
        # Note: We'll rely on application-level idempotency for simplicity
        {},
    )

    def __repr__(self):
        return f"<DocumentTableExtraction(document_id={self.document_id}, page_number={self.page_number}, table_index={self.table_index}, rows={self.row_count}, cols={self.column_count})>"


class DocumentChartAssociation(Base):
    """
    Stores associations between charts and extracted tables.
    When a chart is resolved through a table, this record captures that relationship.
    """
    __tablename__ = "document_chart_associations"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PGUUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    chart_index = Column(Integer, nullable=False)  # Index of chart on the page

    # Association details
    associated_table_id = Column(PGUUID(as_uuid=True), ForeignKey("document_table_extractions.id"), nullable=True)
    association_method = Column(String(50), nullable=False)  # same_page, adjacent_page, etc.
    association_confidence = Column(Float, nullable=False)  # 0-1 confidence in association

    # Chart metadata (preserved from visual extraction)
    chart_metadata = Column(JSON, nullable=True)  # Original chart region/data

    # Resolution status
    resolution_status = Column(String(30), nullable=False)  # resolved, unresolved, partial

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    def __repr__(self):
        return f"<DocumentChartAssociation(document_id={self.document_id}, page_number={self.page_number}, chart_index={self.chart_index}, associated_table_id={self.associated_table_id})>"