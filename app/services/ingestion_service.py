import hashlib
import uuid
from typing import BinaryIO, Optional
from datetime import datetime
from app.utils.checksum import calculate_sha256
from app.storage.factory import get_storage_backend
from app.services.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate, IngestionResult
from app.core.config import get_settings
from app.core.database import get_async_session_local
import logging

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self):
        self.settings = get_settings()
        self.storage_backend = get_storage_backend()

    async def ingest_document(
        self,
        file_data: BinaryIO,
        original_filename: str,
        content_type: str,
        source_type: str = "manual_upload",
        source_identifier: Optional[str] = None,
        subsidiary: Optional[str] = None,
        document_timestamp: Optional[datetime] = None,
    ) -> IngestionResult:
        """
        Main document ingestion method following the Phase 1 lifecycle:
        1. Validate input
        2. Read original file bytes and calculate SHA-256 checksum
        3. Check for duplicate by checksum
        4. If duplicate: return existing document information
        5. If new:
           a. Store immutable original document
           b. Create metadata and provenance
           c. Persist metadata
        6. Return ingestion result
        """
        # Create a new database session for this operation
        async with get_async_session_local()() as session:
            repository = DocumentRepository(session)

            try:
                # 1. Validate input
                if not original_filename:
                    raise ValueError("Original filename is required")
                if not content_type:
                    raise ValueError("Content type is required")
                if not source_type:
                    raise ValueError("Source type is required")

                # Reset file pointer to beginning for reading
                if hasattr(file_data, "seek"):
                    file_data.seek(0)

                # 2. Calculate SHA-256 checksum from original bytes
                checksum_sha256 = calculate_sha256(file_data)
                logger.info(f"Calculated SHA-256 checksum: {checksum_sha256}")

                # Get file size
                if hasattr(file_data, "seek"):
                    file_data.seek(0, 2)  # Seek to end
                    file_size = file_data.tell()
                    file_data.seek(0)  # Reset to beginning for storage
                else:
                    # If not seekable, we need to read everything to get size
                    # This is less efficient but necessary for some file-like objects
                    contents = await file_data.read()
                    file_size = len(contents)
                    # Reset for storage - recreate the binary stream
                    from io import BytesIO
                    file_data = BytesIO(contents)

                # 3. Check for duplicate by checksum
                existing_document = await repository.get_by_checksum(checksum_sha256)
                if existing_document:
                    logger.info(f"Duplicate document found with ID: {existing_document.id}")
                    # Return existing document information
                    return IngestionResult(
                        document_id=str(existing_document.id),
                        original_filename=existing_document.original_filename,
                        content_type=existing_document.content_type,
                        file_size=existing_document.file_size,
                        checksum_sha256=existing_document.checksum_sha256,
                        source_type=existing_document.source_type,
                        source_identifier=existing_document.source_identifier,
                        subsidiary=existing_document.subsidiary,
                        ingested_at=existing_document.ingested_at,
                        document_timestamp=existing_document.document_timestamp,
                        storage_reference=existing_document.storage_reference,
                        status=existing_document.status,
                        is_duplicate=True,
                        message="Document already exists (duplicate)"
                    )

                # 4. If new: store immutable original document
                storage_reference = await self.storage_backend.store_file(
                    file_data=file_data,
                    file_path="",  # Not used for local storage, ignored for S3
                    content_type=content_type
                )
                logger.info(f"Stored document with storage reference: {storage_reference}")

                # 5. Create metadata and provenance
                document_data = DocumentCreate(
                    original_filename=original_filename,
                    content_type=content_type,
                    file_size=file_size,
                    checksum_sha256=checksum_sha256,
                    source_type=source_type,
                    source_identifier=source_identifier,
                    subsidiary=subsidiary,
                    document_timestamp=document_timestamp,
                    storage_reference=storage_reference,
                    status="ingested"
                )

                # Persist metadata
                document = await repository.create(document_data)
                logger.info(f"Created document record with ID: {document.id}")

                # 6. Return ingestion result
                return IngestionResult(
                    document_id=str(document.id),
                    original_filename=document.original_filename,
                    content_type=document.content_type,
                    file_size=document.file_size,
                    checksum_sha256=document.checksum_sha256,
                    source_type=document.source_type,
                    source_identifier=document.source_identifier,
                    subsidiary=document.subsidiary,
                    ingested_at=document.ingested_at,
                    document_timestamp=document.document_timestamp,
                    storage_reference=document.storage_reference,
                    status=document.status,
                    is_duplicate=False,
                    message="Document successfully ingested"
                )

            except Exception as e:
                logger.error(f"Error during document ingestion: {e}")
                raise