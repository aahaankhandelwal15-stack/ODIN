import uuid
import aiofiles
from typing import BinaryIO, Union
import boto3
from botocore.exceptions import ClientError
from app.storage.base import StorageBackend
from app.core.config import get_settings
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


class S3CompatibleStorageBackend(StorageBackend):
    def __init__(self):
        settings = get_settings()
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        self.endpoint_url = settings.AWS_S3_ENDPOINT_URL
        self.aws_access_key_id = settings.AWS_ACCESS_KEY_ID
        self.aws_secret_access_key = settings.AWS_SECRET_ACCESS_KEY
        self.region = settings.AWS_REGION

        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region
        )

    async def store_file(
        self,
        file_data: Union[BinaryIO, bytes],
        file_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Store file data in S3 and return the object key.
        Uses UUID as key to ensure uniqueness and prevent overwrites.
        """
        # Generate a unique key (UUID)
        file_id = str(uuid.uuid4())

        try:
            # Convert file_data to bytes if it's not already
            if isinstance(file_data, bytes):
                data = file_data
                file_obj = BytesIO(data)
            else:
                # Assume it's a file-like object
                # Reset file pointer to beginning if needed
                if hasattr(file_data, "seek"):
                    file_data.seek(0)
                file_obj = file_data

            # Upload file to S3
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                file_id,
                ExtraArgs={
                    'ContentType': content_type
                }
            )

            logger.info(f"Stored file {file_id} in S3 bucket {self.bucket_name}")
            return file_id

        except ClientError as e:
            logger.error(f"Failed to store file in S3: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing file in S3: {e}")
            raise

    async def retrieve_file(self, file_path: str) -> BinaryIO:
        """
        Retrieve file from S3 by object key.
        Returns an async file-like object.
        """
        try:
            # Get object from S3
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=file_path
            )

            # Return the body (which is a streaming body)
            return response['Body']

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"File not found in S3: {file_path}")
            else:
                logger.error(f"Failed to retrieve file from S3: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving file from S3: {e}")
            raise

    async def delete_file(self, file_path: str) -> None:
        """
        Delete file from S3 by object key.
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            logger.info(f"Deleted file {file_path} from S3 bucket {self.bucket_name}")
        except ClientError as e:
            logger.error(f"Failed to delete file from S3: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting file from S3: {e}")
            raise

    async def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists in S3.
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logger.error(f"Error checking file existence in S3: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error checking file existence in S3: {e}")
            raise