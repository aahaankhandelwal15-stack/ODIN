import hashlib
from typing import BinaryIO
import hashlib


def calculate_sha256(file_data: BinaryIO) -> str:
    """
    Calculate SHA-256 checksum from file data.
    Important: This function reads from the current file position and does not reset it.
    Caller should manage file position as needed.
    """
    sha256_hash = hashlib.sha256()
    # Read file in chunks to handle large files
    for chunk in iter(lambda: file_data.read(4096), b""):
        sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def calculate_sha256_from_path(file_path: str) -> str:
    """
    Calculate SHA-256 checksum from a file path.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()