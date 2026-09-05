from sqlalchemy import Column, String, DateTime, BigInteger, Text, UUID as PGUUID, Integer, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.sql import func
from uuid import UUID, uuid4
from app.core.database import Base
import datetime
import uuid


class Document(Base):
    __tablename__ = "documents"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    checksum_sha256 = Column(String(64), nullable=False, unique=True, index=True)
    source_type = Column(String(50), nullable=False)
    source_identifier = Column(String(255), nullable=True)
    subsidiary = Column(String(100), nullable=True)
    document_timestamp = Column(DateTime(timezone=True), nullable=True)
    storage_reference = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="ingested")
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    def __repr__(self):
        return f"<Document(id={self.id}, original_filename='{self.original_filename}', status='{self.status}')>"


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id"),
        nullable=False,
        index=True
    )
    page_number = Column(Integer, nullable=False)

    classification = Column(String(50), nullable=False)
    classification_confidence = Column(String(20), nullable=False)
    classification_reason = Column(Text, nullable=False)
    text_length = Column(Integer, nullable=False)
    image_count = Column(Integer, nullable=False)
    drawing_count = Column(Integer, nullable=False)
    analysis_metadata = Column(JSON, nullable=True)
    preprocessed_image_reference = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "page_number",
            name="uq_document_page_number"
        ),
    )

    def __repr__(self):
        return f"<DocumentPage(document_id={self.document_id}, page_number={self.page_number})>"