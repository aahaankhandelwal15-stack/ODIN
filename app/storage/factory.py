from app.storage.local import LocalStorageBackend
from app.storage.s3 import S3CompatibleStorageBackend
from app.storage.base import StorageBackend
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)


def get_storage_backend() -> StorageBackend:
    """
    Factory function to get the appropriate storage backend based on configuration.
    """
    settings = get_settings()
    if settings.STORAGE_BACKEND == "s3":
        logger.info("Initializing S3 compatible storage backend")
        return S3CompatibleStorageBackend()
    else:
        logger.info("Initializing local storage backend")
        return LocalStorageBackend()