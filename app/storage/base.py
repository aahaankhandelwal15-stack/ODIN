from abc import ABC, abstractmethod
from typing import BinaryIO, Optional
import uuid


class StorageBackend(ABC):
    @abstractmethod
    async def store_file(
        self,
        file_data: BinaryIO,
        file_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Store a file and return a storage reference (path or key).
        Should not overwrite if file already exists (immutable).
        """
        pass

    @abstractmethod
    async def retrieve_file(self, file_path: str) -> BinaryIO:
        """
        Retrieve a file by its storage reference.
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> None:
        """
        Delete a file. Note: For immutable storage, this might not be used in normal flow.
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists at the given storage reference.
        """
        pass