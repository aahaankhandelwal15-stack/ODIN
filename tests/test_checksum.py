import hashlib
import pytest
from app.utils.checksum import calculate_sha256, calculate_sha256_from_path
import tempfile
import os


def test_calculate_sha256():
    """Test SHA-256 calculation from file data."""
    test_data = b"Hello, World!"
    expected = hashlib.sha256(test_data).hexdigest()

    # Test with bytes data
    from io import BytesIO
    file_data = BytesIO(test_data)
    result = calculate_sha256(file_data)
    assert result == expected


def test_calculate_sha256_from_path():
    """Test SHA-256 calculation from file path."""
    test_data = b"Hello, World!"
    expected = hashlib.sha256(test_data).hexdigest()

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(test_data)
        tmp_file.flush()
        tmp_file_name = tmp_file.name

    # File should be closed now after exiting the with block
    try:
        result = calculate_sha256_from_path(tmp_file_name)
        assert result == expected
    finally:
        # Clean up
        os.unlink(tmp_file_name)


def test_different_files_different_checksums():
    """Test that different files produce different checksums."""
    data1 = b"Hello, World!"
    data2 = b"Hello, Worlds!"

    from io import BytesIO
    file1 = BytesIO(data1)
    file2 = BytesIO(data2)

    hash1 = calculate_sha256(file1)
    hash2 = calculate_sha256(file2)

    assert hash1 != hash2
    assert hash1 == hashlib.sha256(data1).hexdigest()
    assert hash2 == hashlib.sha256(data2).hexdigest()


def test_same_file_same_checksum():
    """Test that the same file produces the same checksum."""
    data = b"Test data for checksum"

    from io import BytesIO
    file1 = BytesIO(data)
    file2 = BytesIO(data)

    hash1 = calculate_sha256(file1)
    hash2 = calculate_sha256(file2)

    assert hash1 == hash2