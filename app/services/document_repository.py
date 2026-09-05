from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentResponse
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_checksum(self, checksum_sha256: str) -> Optional[Document]:
        """
        Get document by SHA-256 checksum.
        """
        try:
            stmt = select(Document).where(Document.checksum_sha256 == checksum_sha256)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error retrieving document by checksum: {e}")
            raise

    async def get_by_id(self, document_id: str) -> Optional[Document]:
        """
        Get document by ID.
        """
        try:
            import uuid
            document_uuid = uuid.UUID(document_id)
            stmt = select(Document).where(Document.id == document_uuid)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except ValueError:
            # Invalid UUID string
            return None
        except Exception as e:
            logger.error(f"Error retrieving document by ID: {e}")
            raise

    async def create(self, document_data: DocumentCreate) -> Document:
        """
        Create a new document record.
        """
        try:
            # Convert Pydantic model to SQLAlchemy model
            document = Document(
                original_filename=document_data.original_filename,
                content_type=document_data.content_type,
                file_size=document_data.file_size,
                checksum_sha256=document_data.checksum_sha256,
                source_type=document_data.source_type,
                source_identifier=document_data.source_identifier,
                subsidiary=document_data.subsidiary,
                document_timestamp=document_data.document_timestamp,
                storage_reference=document_data.storage_reference,
                status=document_data.status
            )

            self.session.add(document)
            await self.session.commit()
            await self.session.refresh(document)

            logger.info(f"Created document record with ID: {document.id}")
            return document
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating document record: {e}")
            raise

    async def update_status(self, document_id: str, status: str) -> bool:
        """
        Update document status.
        """
        try:
            import uuid
            document_uuid = uuid.UUID(document_id)
            stmt = (
                update(Document)
                .where(Document.id == document_uuid)
                .values(status=status)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()

            if result.rowcount > 0:
                logger.info(f"Updated document {document_id} status to {status}")
                return True
            else:
                logger.warning(f"No document found with ID {document_id} to update")
                return False
        except ValueError:
            # Invalid UUID string
            logger.warning(f"Invalid UUID string for document ID: {document_id}")
            return False
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating document status: {e}")
            raise