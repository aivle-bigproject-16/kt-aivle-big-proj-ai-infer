import httpx
import pytest

import downloader


def _transport(*, body: bytes, content_type: str = "image/png", status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"content-type": content_type},
            content=body,
            request=request,
        )

    return httpx.MockTransport(handler)


def test_download_image_returns_image_bytes(monkeypatch):
    transport = _transport(body=b"image-bytes")
    original_client = httpx.Client
    monkeypatch.setattr(
        downloader.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    assert downloader.download_image("https://storage.example/image.png") == b"image-bytes"


def test_download_image_rejects_non_image_content(monkeypatch):
    transport = _transport(body=b"not-an-image", content_type="text/plain")
    original_client = httpx.Client
    monkeypatch.setattr(
        downloader.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(downloader.ImageDownloadError, match="unexpected content type"):
        downloader.download_image("https://storage.example/file.txt")


def test_download_image_rejects_oversized_body(monkeypatch):
    transport = _transport(body=b"x" * 5)
    original_client = httpx.Client
    monkeypatch.setattr(downloader, "MAX_IMAGE_BYTES", 4)
    monkeypatch.setattr(
        downloader.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(downloader.ImageDownloadError, match="maximum allowed size"):
        downloader.download_image("https://storage.example/large.png")


@pytest.mark.parametrize("url", ["file:///tmp/image.png", "not-a-url"])
def test_download_image_rejects_unsupported_urls(url):
    with pytest.raises(downloader.ImageDownloadError):
        downloader.download_image(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/image.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/image.png",
        "http://192.168.1.20/image.png",
        "http://[::1]/image.png",
    ],
)
def test_download_image_rejects_internal_addresses(url):
    with pytest.raises(
        downloader.ImageDownloadError,
        match="non-public address",
    ):
        downloader.download_image(url)


def test_download_image_rejects_hostnames_resolving_internally(monkeypatch):
    monkeypatch.setattr(
        downloader,
        "_resolved_addresses",
        lambda hostname: ["169.254.169.254"],
    )

    with pytest.raises(
        downloader.ImageDownloadError,
        match="non-public address",
    ):
        downloader.download_image("https://metadata.example/image.png")


def test_download_image_allows_unresolvable_hostnames(monkeypatch):
    transport = _transport(body=b"image-bytes")
    original_client = httpx.Client
    monkeypatch.setattr(downloader, "_resolved_addresses", lambda hostname: [])
    monkeypatch.setattr(
        downloader.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    assert (
        downloader.download_image("https://storage.example/image.png")
        == b"image-bytes"
    )
