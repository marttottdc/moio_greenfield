# storage_backends.py
import os

import boto3
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

APP_NAME = os.environ.get("APP_NAME")
AWS_STORAGE_MEDIA_BUCKET_NAME = os.environ.get("AWS_STORAGE_MEDIA_BUCKET_NAME")
AWS_STORAGE_STATIC_BUCKET_NAME = os.environ.get("AWS_STORAGE_STATIC_BUCKET_NAME")


class StaticStorage(S3Boto3Storage):
    location = f'{APP_NAME}/static'
    bucket_name = AWS_STORAGE_STATIC_BUCKET_NAME
    default_acl = 'public-read'


class MediaStorage(S3Boto3Storage):
    location = f'{APP_NAME}/media'
    bucket_name = AWS_STORAGE_MEDIA_BUCKET_NAME
    file_overwrite = False
    default_acl = 'private'  #

    def url(self, name, parameters=None, expire=None):
        """
        Generates a presigned URL for S3 objects.
        The expiration time for the URL is specified in seconds.
        """
        # Ensure expiration is set, with a default of 1 day (60 seconds * 60 minutes * 24 hours)
        if expire is None:
            expire = 86400  # 1 day

        # Create a boto3 client for S3
        s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME,
                                 aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                                 aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)

        # Generate the presigned URL for getting the object

        name = f'{self.location}/{name}'

        presigned_url = s3_client.generate_presigned_url('get_object',
                                                         Params={'Bucket': settings.AWS_STORAGE_MEDIA_BUCKET_NAME,
                                                                 'Key': name},
                                                         ExpiresIn=expire)
        return presigned_url
