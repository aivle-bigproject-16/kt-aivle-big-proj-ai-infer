import os
from urllib.parse import urlparse

import httpx


DOWNLOAD_TIMEOUT_SECONDS = float(
    os.getenv("IMAGE_DOWNLOAD_TIMEOUT_SECONDS", "10")
)
MAX_IMAGE_BYTES = int(
    os.getenv("IMAGE_MAX_BYTES", str(20 * 1024 * 1024))
)


class ImageDownloadError(RuntimeError):
    pass


def download_image(image_url: str) -> bytes:
    parsed = urlparse(image_url)

    if parsed.scheme not in {"http", "https"}:
        raise ImageDownloadError("image_url must use http or https")

    if not parsed.hostname:
        raise ImageDownloadError("image_url must contain a hostname")

    try:
        with httpx.Client(
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            with client.stream("GET", image_url) as response:
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if not content_type.lower().startswith("image/"):
                    raise ImageDownloadError(
                        f"unexpected content type: {content_type}"
                    )

                chunks = []
                total_bytes = 0

                for chunk in response.iter_bytes():
                    total_bytes += len(chunk)

                    if total_bytes > MAX_IMAGE_BYTES:
                        raise ImageDownloadError(
                            "image exceeds maximum allowed size"
                        )

                    chunks.append(chunk)

                if total_bytes == 0:
                    raise ImageDownloadError("downloaded image is empty")

                return b"".join(chunks)

    except httpx.HTTPError as exc:
        raise ImageDownloadError("failed to download image") from exc