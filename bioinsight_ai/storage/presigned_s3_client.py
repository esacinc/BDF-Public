import boto3
import botocore
import asyncio
from typing import Optional


class PreSignedS3Client:
    def __init__(self, bucket, region_name, aws_access_key_id, aws_secret_access_key, presigned_url_expiration=604800):
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
        overwrite: bool = True
    ) -> dict[str, str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._upload_and_generate_url, file_path, object_key, mime, data, overwrite)

    def _upload_and_generate_url(self, file_path, object_key, mime, data, overwrite):
        if not overwrite:
            try:
                self._s3.head_object(Bucket=self.bucket, Key=object_key)
                return {
                    "url": self._s3.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': self.bucket, 'Key': object_key},
                        ExpiresIn=self.presigned_url_expiration,
                    )
                }
            except botocore.exceptions.ClientError:
                pass  # object doesn't exist yet, continue to upload

        if data:
            self._s3.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=data,
                ContentType=mime
            )
        elif file_path:
            with open(file_path, "rb") as f:
                self._s3.upload_fileobj(f, self.bucket, object_key, ExtraArgs={"ContentType": mime})

        return {
            "url": self._s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': object_key},
                ExpiresIn=self.presigned_url_expiration,
            )
        }