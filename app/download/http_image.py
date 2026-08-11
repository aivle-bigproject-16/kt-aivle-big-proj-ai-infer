import ipaddress
import os
import socket
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


def _resolved_addresses(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # 이름을 못 풀면 여기서 판단하지 않는다. 실제 연결에서 실패한다.
        return []

    return [info[4][0] for info in infos]


def _reject_internal_hosts(hostname: str) -> None:
    """사내망·메타데이터 엔드포인트로 향하는 요청을 막는다.

    image_url 은 BE 가 발급한 presigned URL 이지만, 서버가 임의 URL 을 그대로
    가져오는 구조라 SSRF 통로가 된다. 리다이렉트는 이미 꺼져 있다.
    """
    candidates = [hostname, *_resolved_addresses(hostname)]

    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue

        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ImageDownloadError(
                "image_url resolves to a non-public address"
            )


def download_image(image_url: str) -> bytes:
    parsed = urlparse(image_url)

    if parsed.scheme not in {"http", "https"}:
        raise ImageDownloadError("image_url must use http or https")

    if not parsed.hostname:
        raise ImageDownloadError("image_url must contain a hostname")

    _reject_internal_hosts(parsed.hostname)

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