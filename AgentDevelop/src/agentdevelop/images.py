"""Validate and encode user-selected local meal images for a vision model."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
        parts.append({"type": "text", "text": f"餐食图片 {index}（{image.path.name}）："})
        parts.append({"type": "image_url", "image_url": {"url": image.data_url}})
    return parts
