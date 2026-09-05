"""
Tests for Phase 6 Validation, Quality Gates & Extraction Quality Assessment
"""

import pytest
import tempfile
import os
import uuid
from io import BytesIO
from unittest.mock import Mock, patch
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker
from app.models.document import Document
from app.models.extraction import DocumentTextExtraction
from app.models.structured_extraction import DocumentTableExtraction, DocumentChartAssociation
from app.models.validation import ValidationRun, ValidationFinding
from app.services.validation.schema_validator import SchemaValidator
from app.services.validation.table_validator import TableValidator
from app.services.validation.numeric_consistency_validator import NumericConsistencyValidator
from app.services.validation.quality_assessor import QualityAssessor
from app.services.validation.validation_persistence_service import ValidationPersistenceService
from app.services.validation.validation_service import ValidationService
from app.core.database import Base, get_async_session_local
import asyncio


# Test database setup
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def async_db_session():
    """Create an async database session for testing."""
    async with get_async_session_local()() as session:
        yield session


@pytest.fixture
def sample_document(async_db_session):
    """Create a sample document for testing."""
    # Note: This fixture is synchronous but uses an async fixture.
    # We need to handle the async session in a synchronous way for the fixture.
    # Since we're in a synchronous fixture, we'll run the async code in a new event loop.
    import asyncio
    from app.models.document import Document

    async def _create_document():
        async with get_async_session_local()() as session:
            document = Document(
                original_filename="test.pdf",
                content_type="application/pdf",
                file_size=1024,
                checksum_sha256="a" * 64,  # 64 character hash
                source_type="manual_upload",
                source_identifier="test",
                storage_reference="test/storage/test.pdf",  # Required field
                status="ingested"
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            return document

    # Run the async function in a new event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    document = loop.run_until_complete(_create_document())
    return document


@pytest.fixture
def sample_text_extraction(sample_document):
    """Create a sample text extraction for testing."""
    return DocumentTextExtraction(
        id=uuid.uuid4(),
        document_id=sample_document.id,
        page_number=1,
        extraction_method="ocr_tesseract",
        raw_text="Sample text content",
        normalized_text="Sample text content",
        confidence=0.85,
        language="eng",
        extraction_metadata={"ocr_engine": "tesseract"}
    )


@pytest.fixture
def sample_table_extraction(sample_document):
    """Create a sample table extraction for testing."""
    return DocumentTableExtraction(
        id=uuid.uuid4(),
        document_id=sample_document.id,
        page_number=1,
        table_index=0,
        extraction_method="opencv_plus_ocr",
        row_count=3,
        column_count=2,
        table_data=[["Header1", "Header2"], ["Value1", "Value2"], ["Total", "100"]],
        extraction_confidence=0.9,
        structure_confidence=0.85,
        source_artifact_reference="test_artifact",
        extraction_metadata={"test": "data"}
    )


@pytest.fixture
def sample_chart_association(sample_document, sample_table_extraction):
    """Create a sample chart association for testing."""
    return DocumentChartAssociation(
        id=uuid.uuid4(),
        document_id=sample_document.id,
        page_number=2,
        chart_index=0,
        associated_table_id=sample_table_extraction.id,
        association_method="same_page_table",
        association_confidence=0.8,
        chart_metadata={"chart_type": "bar"},
        resolution_status="resolved"
    )


class TestSchemaValidator:
    """Tests for the SchemaValidator class."""

    def test_schema_validator_initialization(self):
        """Test that SchemaValidator initializes correctly."""
        validator = SchemaValidator()
        assert validator is not None

    @pytest.mark.asyncio
    async def test_validate_text_extraction_valid(self, sample_text_extraction):
        """Test validation of a valid text extraction."""
        validator = SchemaValidator()
        findings = validator.validate_text_extraction(sample_text_extraction)

        # Should have no findings for valid extraction
        assert len(findings) == 0

    def test_validate_text_extraction_invalid_page_number(self, sample_document):
        """Test validation of text extraction with invalid page number."""
        extraction = DocumentTextExtraction(
            id="test-text-extraction-id-2",
            document_id=str(sample_document.id),  # Convert UUID to string for FK
            page_number=0,  # Invalid: must be positive
            extraction_method="ocr_tesseract",
            raw_text="Sample text",
            normalized_text="Sample text",
            confidence=0.85,
            language="eng"
        )

        validator = SchemaValidator()
        findings = validator.validate_text_extraction(extraction)

        # Should have one failed finding
        assert len(findings) == 1
        assert findings[0]['validator'] == 'schema'
        assert findings[0]['status'] == 'failed'
        assert 'page_number' in findings[0]['message'].lower()

    def test_validate_text_extraction_invalid_confidence(self, sample_document):
        """Test validation of text extraction with invalid confidence."""
        extraction = DocumentTextExtraction(
            id="test-text-extraction-id-3",
            document_id=str(sample_document.id),  # Convert UUID to string for FK
            page_number=1,
            extraction_method="ocr_tesseract",
            raw_text="Sample text",
            normalized_text="Sample text",
            confidence=1.5,  # Invalid: must be between 0 and 1
            language="eng"
        )

        validator = SchemaValidator()
        findings = validator.validate_text_extraction(extraction)

        # Should have one failed finding
        assert len(findings) == 1
        assert findings[0]['validator'] == 'schema'
        assert findings[0]['status'] == 'failed'
        assert 'confidence' in findings[0]['message'].lower()

    @pytest.mark.asyncio
    async def test_validate_table_extraction_valid(self, sample_table_extraction):
        """Test validation of a valid table extraction."""
        validator = SchemaValidator()
        findings = validator.validate_table_extraction(sample_table_extraction)

        # Should have no findings for valid extraction
        assert len(findings) == 0

    def test_validate_table_extraction_inconsistent_rows(self, sample_document):
        """Test validation of table extraction with inconsistent row widths."""
        table = DocumentTableExtraction(
            id="test-table-extraction-id-2",
            document_id=str(sample_document.id),  # Convert UUID to string for FK
            page_number=1,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            row_count=2,
            column_count=2,
            table_data=[["A", "B"], ["C", "D", "E"]],  # Second row has 3 columns
            extraction_confidence=0.9,
            structure_confidence=0.85
        )

        validator = SchemaValidator()
        findings = validator.validate_table_extraction(table)

        # Should have one failed finding
        assert len(findings) == 1
        assert findings[0]['validator'] == 'schema'
        assert findings[0]['status'] == 'failed'
        assert 'inconsistent' in findings[0]['message'].lower()

    @pytest.mark.asyncio
    async def test_validate_chart_association_valid(self, sample_chart_association):
        """Test validation of a valid chart association."""
        validator = SchemaValidator()
        findings = validator.validate_chart_association(sample_chart_association)

        # Should have no findings for valid association
        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_validate_chart_association_invalid_resolution_status(self, sample_document):
        """Test validation of chart association with invalid resolution status."""
        association = DocumentChartAssociation(
            id=uuid.uuid4(),
            document_id=sample_document.id,
            page_number=1,
            chart_index=0,
            associated_table_id=None,
            association_method="same_page_table",
            association_confidence=0.8,
            chart_metadata={},
            resolution_status="invalid_status"  # Invalid status
        )

        validator = SchemaValidator()
        findings = validator.validate_chart_association(association)

        # Should have one failed finding
        assert len(findings) == 1
        assert findings[0]['validator'] == 'schema'
        assert findings[0]['status'] == 'failed'
        assert 'resolution status' in findings[0]['message'].lower()


class TestTableValidator:
    """Tests for the TableValidator class."""

    def test_table_validator_initialization(self):
        """Test that TableValidator initializes correctly."""
        validator = TableValidator()
        assert validator is not None

    def test_validate_table_structure_valid(self, sample_table_extraction):
        """Test validation of a valid table structure."""
        validator = TableValidator()
        findings = validator.validate_table_structure(sample_table_extraction)

        # May have informational findings but no failures
        failure_findings = [f for f in findings if f['status'] == 'failed']
        assert len(failure_findings) == 0

    def test_validate_table_structure_empty_table(self, sample_document):
        """Test validation of an empty table."""
        table = DocumentTableExtraction(
            id="test-table-extraction-id-3",
            document_id=str(sample_document.id),
            page_number=1,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            row_count=0,  # Empty table
            column_count=0,
            table_data=[],
            extraction_confidence=0.9,
            structure_confidence=0.85
        )

        validator = TableValidator()
        findings = validator.validate_table_structure(table)

        # Should have failed findings for empty table
        failure_findings = [f for f in findings if f['status'] == 'failed']
        assert len(failure_findings) >= 1
        assert any('empty' in f['message'].lower() for f in failure_findings)

    def test_validate_table_structure_inconsistent_rows(self, sample_document):
        """Test validation of table with inconsistent row widths."""
        table = DocumentTableExtraction(
            id="test-table-extraction-id-4",
            document_id=str(sample_document.id),
            page_number=1,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            row_count=2,
            column_count=2,
            table_data=[["A", "B"], ["C", "D", "E"]],  # Inconsistent columns
            extraction_confidence=0.9,
            structure_confidence=0.85
        )

        validator = TableValidator()
        findings = validator.validate_table_structure(table)

        # Should have failed findings for inconsistent rows
        failure_findings = [f for f in findings if f['status'] == 'failed']
        assert len(failure_findings) >= 1
        assert any('inconsistent' in f['message'].lower() or 'width' in f['message'].lower() for f in failure_findings)

    def test_validate_table_structure_empty_rows(self, sample_document):
        """Test validation of table with empty rows."""
        table = DocumentTableExtraction(
            id="test-table-extraction-id-5",
            document_id=str(sample_document.id),
            page_number=1,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            row_count=3,
            column_count=2,
            table_data=[["A", "B"], ["", ""], ["C", "D"]],  # Middle row is empty
            extraction_confidence=0.9,
            structure_confidence=0.85
        )

        validator = TableValidator()
        findings = validator.validate_table_structure(table)

        # Should have info findings for empty rows
        info_findings = [f for f in findings if f['severity'] == 'info' and 'empty' in f['message'].lower()]
        assert len(info_findings) >= 1

    def test_is_numeric_like(self):
        """Test the numeric-like detection helper."""
        validator = TableValidator()

        # Test positive numbers
        assert validator._is_numeric_like("123") == True
        assert validator._is_numeric_like("123.45") == True
        assert validator._is_numeric_like("1,234") == True
        assert validator._is_numeric_like("$123") == True
        assert validator._is_numeric_like("(123)") == True  # Negative in parentheses

        # Test negative numbers
        assert validator._is_numeric_like("-123") == True
        assert validator._is_numeric_like("-123.45") == True

        # Test non-numeric
        assert validator._is_numeric_like("abc") == False
        assert validator._is_numeric_like("123abc") == False
        assert validator._is_numeric_like("") == False
        assert validator._is_numeric_like(None) == False


class TestNumericConsistencyValidator:
    """Tests for the NumericConsistencyValidator class."""

    def test_numeric_consistency_validator_initialization(self):
        """Test that NumericConsistencyValidator initializes correctly."""
        validator = NumericConsistencyValidator()
        assert validator is not None
        assert validator.tolerance == 0.01

    def test_validate_numeric_consistency_no_data(self, sample_document):
        """Test validation of table with no data."""
        table = DocumentTableExtraction(
            id="test-table-extraction-id-6",
            document_id=str(sample_document.id),
            page_number=1,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            row_count=0,
            column_count=0,
            table_data=[],
            extraction_confidence=0.9,
            structure_confidence=0.85
        )

        validator = NumericConsistencyValidator()
        findings = validator.validate_numeric_consistency(table)

        # Should have skipped findings
        skipped_findings = [f for f in findings if f['status'] == 'skipped']
        assert len(skipped_findings) >= 1
        assert any('no data' in f['message'].lower() for f in skipped_findings)

    def test_validate_numeric_consistency_no_total_row(self, sample_document):
        """Test validation of table with no explicit total row."""
        table = DocumentTableExtraction(
            id="test-table-extraction-id-7",
            document_id=str(sample_document.id),
            page_number=1,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            row_count=2,
            column_count=2,
            table_data=[["A", "10"], ["B", "20"]],  # No total row
            extraction_confidence=0.9,
            structure_confidence=0.85
        )

        validator = NumericConsistencyValidator()
        findings = validator.validate_numeric_consistency(table)

        # Should have skipped findings
        skipped_findings = [f for f in findings if f['status'] == 'skipped']
        assert len(skipped_findings) >= 1
        assert any('no explicit total' in f['message'].lower() for f in skipped_findings)

    @pytest.mark.asyncio
    async def test_validate_numeric_consistency_valid_total(self, sample_document):
        """Test validation of table with valid total row."""
        table = DocumentTableExtraction(
            id=uuid.uuid4(),
            document_id=sample_document.id,
            page_number=1,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            row_count=3,
            column_count=2,
            table_data=[["Item1", "10"], ["Item2", "20"], ["Total", "30"]],  # Valid total
            extraction_confidence=0.9,
            structure_confidence=0.85
        )

        validator = NumericConsistencyValidator()
        findings = validator.validate_numeric_consistency(table)

        # Should have passed findings for valid total
        passed_findings = [f for f in findings if f['status'] == 'passed']
        assert len(passed_findings) >= 1
        assert any('total match' in f['message'].lower() for f in passed_findings)

    @pytest.mark.asyncio
    async def test_validate_numeric_consistency_invalid_total(self, sample_document):
        """Test validation of table with invalid total row."""
        table = DocumentTableExtraction(
            id=uuid.uuid4(),
            document_id=sample_document.id,
            page_number=1,
            table_index=0,
            extraction_method="opencv_plus_ocr",
            row_count=3,
            column_count=2,
            table_data=[["Item1", "10"], ["Item2", "20"], ["Total", "40"]],  # Invalid total (should be 30)
            extraction_confidence=0.9,
            structure_confidence=0.85
        )

        validator = NumericConsistencyValidator()
        findings = validator.validate_numeric_consistency(table)

        # Should have failed findings for invalid total
        failed_findings = [f for f in findings if f['status'] == 'failed']
        assert len(failed_findings) >= 1
        assert any('total mismatch' in f['message'].lower() for f in failed_findings)

    def test_is_extractable_number(self):
        """Test the number extraction helper."""
        validator = NumericConsistencyValidator()

        # Test extractable numbers
        assert validator._is_extractable_number("123") == True
        assert validator._is_extractable_number("123.45") == True
        assert validator._is_extractable_number("1,234") == True
        assert validator._is_extractable_number("$123") == True
        assert validator._is_extractable_number("(123)") == True  # Negative in parentheses
        assert validator._is_extractable_number("-123") == True
        assert validator._is_extractable_number("12.5%") == True

        # Test non-extractable
        assert validator._is_extractable_number("abc") == False
        assert validator._is_extractable_number("123abc") == False
        assert validator._is_extractable_number("") == False
        assert validator._is_extractable_number(None) == False

    def test_extract_number(self):
        """Test the number extraction helper."""
        validator = NumericConsistencyValidator()

        # Test extraction
        assert validator._extract_number("123") == 123.0
        assert validator._extract_number("123.45") == 123.45
        assert validator._extract_number("1,234") == 1234.0
        assert validator._extract_number("$123") == 123.0
        assert validator._extract_number("(123)") == -123.0  # Negative in parentheses
        assert validator._extract_number("-123.45") == -123.45
        assert validator._extract_number("12.5%") == 12.5   # Percentage treated as unit (12.5, not 0.125)

        # Test non-extractable returns None
        assert validator._extract_number("abc") is None
        assert validator._extract_number("") is None
        assert validator._extract_number(None) is None


class TestQualityAssessor:
    """Tests for the QualityAssessor class."""

    def test_quality_assessor_initialization(self):
        """Test that QualityAssessor initializes correctly."""
        assessor = QualityAssessor()
        assert assessor is not None
        assert assessor.weights['ocr_confidence'] == 0.30
        assert assessor.weights['validation_pass_rate'] == 0.40
        assert assessor.weights['structure_quality'] == 0.20
        assert assessor.weights['completeness'] == 0.10

    def test_quality_assessor_initialization_with_config(self):
        """Test that QualityAssessor initializes with custom config."""
        config = {
            'weights': {
                'ocr_confidence': 0.40,
                'validation_pass_rate': 0.30,
                'structure_quality': 0.20,
                'completeness': 0.10
            }
        }
        assessor = QualityAssessor(config)
        assert assessor.weights['ocr_confidence'] == 0.40
        assert assessor.weights['validation_pass_rate'] == 0.30

    def test_assess_quality_no_extractions(self):
        """Test quality assessment with no extractions."""
        assessor = QualityAssessor()
        result = assessor.assess_quality(
            document_id="test-doc",
            text_extractions=[],
            table_extractions=[],
            chart_associations=[],
            validation_findings=[]
        )

        # Should return a valid score
        assert 'overall_quality_score' in result
        assert 0 <= result['overall_quality_score'] <= 100

    def test_assess_ocr_confidence_no_extractions(self):
        """Test OCR confidence assessment with no extractions."""
        assessor = QualityAssessor()
        score = assessor._assess_ocr_confidence([])
        assert score == 50.0  # Neutral score

    def test_assess_ocr_confidence_native_extraction(self):
        """Test OCR confidence assessment with native text extraction."""
        assessor = QualityAssessor()
        extraction = Mock()
        extraction.extraction_method = "native_pdf"
        extraction.confidence = None

        score = assessor._assess_ocr_confidence([extraction])
        assert score == 50.0  # Native extraction gets neutral score

    def test_assess_ocr_confidence_ocr_extraction(self):
        """Test OCR confidence assessment with OCR extraction."""
        assessor = QualityAssessor()
        extraction = Mock()
        extraction.extraction_method = "ocr_tesseract"
        extraction.confidence = 0.8  # 80% confidence

        score = assessor._assess_ocr_confidence([extraction])
        assert score == 80.0  # Should match the confidence

    def test_assess_ocr_confidence_multiple_ocr(self):
        """Test OCR confidence assessment with multiple OCR extractions."""
        assessor = QualityAssessor()
        extraction1 = Mock()
        extraction1.extraction_method = "ocr_tesseract"
        extraction1.confidence = 0.8

        extraction2 = Mock()
        extraction2.extraction_method = "ocr_tesseract"
        extraction2.confidence = 0.9

        score = assessor._assess_ocr_confidence([extraction1, extraction2])
        assert score == 85.0  # Average of 80 and 90

    def test_assess_validation_pass_rate_no_findings(self):
        """Test validation pass rate assessment with no findings."""
        assessor = QualityAssessor()
        score = assessor._assess_validation_pass_rate([])
        assert score == 50.0  # Neutral score

    def test_assess_validation_pass_rate_all_passed(self):
        """Test validation pass rate assessment with all passed."""
        assessor = QualityAssessor()
        findings = [
            {'status': 'passed'},
            {'status': 'passed'},
            {'status': 'passed'}
        ]
        score = assessor._assess_validation_pass_rate(findings)
        assert score == 100.0  # All passed

    def test_assess_validation_pass_rate_mixed(self):
        """Test validation pass rate assessment with mixed results."""
        assessor = QualityAssessor()
        findings = [
            {'status': 'passed'},
            {'status': 'failed'},
            {'status': 'passed'},
            {'status': 'skipped'}  # Skipped doesn't count against pass rate
        ]
        score = assessor._assess_validation_pass_rate(findings)
        assert score == 66.67  # 2 passed out of 3 applicable (passed + failed)

    def test_assess_structure_quality_no_tables(self):
        """Test structure quality assessment with no tables."""
        assessor = QualityAssessor()
        score = assessor._assess_structure_quality([])
        assert score == 50.0  # Neutral score

    def test_assess_completeness_no_extractions(self):
        """Test completeness assessment with no extractions."""
        assessor = QualityAssessor()
        score = assessor._assess_completeness([], [], [])
        assert score == 0.0  # No extractions

    def test_assess_completeness_some_extractions(self):
        """Test completeness assessment with some extractions."""
        assessor = QualityAssessor()
        text_extraction = Mock()
        table_extraction = Mock()
        chart_association = Mock()

        score = assessor._assess_completeness([text_extraction], [table_extraction], [chart_association])
        assert score == 90.0  # Good number of extractions

    def test_assess_quality_weighted_calculation(self):
        """Test that quality assessment uses weighted calculation correctly."""
        assessor = QualityAssessor()

        # Mock the component assessment methods to return known values
        assessor._assess_ocr_confidence = Mock(return_value=80.0)    # 80% OCR
        assessor._assess_validation_pass_rate = Mock(return_value=90.0) # 90% passed
        assessor._assess_structure_quality = Mock(return_value=70.0)   # 70% structure
        assessor._assess_completeness = Mock(return_value=60.0)       # 60% complete

        result = assessor.assess_quality(
            document_id="test-doc",
            text_extractions=[Mock()],
            table_extractions=[Mock()],
            chart_associations=[Mock()],
            validation_findings=[Mock()]
        )

        # Calculate expected score: 0.3*80 + 0.4*90 + 0.2*70 + 0.1*60 = 24 + 36 + 14 + 6 = 80
        expected_score = 80.0
        assert result['overall_quality_score'] == expected_score


class TestValidationPersistenceService:
    """Tests for the ValidationPersistenceService class."""

    @pytest.mark.asyncio
    async def test_create_validation_run(self, sample_document):
        """Test creating a validation run."""
        service = ValidationPersistenceService()

        run_id = await service.create_validation_run(
            document_id=sample_document.id,
            config_snapshot={"test": "config"},
            input_hash="test_hash"
        )

        assert run_id is not None
        assert len(str(run_id)) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_get_latest_validation_run_none(self, async_db_session, sample_document):
        """Test getting latest validation run when none exists."""
        service = ValidationPersistenceService()
        result = await service.get_latest_validation_run(sample_document.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_should_skip_validation_no_previous_run(self, async_db_session, sample_document):
        """Test idempotency check when no previous validation exists."""
        service = ValidationPersistenceService()
        should_skip, existing_run_id = await service.should_skip_validation(sample_document.id)
        assert should_skip == False
        assert existing_run_id is None

    @pytest.mark.asyncio
    async def test_compute_input_hash(self, async_db_session, sample_document):
        """Test computing input hash for idempotency."""
        service = ValidationPersistenceService()
        # Compute the hash for the sample document
        hash_result = await service.compute_input_hash(sample_document.id)
        # Should return a string (SHA-256 hash)
        assert isinstance(hash_result, str)
        assert len(hash_result) == 64  # SHA-256 hex digest length


class TestValidationService:
    """Tests for the ValidationService class."""

    def test_validation_service_initialization(self):
        """Test that ValidationService initializes correctly."""
        service = ValidationService()
        assert service is not None
        assert service.schema_validator is not None
        assert service.table_validator is not None
        assert service.numeric_validator is not None
        assert service.quality_assessor is not None
        assert service.persistence_service is not None

    def test_get_config_snapshot(self):
        """Test getting configuration snapshot."""
        service = ValidationService()
        config = service._get_config_snapshot()
        assert 'validation_auto_approve_threshold' in config
        assert 'numeric_consistency_tolerance' in config
        assert 'quality_assessor_weights' in config

    def test_determine_final_decision_approved(self):
        """Test final decision logic for approved status."""
        service = ValidationService()

        # High score, no critical errors
        decision = service._determine_final_decision(
            quality_score=90.0,
            validation_findings=[]
        )
        assert decision == "approved"

    def test_determine_final_decision_flagged_below_threshold(self):
        """Test final decision logic for flagged status due to low score."""
        service = ValidationService()

        # Low score
        decision = service._determine_final_decision(
            quality_score=70.0,
            validation_findings=[]
        )
        assert decision == "flagged"

    def test_determine_final_decision_flagged_critical_error(self):
        """Test final decision logic for flagged status due to critical error."""
        service = ValidationService()

        # High score but critical error
        findings = [
            {
                'severity': 'critical',
                'status': 'error',
                'message': 'Validation process failed'
            }
        ]
        decision = service._determine_final_decision(
            quality_score=90.0,
            validation_findings=findings
        )
        assert decision == "failed"  # Critical errors lead to failed, not flagged

    def test_determine_final_decision_flagged_error_findings(self):
        """Test final decision logic for flagged status due to error findings."""
        service = ValidationService()

        # High score but error findings
        findings = [
            {
                'severity': 'error',
                'status': 'failed',
                'message': 'Total mismatch'
            }
        ]
        decision = service._determine_final_decision(
            quality_score=90.0,
            validation_findings=findings
        )
        assert decision == "flagged"

    @pytest.mark.asyncio
    async def test_validate_document_missing_document(self):
        """Test validation of missing document."""
        service = ValidationService()

        with pytest.raises(ValueError, match="not found"):
            await service.validate_document("non-existent-doc-id")


class TestValidationAPIEndpoints:
    """Tests for the validation API endpoints."""

    def test_validation_router_import(self):
        """Test that validation router can be imported."""
        from app.api.endpoints.validation import router
        assert router is not None

    def test_validation_endpoints_exist(self):
        """Test that validation endpoints are defined."""
        from app.api.endpoints.validation import router

        # Get all routes
        routes = [route.path for route in router.routes]

        # Check that expected endpoints exist
        assert any("/{document_id}/validate" in route for route in routes)
        assert any("/{document_id}/validation" in route for route in routes)
        assert any("/{document_id}/validation/findings" in route for route in routes)
        assert any("/validation/{validation_run_id}" in route for route in routes)


if __name__ == "__main__":
    pytest.main([__file__])