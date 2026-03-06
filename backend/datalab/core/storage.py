"""
Storage utilities for Data Lab ResultSets.

Handles saving and loading Parquet files to/from S3.
"""
from __future__ import annotations

import logging
from io import BytesIO
from uuid import UUID

import boto3
import pandas as pd
from django.conf import settings

logger = logging.getLogger(__name__)


class DataLabStorage:
    """Utilities for storing ResultSets in S3 as Parquet."""
    
    BASE_PATH = "datalab/resultsets"
    THRESHOLD_ROWS = 10000  # Materialize if > 10k rows
    
    def __init__(self):
        """Initialize S3 client."""
        self.s3_client = boto3.client(
            's3',
            region_name=settings.AWS_S3_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.bucket_name = settings.AWS_STORAGE_MEDIA_BUCKET_NAME
    
    @staticmethod
    def get_resultset_key(resultset_id: UUID) -> str:
        """Generate S3 key for a ResultSet."""
        return f"{DataLabStorage.BASE_PATH}/{resultset_id}.parquet"
    
    def save_parquet(self, df: pd.DataFrame, resultset_id: UUID) -> str:
        """
        Save DataFrame as Parquet in S3.
        
        Args:
            df: DataFrame to save
            resultset_id: UUID of the ResultSet
            
        Returns:
            S3 key where the file was saved
            
        Raises:
            Exception: If S3 upload fails
        """
        key = self.get_resultset_key(resultset_id)
        
        try:
            # Convert DataFrame to Parquet bytes
            buffer = BytesIO()
            df.to_parquet(
                buffer,
                engine='pyarrow',
                compression='snappy',
                index=False
            )
            buffer.seek(0)
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                buffer,
                self.bucket_name,
                key,
                ExtraArgs={
                    'ContentType': 'application/octet-stream',
                    'ServerSideEncryption': 'AES256'
                }
            )
            
            logger.info(f"Saved ResultSet {resultset_id} to S3: {key}")
            return key
            
        except Exception as e:
            logger.error(f"Failed to save ResultSet {resultset_id} to S3: {e}")
            raise
    
    def load_parquet(self, resultset_id: UUID) -> pd.DataFrame:
        """
        Load Parquet from S3.
        
        Args:
            resultset_id: UUID of the ResultSet
            
        Returns:
            DataFrame loaded from Parquet
            
        Raises:
            Exception: If S3 download fails or file doesn't exist
        """
        key = self.get_resultset_key(resultset_id)
        
        try:
            # Download from S3
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            # Read Parquet from bytes
            buffer = BytesIO(response['Body'].read())
            df = pd.read_parquet(buffer, engine='pyarrow')
            
            logger.info(f"Loaded ResultSet {resultset_id} from S3: {key}")
            return df
            
        except self.s3_client.exceptions.NoSuchKey:
            logger.error(f"ResultSet {resultset_id} not found in S3: {key}")
            raise FileNotFoundError(f"ResultSet {resultset_id} not found in S3")
        except Exception as e:
            logger.error(f"Failed to load ResultSet {resultset_id} from S3: {e}")
            raise
    
    def delete_parquet(self, resultset_id: UUID) -> None:
        """
        Delete Parquet file from S3.
        
        Args:
            resultset_id: UUID of the ResultSet
            
        Raises:
            Exception: If S3 deletion fails
        """
        key = self.get_resultset_key(resultset_id)
        
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            logger.info(f"Deleted ResultSet {resultset_id} from S3: {key}")
        except Exception as e:
            logger.error(f"Failed to delete ResultSet {resultset_id} from S3: {e}")
            raise
    
    def exists(self, resultset_id: UUID) -> bool:
        """
        Check if Parquet file exists in S3.
        
        Args:
            resultset_id: UUID of the ResultSet
            
        Returns:
            True if file exists, False otherwise
        """
        key = self.get_resultset_key(resultset_id)
        
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return True
        except self.s3_client.exceptions.NoSuchKey:
            return False
        except Exception:
            return False


# Singleton instance
_storage_instance = None


def get_storage() -> DataLabStorage:
    """Get singleton DataLabStorage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = DataLabStorage()
    return _storage_instance
