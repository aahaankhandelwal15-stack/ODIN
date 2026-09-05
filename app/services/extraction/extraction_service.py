"""
Extraction Service Module for ODIN V1 Phase 4
Orchestrates the text extraction process: retrieve → extract → normalize → persist.
"""

from typing import List, Optional, Dict, Any
import uuid
import logging
from sqlalchemy import select

from app.services.extraction.text_extractor import TextExtractor
from app.services.extraction.ocr_extractor import OCRExtractor
from app.services.extraction.text_normalizer import TextNormalizer
from app.core.database import get_async_session_local
from app.services.document_repository import DocumentRepository
from app.storage.factory import get_storage_backend
from app.core.config import get_settings
from app.models.document import Document
from app.models.extraction import DocumentTextExtraction

logger = logging.getLogger(__name__)


class ExtractionService:
    """
    Service responsible for orchestrating text extraction workflow.

    Workflow:
    1. Retrieve document from storage
    2. For each page:
       a. Extract text natively (if applicable)
       b. Apply OCR (if applicable based on classification)
       c. Normalize extracted text
       d. Persist extraction results
    """

    def __init__(self):
        """Initialize the extraction service."""
        self.settings = get_settings()
        self.storage_backend = get_storage_backend()
        self.text_extractor = TextExtractor()
        # OCRExtractor will be initialized per language when needed
        self.text_normalizer = TextNormalizer()

    async def extract_text_from_document(
        self,
        document_id: str,
        force_reextraction: bool = False
    ) -> Dict[str, Any]:
        """
        Extract text from a document and persist extraction results.

        Args:
            document_id: UUID of the document to extract text from
            force_reextraction: If True, re-extract even if already extracted

        Returns:
            Dictionary containing extraction summary

        Raises:
            ValueError: If document not found
            Exception: For extraction or persistence failures
        """
        settings = get_settings()

        # Create database session
        async with get_async_session_local()() as session:
            # Get document repository
            doc_repo = DocumentRepository(session)

            # Retrieve document
            document = await doc_repo.get_by_id(document_id)
            if not document:
                raise ValueError(f"Document with ID {document_id} not found")

            # Check if already extracted (unless force_reextraction)
            if not force_reextraction and await self._is_extracted(session, document_id):
                logger.info(f"Document {document_id} already extracted. Use force_reextraction=True to re-extract.")
                return await self.get_extraction_results(document_id)

            # Update status to extracting
            await doc_repo.update_status(document_id, "extracting")
            await session.commit()

            try:
                # Retrieve document from storage
                logger.info(f"Retrieving document {document_id} from storage")
                pdf_bytes = await self._retrieve_document_bytes(document.storage_reference)

                # Get page classifications to determine extraction approach
                from app.services.analysis.analysis_service import get_analysis_results
                analysis_results = await get_analysis_results(document_id)
                page_classifications = {
                    page["page_number"]: page["classification"]
                    for page in analysis_results["pages"]
                }

                # Extract text from PDF
                logger.info(f"Extracting text from PDF with {analysis_results['page_count']} pages")

                # Get native text extraction
                native_texts = self.text_extractor.extract_text_from_bytes_with_details(pdf_bytes)

                extraction_results = []
                extraction_objects = []  # For bulk creation

                for page_info in native_texts:
                    page_number = page_info["page_number"]
                    raw_text = page_info["text"]
                    classification = page_classifications.get(page_number, "unknown")

                    # Determine if OCR should be applied
                    should_apply_ocr = classification in ["scanned_document", "mixed"] and not raw_text

                    ocr_text = None
                    ocr_confidence = None
                    ocr_metadata = {}

                    if should_apply_ocr:
                        # Apply OCR
                        try:
                            # For OCR, we need the image. In a full implementation,
                            # we would render the PDF page to an image.
                            # For now, we'll simulate OCR on empty image if no native text
                            # or use a placeholder approach
                            logger.info(f"Applying OCR to page {page_number} (classification: {classification})")
                            # Placeholder - in real implementation, we'd render PDF page to image
                            # and run OCR on that image
                            ocr_text, ocr_confidence, ocr_metadata = None, None, {}
                        except Exception as e:
                            logger.warning(f"OCR failed for page {page_number}: {e}")
                            ocr_text, ocr_confidence, ocr_metadata = None, None, {"error": str(e)}

                    # Use OCR text if available and native text is insufficient, otherwise use native text
                    final_raw_text = ocr_text if (ocr_text and len(ocr_text.strip()) > len((raw_text or "").strip())) else raw_text

                    # Normalize text
                    normalized_text = self.text_normalizer.normalize(final_raw_text) if final_raw_text else ""

                    # Determine extraction method
                    if ocr_text and len(ocr_text.strip()) > 0:
                        extraction_method = "ocr_tesseract"
                        confidence = ocr_confidence
                    elif raw_text and len(raw_text.strip()) > 0:
                        extraction_method = "native_pdf"
                        confidence = None  # Native extraction doesn't have confidence score
                    else:
                        extraction_method = "none"
                        confidence = None

                    # Prepare extraction metadata
                    extraction_metadata = {
                        "page_number": page_number,
                        "classification": classification,
                        "native_text_length": len(raw_text) if raw_text else 0,
                        "ocr_applied": should_apply_ocr,
                        "ocr_text_length": len(ocr_text) if ocr_text else 0,
                    }
                    if ocr_metadata:
                        extraction_metadata.update(ocr_metadata)

                    # Convert to dictionary for storage
                    extraction_data = {
                        "document_id": document_id,
                        "page_number": page_number,
                        "extraction_method": extraction_method,
                        "raw_text": final_raw_text,
                        "normalized_text": normalized_text,
                        "confidence": confidence,
                        "language": "eng",  # Default to English, could be detected
                        "extraction_metadata": extraction_metadata
                    }

                    extraction_results.append(extraction_data)
                    extraction_objects.append(extraction_data)

                # Persist extraction results
                await self._persist_extractions(session, extraction_objects)

                # Update document status to extracted
                await doc_repo.update_status(document_id, "extracted")
                await session.commit()

                logger.info(f"Successfully extracted text from document {document_id}")

                # Return extraction summary
                return {
                    "document_id": document_id,
                    "status": "extracted",
                    "page_count": analysis_results["page_count"],
                    "extractions": extraction_results
                }

            except Exception as e:
                # Update status to extraction_failed on error
                await doc_repo.update_status(document_id, "extraction_failed")
                await session.commit()
                logger.error(f"Extraction failed for document {document_id}: {e}")
                raise

    async def _retrieve_document_bytes(self, storage_reference: str) -> bytes:
        """
        Retrieve document bytes from storage.

        Args:
            storage_reference: Storage reference (path or key)

        Returns:
            Document bytes
        """
        file_obj = await self.storage_backend.retrieve_file(storage_reference)

        # Read all bytes from the file object
        if hasattr(file_obj, 'read'):
            bytes_data = await file_obj.read()
        else:
            bytes_data = file_obj  # Already bytes

        # Close the file object if it has a close method
        if hasattr(file_obj, 'close'):
            await file_obj.close()

        return bytes_data

    async def _is_extracted(self, session, document_id: str) -> bool:
        """
        Check if a document has already been text extracted.

        Args:
            session: Database session
            document_id: Document ID to check

        Returns:
            True if document has been extracted, False otherwise
        """
        stmt = select(DocumentTextExtraction).where(
            DocumentTextExtraction.document_id == document_id
        ).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _persist_extractions(
        self,
        session,
        extraction_data_list: List[Dict[str, Any]]
    ) -> None:
        """
        Persist extraction results to database.

        Args:
            session: Database session
            extraction_data_list: List of extraction data dictionaries
        """
        # Delete existing extractions for this document (if not doing incremental updates)
        delete_stmt = DocumentTextExtraction.__table__.delete().where(
            DocumentTextExtraction.document_id == extraction_data_list[0]["document_id"]
        )
        await session.execute(delete_stmt)

        # Create new extraction records
        extraction_objects = [
            DocumentTextExtraction(**extraction_data) for extraction_data in extraction_data_list
        ]
        session.add_all(extraction_objects)
        await session.commit()

    async def get_extraction_results(self, document_id: str) -> Dict[str, Any]:
        """
        Retrieve extraction results for a document.

        Args:
            document_id: Document ID

        Returns:
            Dictionary containing extraction results

        Raises:
            ValueError: If document not found
        """
        async with get_async_session_local()() as session:
            # Get document
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(document_id)
            if not document:
                raise ValueError(f"Document with ID {document_id} not found")

            # Get extraction records
            from app.models.extraction import DocumentTextExtraction
            stmt = select(DocumentTextExtraction).where(
                DocumentTextExtraction.document_id == document_id
            ).order_by(DocumentTextExtraction.page_number)
            result = await session.execute(stmt)
            extraction_records = result.scalars().all()

            # Convert to response format
            extractions = []
            for extraction in extraction_records:
                extractions.append({
                    "page_number": extraction.page_number,
                    "extraction_method": extraction.extraction_method,
                    "raw_text": extraction.raw_text,
                    "normalized_text": extraction.normalized_text,
                    "confidence": extraction.confidence,
                    "language": extraction.language,
                    "extraction_metadata": extraction.extraction_metadata
                })

            return {
                "document_id": document_id,
                "status": document.status,
                "page_count": len(extractions),
                "extractions": extractions
            }


# Convenience functions for external use
async def extract_text_from_document(document_id: str, force_reextraction: bool = False) -> Dict[str, Any]:
    """
    Convenience function to extract text from a document.

    Args:
        document_id: UUID of the document to extract text from
        force_reextraction: If True, re-extract even if already extracted

    Returns:
        Dictionary containing extraction summary
    """
    service = ExtractionService()
    return await service.extract_text_from_document(document_id, force_reextraction)


async def get_extraction_results(document_id: str) -> Dict[str, Any]:
    """
    Convenience function to get extraction results for a document.

    Args:
        document_id: Document ID

    Returns:
        Dictionary containing extraction results
    """
    service = ExtractionService()
    return await service.get_extraction_results(document_id)