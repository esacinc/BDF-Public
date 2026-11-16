import boto3
import botocore
import asyncio
from typing import Optional


class PreSignedS3Client:
    def __init__(
        self,
        bucket,
        region_name,
        aws_access_key_id,
        aws_secret_access_key,
        presigned_url_expiration=604800,
    ):
        self.bucket = bucket
        self.presigned_url_expiration = presigned_url_expiration
        self._s3 = boto3.client(
            "s3",
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

    async def upload_file(
        self,
        file_path: Optional[str] = None,
        object_key: str = "",
        mime: str = "",
        data: Optional[bytes] = None,
        overwrite: bool = True,
    ) -> dict[str, str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._upload_and_generate_url,
            file_path,
            object_key,
            mime,
            data,
            overwrite,
        )

    def _upload_and_generate_url(self, file_path, object_key, mime, data, overwrite):
        # Chainlit's data layer expects {"object_key": ..., "url": ...} from
        # upload_file (see chainlit/data/storage_clients/s3.py reference impl
        # and chainlit/data/dynamodb.py:create_element which writes both keys
        # onto the element row). If object_key is missing here, the DDB row
        # ends up with objectKey=None and on resume get_thread refreshes the
        # element URL via get_read_url(None) → returns None → plot disappears.
        if not overwrite:
            try:
                self._s3.head_object(Bucket=self.bucket, Key=object_key)
                return {
                    "object_key": object_key,
                    "url": self._s3.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": self.bucket, "Key": object_key},
                        ExpiresIn=self.presigned_url_expiration,
                    ),
                }
            except botocore.exceptions.ClientError:
                pass  # object doesn't exist yet, continue to upload

        if data:
            self._s3.put_object(
                Bucket=self.bucket, Key=object_key, Body=data, ContentType=mime
            )
        elif file_path:
            with open(file_path, "rb") as f:
                self._s3.upload_fileobj(
                    f, self.bucket, object_key, ExtraArgs={"ContentType": mime}
                )

        return {
            "object_key": object_key,
            "url": self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=self.presigned_url_expiration,
            ),
        }

    # ✅ New safe methods
    async def get_read_url(self, object_key: Optional[str] = None) -> Optional[str]:
        if not object_key:
            print("⚠️ get_read_url called with None object_key")
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=self.presigned_url_expiration,
            ),
        )

    async def get_write_url(self, object_key: Optional[str] = None) -> Optional[str]:
        if not object_key:
            print("⚠️ get_write_url called with None object_key")
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=self.presigned_url_expiration,
            ),
        )
