"""
Tests for Phase 5 Structured Table & Chart Extraction
"""

import pytest
import tempfile
import os
from io import BytesIO
from unittest.mock import Mock, patch
from app.services.structured_extraction.table_extractor import TableExtractor, TableExtractionResult, TableCell
from app.services.structured_extraction.structured_extraction_service import StructuredExtractionService
from app.models.structured_extraction import DocumentTableExtraction, DocumentChartAssociation


class TestTableExtractor:
    """Tests for the TableExtractor class."""

    def test_extractor_initialization(self):
        """Test that TableExtractor initializes correctly."""
        extractor = TableExtractor()
        assert extractor is not None
        assert hasattr(extractor, 'tesseract_available')

    def test_extractor_initialization_with_language(self):
        """Test that TableExtractor initializes with language parameter."""
        extractor = TableExtractor(language='fra')
        assert extractor.language == 'fra'

    @patch('app.services.structured_extraction.table_extractor.TESSERACT_AVAILABLE', False)
    def test_extractor_without_tesseract(self):
        """Test that TableExtractor works when Tesseract is not available."""
        extractor = TableExtractor()
        assert extractor.tesseract_available == False

    def test_table_cell_dataclass(self):
        """Test TableCell dataclass."""
        cell = TableCell(
            text="Test Cell",
            row_index=0,
            column_index=1,
            confidence=0.95,
            bounding_box={"x": 10, "y": 20, "width": 50, "height": 30}
        )

        assert cell.text == "Test Cell"
        assert cell.row_index == 0
        assert cell.column_index == 1
        assert cell.confidence == 0.95
        assert cell.bounding_box["x"] == 10

    def test_table_extraction_result_dataclass(self):
        """Test TableExtractionResult dataclass."""
        result = TableExtractionResult(
            document_id="test-doc",
            page_number=1,
            table_index=0,
            extraction_method="test_method",
            rows=[["A1", "B1"], ["A2", "B2"]],
            row_count=2,
            column_count=2,
            extraction_confidence=0.8,
            structure_confidence=0.9
        )

        assert result.document_id == "test-doc"
        assert result.page_number == 1
        assert result.table_index == 0
        assert result.rows == [["A1", "B1"], ["A2", "B2"]]
        assert result.row_count == 2
        assert result.column_count == 2


class TestStructuredExtractionService:
    """Tests for the StructuredExtractionService class."""

    def test_service_initialization(self):
        """Test that StructuredExtractionService initializes correctly."""
        service = StructuredExtractionService()
        assert service is not None
        assert service.table_extractor is not None
        assert service.extraction_service is not None

    @pytest.mark.asyncio
    async def test_should_extract_tables_logic(self):
        """Test the table extraction routing logic."""
        service = StructuredExtractionService()

        # Test table_dense - should extract
        assert service._should_extract_tables("table_dense", 1, {}) == True

        # Test mixed - should extract
        assert service._should_extract_tables("mixed", 1, {}) == True

        # Test scanned_document - should extract
        assert service._should_extract_tables("scanned_document", 1, {}) == True

        # Test typed_text - should NOT extract (conservative)
        assert service._should_extract_tables("typed_text", 1, {}) == False

        # Test chart_graph - should NOT extract (handled separately)
        assert service._should_extract_tables("chart_graph", 1, {}) == False

        # Test map_diagram - should NOT extract (handled separately)
        assert service._should_extract_tables("map_diagram", 1, {}) == False

        # Test unknown - should NOT extract
        assert service._should_extract_tables("unknown", 1, {}) == False

    def test_table_result_to_model_conversion(self):
        """Test conversion from TableExtractionResult to DocumentTableExtraction model."""
        service = StructuredExtractionService()

        table_result = TableExtractionResult(
            document_id="test-doc-uuid",
            page_number=2,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            rows=[["Header1", "Header2"], ["Value1", "Value2"]],
            row_count=2,
            column_count=2,
            extraction_confidence=0.85,
            structure_confidence=0.9,
            source_artifact_reference="test_artifact",
            extraction_metadata={"test": "data"}
        )

        model = service._table_result_to_model(table_result)

        assert isinstance(model, DocumentTableExtraction)
        assert model.document_id == "test-doc-uuid"
        assert model.page_number == 2
        assert model.table_index == 0
        assert model.extraction_method == "opencv_plus_ocr"
        assert model.row_count == 2
        assert model.column_count == 2
        assert model.table_data == [["Header1", "Header2"], ["Value1", "Value2"]]
        assert model.extraction_confidence == 0.85
        assert model.structure_confidence == 0.9
        assert model.source_artifact_reference == "test_artifact"


if __name__ == "__main__":
    pytest.main([__file__])