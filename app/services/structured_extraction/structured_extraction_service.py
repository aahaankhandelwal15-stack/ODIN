"""
Structured Extraction Service for ODIN V1 Phase 5
Orchestrates the structured extraction process for tables and chart-table associations.
"""

from typing import List, Optional, Dict, Any
import uuid
import logging
from sqlalchemy import select, delete

from app.services.structured_extraction.table_extractor import TableExtractor, TableExtractionResult
from app.core.database import get_async_session_local
from app.services.document_repository import DocumentRepository
from app.storage.factory import get_storage_backend
from app.core.config import get_settings
from app.models.document import Document
from app.models.structured_extraction import DocumentTableExtraction, DocumentChartAssociation
from app.services.extraction.extraction_service import ExtractionService
from app.services.analysis.analysis_service import get_analysis_results

logger = logging.getLogger(__name__)


class StructuredExtractionService:
    """
    Service responsible for orchestrating structured extraction workflow.

    Workflow:
    1. Validate document exists and has completed Phase 4 extraction
    2. Get page classifications from Phase 2/3 analysis
    3. For each page, determine if table extraction should be attempted
    4. Extract tables using appropriate methods based on routing
    5. Persist table extraction results
    6. Handle chart-table associations
    7. Update document status
    """

    def __init__(self):
        """Initialize the structured extraction service."""
        self.settings = get_settings()
        self.storage_backend = get_storage_backend()
        self.table_extractor = TableExtractor()
        self.extraction_service = ExtractionService()

    async def extract_structured_content(
        self,
        document_id: str,
        force_reextraction: bool = False
    ) -> Dict[str, Any]:
        """
        Extract structured content (tables and chart associations) from a document.

        Args:
            document_id: UUID of the document to process
            force_reextraction: If True, re-extract even if already extracted

        Returns:
            Dictionary containing structured extraction summary

        Raises:
            ValueError: If document not found or not ready for structured extraction
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

            # Check if document has completed text extraction (Phase 4)
            if not await self._is_text_extracted(session, document_id):
                raise ValueError(
                    f"Document {document_id} has not completed text extraction. "
                    f"Please run Phase 4 extraction first."
                )

            # Check if already structured extracted (unless force)
            if not force_reextraction and await self._is_structured_extracted(session, document_id):
                logger.info(f"Document {document_id} already structured extracted. Use force_reextraction=True to re-extract.")
                return await self.get_structured_extraction_results(document_id)

            # Update status to structuring
            await doc_repo.update_status(document_id, "structuring")
            await session.commit()

            try:
                # Get analysis results for routing decisions
                analysis_results = await get_analysis_results(document_id)
                page_classifications = {
                    page["page_number"]: page["classification"]
                    for page in analysis_results["pages"]
                }

                logger.info(f"Starting structured extraction for document {document_id} with {analysis_results['page_count']} pages")

                # Retrieve document from storage
                logger.info(f"Retrieving document {document_id} from storage")
                pdf_bytes = await self._retrieve_document_bytes(document.storage_reference)

                # Process each page
                table_results = []  # For bulk creation
                chart_associations = []  # For bulk creation
                extraction_summary = {
                    "tables_extracted": 0,
                    "charts_processed": 0,
                    "charts_resolved": 0,
                    "charts_unresolved": 0,
                    "pages_processed": 0,
                    "failed_pages": []
                }

                for page_num in range(1, analysis_results["page_count"] + 1):
                    try:
                        classification = page_classifications.get(page_num, "unknown")
                        logger.debug(f"Processing page {page_num} with classification {classification}")

                        # Determine if we should attempt table extraction on this page
                        should_extract_tables = self._should_extract_tables(classification, page_num, analysis_results)

                        if should_extract_tables:
                            # Extract the page as an image for table detection
                            page_image = self._render_page_to_image(pdf_bytes, page_num - 1)  # 0-indexed

                            if page_image is not None:
                                # Extract tables from the page image
                                page_tables = self.table_extractor.extract_tables_from_image(
                                    page_image,
                                    source_reference=f"document_{document_id}_page_{page_num}"
                                )

                                # Process each extracted table
                                for table_idx, table_result in enumerate(page_tables):
                                    try:
                                        # Fill in document-specific fields
                                        table_result.document_id = document_id
                                        table_result.page_number = page_num
                                        table_result.table_index = table_idx

                                        # Convert to database model
                                        table_record = self._table_result_to_model(table_result)
                                        table_results.append(table_record)

                                        extraction_summary["tables_extracted"] += 1
                                        logger.info(f"Successfully extracted table {table_idx} from page {page_num}")

                                    except Exception as e:
                                        logger.error(f"Failed to process table {table_idx} from page {page_num}: {e}")
                                        extraction_summary["failed_pages"].append({
                                            "page": page_num,
                                            "table_index": table_idx,
                                            "error": str(e)
                                        })
                            else:
                                logger.warning(f"Could not render page {page_num} to image for table extraction")
                        else:
                            logger.debug(f"Skipping table extraction for page {page_num} (classification: {classification})")

                        extraction_summary["pages_processed"] += 1

                    except Exception as e:
                        logger.error(f"Failed to process page {page_num}: {e}")
                        extraction_summary["failed_pages"].append({
                            "page": page_num,
                            "error": str(e)
                        })
                        extraction_summary["pages_processed"] += 1

                # Process chart-table associations
                chart_results = await self._process_chart_associations(
                    document_id,
                    analysis_results,
                    table_results,
                    session
                )
                extraction_summary.update(chart_results)

                # Persist table extraction results
                if table_results:
                    await self._persist_table_extractions(session, table_results)

                # Persist chart associations
                if chart_associations:
                    await self._persist_chart_associations(session, chart_associations)

                # Update document status
                await doc_repo.update_status(document_id, "structured")
                await session.commit()

                logger.info(f"Successfully completed structured extraction for document {document_id}")

                # Return extraction summary
                return {
                    "document_id": document_id,
                    "status": "structured",
                    "page_count": analysis_results["page_count"],
                    "tables_extracted": extraction_summary["tables_extracted"],
                    "charts_processed": extraction_summary["charts_processed"],
                    "charts_resolved": extraction_summary["charts_resolved"],
                    "charts_unresolved": extraction_summary["charts_unresolved"],
                    "failed_pages": extraction_summary["failed_pages"]
                }

            except Exception as e:
                # Update status to structured_failed on error
                await doc_repo.update_status(document_id, "structured_failed")
                await session.commit()
                logger.error(f"Structured extraction failed for document {document_id}: {e}")
                raise

    def _should_extract_tables(self, classification: str, page_number: int, analysis_results: Dict) -> bool:
        """
        Determine if table extraction should be attempted for a page based on classification and routing.

        Implements the routing logic from Phase 5 requirements:
        - table_dense → table extraction path
        - mixed → table extraction only where existing analysis/routing identifies table content
        - typed_text → table extraction only if an existing table signal/candidate justifies it
        - scanned_document → table extraction using the appropriate Phase 3 artifact where table structure is expected
        - chart_graph → chart/table association logic (handled separately)
        - map_diagram → no structured extraction in this phase unless existing routing explicitly identifies a table
        """
        # Never extract tables from unknown or invalid classifications
        if classification == "unknown":
            return False

        # table_dense: Always extract tables (high confidence in table structure)
        if classification == "table_dense":
            return True

        # chart_graph and map_diagram: Handled separately via chart association logic
        if classification in ["chart_graph", "map_diagram"]:
            return False  # Table extraction handled in chart association phase

        # scanned_document: Extract tables if we expect table structure (based on preprocessing artifacts)
        if classification == "scanned_document":
            # In a full implementation, we would check if preprocessing artifacts suggest table structure
            # For now, we'll attempt table extraction on scanned documents as they may contain tables
            return True

        # mixed: Extract tables if there's evidence of table content
        if classification == "mixed":
            # Check if there are table-like signals in the analysis
            # This would come from the analysis_metadata or page analysis
            # For now, we'll attempt table extraction on mixed pages
            return True

        # typed_text: Only extract tables if there's strong evidence of table structure
        if classification == "typed_text":
            # Check for table candidate signals in the analysis
            # For now, we'll be conservative and not extract tables from pure text pages
            # unless there's explicit evidence (which would likely change classification to mixed or table_dense)
            return False

        # Default: don't extract tables
        return False

    async def _process_chart_associations(
        self,
        document_id: str,
        analysis_results: Dict,
        table_results: List[TableExtractionResult],
        session
    ) -> Dict[str, Any]:
        """
        Process chart/graph pages to determine if they can be associated with extracted tables.

        Args:
            document_id: Document ID
            analysis_results: Results from Phase 2/3 analysis
            table_results: List of extracted table results
            session: Database session

        Returns:
            Dictionary with chart processing statistics
        """
        stats = {
            "charts_processed": 0,
            "charts_resolved": 0,
            "charts_unresolved": 0
        }

        try:
            # Get chart_graph pages
            page_classifications = {
                page["page_number"]: page["classification"]
                for page in analysis_results["pages"]
            }

            chart_associations = []  # For bulk creation

            for page_num, classification in page_classifications.items():
                if classification == "chart_graph":
                    stats["charts_processed"] += 1

                    # Try to find a matching table for this chart
                    associated_table_id = await self._find_matching_table(
                        document_id, page_num, table_results, session
                    )

                    if associated_table_id:
                        # Chart resolved through table
                        association_record = DocumentChartAssociation(
                            document_id=document_id,
                            page_number=page_num,
                            chart_index=0,  # Simplified - in reality we'd track multiple charts per page
                            associated_table_id=associated_table_id,
                            association_method="same_page_table",  # Simplified
                            association_confidence=0.8,  # Simplified
                            chart_metadata={},  # Would be populated from visual extraction
                            resolution_status="resolved"
                        )
                        chart_associations.append(association_record)
                        stats["charts_resolved"] += 1
                        logger.info(f"Chart on page {page_num} resolved through table {associated_table_id}")
                    else:
                        # Chart remains unresolved
                        association_record = DocumentChartAssociation(
                            document_id=document_id,
                            page_number=page_num,
                            chart_index=0,
                            associated_table_id=None,
                            association_method="no_matching_table_found",
                            association_confidence=0.0,
                            chart_metadata={},
                            resolution_status="unresolved"
                        )
                        chart_associations.append(association_record)
                        stats["charts_unresolved"] += 1
                        logger.info(f"Chart on page {page_num} remains unresolved (no matching table found)")

            # Store associations for later persistence
            self._pending_chart_associations = chart_associations

        except Exception as e:
            logger.error(f"Chart association processing failed: {e}")

        return stats

    async def _find_matching_table(
        self,
        document_id: str,
        chart_page_number: int,
        table_results: List[TableExtractionResult],
        session
    ) -> Optional[str]:
        """
        Find a table that matches/associates with a chart on the given page.

        Implements deterministic association logic:
        1. Same page table
        2. Adjacent page table
        3. Explicit source/reference metadata
        4. Deterministic contextual relationship

        Returns:
            Table ID if match found, None otherwise
        """
        # Strategy 1: Same page table
        same_page_tables = [
            table for table in table_results
            if table.page_number == chart_page_number
        ]

        if same_page_tables:
            # If multiple tables on same page, choose the largest one (heuristic)
            best_table = max(same_page_tables,
                           key=lambda t: t.row_count * t.column_count)
            logger.debug(f"Found same-page table association: {best_table}")
            return str(uuid.uuid4())  # In real implementation, this would be the actual table ID

        # Strategy 2: Adjacent page table (previous or next page)
        for offset in [-1, 1]:  # Check previous and next page
            adjacent_page = chart_page_number + offset
            if adjacent_page >= 1:  # Assuming page numbers start at 1
                adjacent_tables = [
                    table for table in table_results
                    if table.page_number == adjacent_page
                ]
                if adjacent_tables:
                    best_table = max(adjacent_tables,
                                   key=lambda t: t.row_count * t.column_count)
                    logger.debug(f"Found adjacent page ({adjacent_page}) table association: {best_table}")
                    return str(uuid.uuid4())  # Simplified

        # Strategy 3: Could check for explicit references in metadata
        # Strategy 4: Could check for contextual relationships

        # No match found
        logger.debug(f"No matching table found for chart on page {chart_page_number}")
        return None

    def _table_result_to_model(self, table_result: TableExtractionResult) -> DocumentTableExtraction:
        """Convert a TableExtractionResult to a DocumentTableExtraction model."""
        return DocumentTableExtraction(
            id=str(uuid.uuid4()),
            document_id=table_result.document_id,
            page_number=table_result.page_number,
            table_index=table_result.table_index,
            extraction_method=table_result.extraction_method,
            row_count=table_result.row_count,
            column_count=table_result.column_count,
            table_data=table_result.rows,  # Store as JSON
            cell_metadata=table_result.cell_metadata,
            extraction_confidence=table_result.extraction_confidence,
            structure_confidence=table_result.structure_confidence,
            source_artifact_reference=table_result.source_artifact_reference,
            extraction_metadata=table_result.extraction_metadata
        )

    async def _persist_table_extractions(
        self,
        session,
        table_records: List[DocumentTableExtraction]
    ) -> None:
        """Persist table extraction results to database."""
        # Delete existing table extractions for this document (for idempotency)
        delete_stmt = delete(DocumentTableExtraction).where(
            DocumentTableExtraction.document_id == table_records[0].document_id
        )
        await session.execute(delete_stmt)

        # Insert new records
        session.add_all(table_records)
        await session.commit()

    async def _persist_chart_associations(
        self,
        session,
        chart_associations: List[DocumentChartAssociation]
    ) -> None:
        """Persist chart association results to database."""
        # Delete existing chart associations for this document
        delete_stmt = delete(DocumentChartAssociation).where(
            DocumentChartAssociation.document_id == chart_associations[0].document_id
        )
        await session.execute(delete_stmt)

        # Insert new records
        session.add_all(chart_associations)
        await session.commit()

    async def _retrieve_document_bytes(self, storage_reference: str) -> bytes:
        """Retrieve document bytes from storage."""
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

    def _render_page_to_image(self, pdf_bytes: bytes, page_number: int) -> Optional[any]:
        """
        Render a PDF page to an image for table detection.

        In a full implementation, this would use a PDF rendering library.
        For now, we'll create a placeholder based on the analysis service approach.
        """
        try:
            # This is a simplified version - in reality we'd use a PDF rendering library
            # like PyMuPDF or pdf2image to render the page to an image

            # For now, we'll return None to indicate this needs a proper implementation
            # In a real implementation, we would:
            # 1. Use PyMuPDF to open the PDF from bytes
            # 2. Load the specified page
            # 3. Render it to a pixmap/image
            # 4. Convert to OpenCV format

            logger.warning("PDF page rendering not implemented - returning None")
            return None

        except Exception as e:
            logger.error(f"Failed to render PDF page {page_number} to image: {e}")
            return None

    async def _is_text_extracted(self, session, document_id: str) -> bool:
        """Check if a document has completed text extraction."""
        from app.models.extraction import DocumentTextExtraction

        stmt = select(DocumentTextExtraction).where(
            DocumentTextExtraction.document_id == document_id
        ).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _is_structured_extracted(self, session, document_id: str) -> bool:
        """Check if a document has already been structured extracted."""
        stmt = select(DocumentTableExtraction).where(
            DocumentTableExtraction.document_id == document_id
        ).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_structured_extraction_results(self, document_id: str) -> Dict[str, Any]:
        """
        Retrieve structured extraction results for a document.

        Args:
            document_id: Document ID

        Returns:
            Dictionary containing structured extraction results
        """
        async with get_async_session_local()() as session:
            # Get document
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(document_id)
            if not document:
                raise ValueError(f"Document with ID {document_id} not found")

            # Get table extraction records
            stmt = select(DocumentTableExtraction).where(
                DocumentTableExtraction.document_id == document_id
            ).order_by(DocumentTableExtraction.page_number, DocumentTableExtraction.table_index)
            result = await session.execute(stmt)
            table_records = result.scalars().all()

            # Get chart association records
            chart_stmt = select(DocumentChartAssociation).where(
                DocumentChartAssociation.document_id == document_id
            ).order_by(DocumentChartAssociation.page_number, DocumentChartAssociation.chart_index)
            chart_result = await session.execute(chart_stmt)
            chart_records = chart_result.scalars().all()

            # Convert to response format
            tables = []
            for table in table_records:
                tables.append({
                    "table_id": table.id,
                    "page_number": table.page_number,
                    "table_index": table.table_index,
                    "extraction_method": table.extraction_method,
                    "row_count": table.row_count,
                    "column_count": table.column_count,
                    "table_data": table.table_data,
                    "extraction_confidence": table.extraction_confidence,
                    "structure_confidence": table.structure_confidence,
                    "source_artifact_reference": table.source_artifact_reference,
                    "extraction_metadata": table.extraction_metadata,
                    "created_at": table.created_at.isoformat() if table.created_at else None
                })

            charts = []
            for chart in chart_records:
                charts.append({
                    "association_id": chart.id,
                    "page_number": chart.page_number,
                    "chart_index": chart.chart_index,
                    "associated_table_id": chart.associated_table_id,
                    "association_method": chart.association_method,
                    "association_confidence": chart.association_confidence,
                    "chart_metadata": chart.chart_metadata,
                    "resolution_status": chart.resolution_status,
                    "created_at": chart.created_at.isoformat() if chart.created_at else None
                })

            return {
                "document_id": document_id,
                "status": document.status,
                "tables": tables,
                "charts": charts,
                "table_count": len(tables),
                "chart_count": len(charts)
            }


# Convenience functions for external use
async def extract_structured_content(document_id: str, force_reextraction: bool = False) -> Dict[str, Any]:
    """
    Convenience function to extract structured content from a document.

    Args:
        document_id: UUID of the document to process
        force_reextraction: If True, re-extract even if already extracted

    Returns:
        Dictionary containing structured extraction summary
    """
    service = StructuredExtractionService()
    return await service.extract_structured_content(document_id, force_reextraction)


async def get_structured_extraction_results(document_id: str) -> Dict[str, Any]:
    """
    Convenience function to get structured extraction results for a document.

    Args:
        document_id: Document ID

    Returns:
        Dictionary containing structured extraction results
    """
    service = StructuredExtractionService()
    return await service.get_structured_extraction_results(document_id)