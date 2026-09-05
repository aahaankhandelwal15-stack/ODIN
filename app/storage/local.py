import os
import uuid
import aiofiles
from typing import BinaryIO, Union
from app.storage.base import StorageBackend
from app.core.config import get_settings


class LocalStorageBackend(StorageBackend):
    def __init__(self, storage_root: str = None):
        settings = get_settings()
        self.storage_root = storage_root or settings.STORAGE_LOCAL_PATH
        # Ensure storage root exists
        os.makedirs(self.storage_root, exist_ok=True)

    async def store_file(
        self,
        file_data: Union[BinaryIO, bytes],
        file_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Store file data and return a unique storage reference (UUID).
        The file_path argument is ignored for local storage; we generate our own.
        """
        # Generate a unique filename
        file_id = uuid.uuid4()
        # We could use extension from original filename, but not necessary
        full_path = os.path.join(self.storage_root, str(file_id))

        # Convert file_data to bytes if it's not already
        if isinstance(file_data, bytes):
            data = file_data
        else:
            # Assume it's a file-like object
            # Reset file pointer to beginning if needed
            if hasattr(file_data, "seek"):
                file_data.seek(0)
            data = file_data.read()

        # Write the bytes asynchronously
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(data)

        return str(file_id)

    async def retrieve_file(self, file_path: str) -> BinaryIO:
        """
        Retrieve file by storage reference (UUID).
        Returns an async file object opened for reading in binary mode.
        """
        full_path = os.path.join(self.storage_root, file_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        # Return an async file object
        return await aiofiles.open(full_path, "rb")

    async def delete_file(self, file_path: str) -> None:
        """
        Delete file by storage reference.
        """
        full_path = os.path.join(self.storage_root, file_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    async def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists.
        """
        full_path = os.path.join(self.storage_root, file_path)
        return os.path.exists(full_path)