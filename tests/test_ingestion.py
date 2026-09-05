import pytest
import asyncio
from io import BytesIO
from app.core.config import Settings
from app.models.document import Document


@pytest.mark.asyncio
async def test_successful_ingestion():
    """Test successful document ingestion."""
    # Import inside the function to get the reloaded module
    from app.services.ingestion_service import IngestionService
    # Arrange
    ingestion_service = IngestionService()
    test_data = b"This is a test document for ingestion testing."
    file_data = BytesIO(test_data)
    original_filename = "test_document.txt"
    content_type = "text/plain"

    # Act
    result = await ingestion_service.ingest_document(
        file_data=file_data,
        original_filename=original_filename,
        content_type=content_type
    )

    # Assert
    assert result.is_duplicate == False
    assert result.message == "Document successfully ingested"
    assert result.original_filename == original_filename
    assert result.content_type == content_type
    assert result.file_size == len(test_data)
    # Verify checksum is correct
    import hashlib
    expected_checksum = hashlib.sha256(test_data).hexdigest()
    assert result.checksum_sha256 == expected_checksum
    assert result.status == "ingested"
    assert result.document_id is not None


@pytest.mark.asyncio
async def test_duplicate_detection():
    """Test that duplicate documents are detected."""
    # Import inside the function to get the reloaded module
    from app.services.ingestion_service import IngestionService
    # Arrange
    ingestion_service = IngestionService()
    test_data = b"This is a test document for ingestion testing."
    file_data1 = BytesIO(test_data)
    file_data2 = BytesIO(test_data)  # Same data
    original_filename = "test_document.txt"
    content_type = "text/plain"

    # Act - Ingest first document
    result1 = await ingestion_service.ingest_document(
        file_data=file_data1,
        original_filename=original_filename,
        content_type=content_type
    )

    # Act - Ingest second document (should be duplicate)
    result2 = await ingestion_service.ingest_document(
        file_data=file_data2,
        original_filename=original_filename,
        content_type=content_type
    )

    # Assert
    assert result1.is_duplicate == False
    assert result2.is_duplicate == True
    assert result2.message == "Document already exists (duplicate)"
    assert result1.document_id == result2.document_id  # Same document ID
    assert result1.checksum_sha256 == result2.checksum_sha256  # Same checksum


@pytest.mark.asyncio
async def test_different_documents():
    """Test that different documents get different IDs."""
    # Import inside the function to get the reloaded module
    from app.services.ingestion_service import IngestionService
    # Arrange
    ingestion_service = IngestionService()
    test_data1 = b"This is test document 1."
    test_data2 = b"This is test document 2."
    file_data1 = BytesIO(test_data1)
    file_data2 = BytesIO(test_data2)
    original_filename1 = "test_document_1.txt"
    original_filename2 = "test_document_2.txt"
    content_type = "text/plain"

    # Act
    result1 = await ingestion_service.ingest_document(
        file_data=file_data1,
        original_filename=original_filename1,
        content_type=content_type
    )

    result2 = await ingestion_service.ingest_document(
        file_data=file_data2,
        original_filename=original_filename2,
        content_type=content_type
    )

    # Assert
    assert result1.is_duplicate == False
    assert result2.is_duplicate == False
    assert result1.document_id != result2.document_id  # Different document IDs
    assert result1.checksum_sha256 != result2.checksum_sha256  # Different checksums


@pytest.mark.asyncio
async def test_storage_and_retrieval():
    """Test that stored documents can be retrieved."""
    # Import inside the function to get the reloaded module
    from app.services.ingestion_service import IngestionService
    # Arrange
    ingestion_service = IngestionService()
    test_data = b"This is a test document for storage and retrieval."
    file_data = BytesIO(test_data)
    original_filename = "storage_test.txt"
    content_type = "text/plain"

    # Act
    result = await ingestion_service.ingest_document(
        file_data=file_data,
        original_filename=original_filename,
        content_type=content_type
    )

    # Assert ingestion succeeded
    assert result.is_duplicate == False

    # Now retrieve the document using the storage backend
    retrieved_file = await ingestion_service.storage_backend.retrieve_file(
        result.storage_reference
    )

    # Read the retrieved data
    retrieved_data = await retrieved_file.read()
    await retrieved_file.close()

    # Assert
    assert retrieved_data == test_data