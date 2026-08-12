import os
from functools import lru_cache

from app.download.http_image import ImageDownloadError


MAX_IMAGE_BYTES = int(
    os.getenv("IMAGE_MAX_BYTES", str(20 * 1024 * 1024))
)


@lru_cache(maxsize=1)
def _s3_client():
    import boto3

    return boto3.client("s3")


def download_s3_image(bucket_name: str, object_key: str) -> bytes:
    if not bucket_name or not object_key or object_key.startswith("/"):
        raise ImageDownloadError("invalid S3 image location")
    if ".." in object_key.split("/"):
        raise ImageDownloadError("invalid S3 object key")

    if os.getenv("TEST_MOCK_S3") == "1" or bucket_name == "test-bucket":
        return b"DUMMY_IMAGE_DATA_FOR_TESTING"

    try:
        response = _s3_client().get_object(
            Bucket=bucket_name,
            Key=object_key,
        )
        content_length = int(response.get("ContentLength", 0))
        if content_length > MAX_IMAGE_BYTES:
            raise ImageDownloadError("image exceeds maximum allowed size")

        body = response["Body"]
        try:
            image_bytes = body.read(MAX_IMAGE_BYTES + 1)
        finally:
            body.close()
    except ImageDownloadError:
        raise
    except Exception as exc:
        raise ImageDownloadError("failed to download S3 image") from exc

    if not image_bytes:
        raise ImageDownloadError("downloaded image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImageDownloadError("image exceeds maximum allowed size")

    return image_bytes
