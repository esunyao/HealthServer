"""Validate and encode user-selected local meal images for a vision model."""

from __future__ import annotations

import base64
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

import httpx

from .config import MAX_MEAL_IMAGE_BYTES, MAX_MEAL_IMAGES, MAX_MEAL_TOTAL_IMAGE_BYTES

_SIGNATURES = (
    ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
)


class ImageInputError(ValueError):
    """An image is missing, unsupported, or exceeds configured safety limits."""


@dataclass(frozen=True)
class LocalImage:
    path: Path
    mime_type: str
    data: bytes

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class CapturedImage:
    """A bounded in-memory image fetched from an authorized capture URL."""

    name: str
    mime_type: str
    data: bytes

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"


def load_local_images(
    paths: Iterable[str | Path],
    *,
    max_images: int = MAX_MEAL_IMAGES,
    max_image_bytes: int = MAX_MEAL_IMAGE_BYTES,
    max_total_bytes: int = MAX_MEAL_TOTAL_IMAGE_BYTES,
) -> list[LocalImage]:
    ordered_paths = [Path(path).expanduser() for path in paths]
    if not ordered_paths:
        raise ImageInputError("至少需要一个本地图片文件")
    if len(ordered_paths) > max_images:
        raise ImageInputError(f"图片最多 {max_images} 张")

    images: list[LocalImage] = []
    total_bytes = 0
    for path in ordered_paths:
        try:
            if not path.is_file():
                raise ImageInputError(f"图片文件不存在或不是普通文件：{path}")
            size = path.stat().st_size
            if size <= 0:
                raise ImageInputError(f"图片文件为空：{path}")
            if size > max_image_bytes:
                raise ImageInputError(f"单张图片超过 {max_image_bytes // (1024 * 1024)} MiB：{path.name}")
            data = path.read_bytes()
        except OSError as exception:
            raise ImageInputError(f"无法读取图片文件：{path}") from exception

        if len(data) > max_image_bytes:
            raise ImageInputError(f"单张图片超过 {max_image_bytes // (1024 * 1024)} MiB：{path.name}")
        mime_type = next((mime for mime, matches in _SIGNATURES if matches(data)), None)
        if mime_type is None:
            raise ImageInputError(f"图片格式不支持或文件头无效：{path.name}（仅支持 JPEG、PNG、WebP）")
        total_bytes += len(data)
        if total_bytes > max_total_bytes:
            raise ImageInputError(f"图片总大小超过 {max_total_bytes // (1024 * 1024)} MiB")
        images.append(LocalImage(path=path.resolve(), mime_type=mime_type, data=data))
    return images


def image_message_parts(images: Iterable[LocalImage]) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = []
    for index, image in enumerate(images, start=1):
        parts.append({"type": "text", "text": f"餐食图片 {index}（{image.name}）："})
        parts.append({"type": "image_url", "image_url": {"url": image.data_url}})
    return parts


def _validate_capture_url(url: str, allowed_hosts: frozenset[str]) -> str:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        scheme = parsed.scheme.lower()
        port = parsed.port
        if parsed.username or parsed.password or parsed.fragment or not host:
            raise ValueError
        if scheme not in {"https", "http"} or host not in allowed_hosts:
            raise ValueError
        if scheme == "https" and port not in {None, 443}:
            raise ValueError
        if scheme == "http":
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = host == "localhost"
            if not loopback:
                raise ValueError
    except (TypeError, ValueError) as exception:
        raise ImageInputError("授权餐食图片地址不符合允许的传输规则") from exception
    return host


async def load_captured_images(
    image_urls: object,
    *,
    allowed_hosts: frozenset[str],
    max_images: int = MAX_MEAL_IMAGES,
    max_image_bytes: int = MAX_MEAL_IMAGE_BYTES,
    max_total_bytes: int = MAX_MEAL_TOTAL_IMAGE_BYTES,
    client: httpx.AsyncClient | None = None,
) -> list[CapturedImage]:
    """Fetch only MCP-authorized signed URLs using a strict allowlist and limits.

    URLs and transport errors are deliberately absent from returned messages so
    signed credentials cannot leak into model context or logs.
    """
    if not isinstance(image_urls, list) or not image_urls:
        return []
    if len(image_urls) > max_images:
        raise ImageInputError(f"授权图片超过 {max_images} 张")
    if not allowed_hosts:
        raise ImageInputError("未配置授权图片下载主机白名单")
    own_client = client is None
    session = client or httpx.AsyncClient(timeout=20, follow_redirects=False)
    images: list[CapturedImage] = []
    total_bytes = 0
    try:
        for index, item in enumerate(image_urls, start=1):
            url = item.get("url") if isinstance(item, dict) else None
            if not isinstance(url, str) or not url:
                raise ImageInputError("授权餐食图片记录缺少可下载地址")
            _validate_capture_url(url, allowed_hosts)
            try:
                async with session.stream("GET", url) as response:
                    if response.is_redirect:
                        raise ImageInputError("授权图片下载不接受重定向")
                    response.raise_for_status()
                    declared_size = response.headers.get("content-length")
                    if declared_size is not None:
                        try:
                            parsed_size = int(declared_size)
                        except ValueError as exception:
                            raise ImageInputError("授权图片长度标头无效") from exception
                        if parsed_size > max_image_bytes:
                            raise ImageInputError("授权图片超过单张大小限制")
                    declared_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > max_image_bytes:
                            raise ImageInputError("授权图片超过单张大小限制")
            except ImageInputError:
                raise
            except httpx.HTTPError as exception:
                raise ImageInputError("授权餐食图片下载失败") from exception
            data = bytes(chunks)
            detected_type = next((mime for mime, matches in _SIGNATURES if matches(data)), None)
            if detected_type is None or declared_type not in {detected_type, "application/octet-stream"}:
                raise ImageInputError("授权图片内容不是受支持的 JPEG、PNG 或 WebP")
            total_bytes += len(data)
            if total_bytes > max_total_bytes:
                raise ImageInputError("授权餐食图片总大小超过限制")
            images.append(CapturedImage(name=f"image-{index}.{detected_type.split('/')[-1]}", mime_type=detected_type, data=data))
    finally:
        if own_client:
            await session.aclose()
    return images
