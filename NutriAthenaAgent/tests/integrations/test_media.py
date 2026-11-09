from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from nutriathena_agent.integrations.media import (
    CapturedImage,
    ImageInputError,
    image_message_parts,
    load_captured_images,
    load_local_images,
)


def test_local_image_empty_missing_and_total_limits(tmp_path):
    with pytest.raises(ImageInputError, match="至少需要"):
        load_local_images([])
    with pytest.raises(ImageInputError, match="不存在"):
        load_local_images([tmp_path / "missing.jpg"])
    empty = tmp_path / "empty.jpg"
    empty.touch()
    with pytest.raises(ImageInputError, match="为空"):
        load_local_images([empty])
    valid = tmp_path / "valid.jpg"
    valid.write_bytes(b"\xff\xd8\xffdata")
    with pytest.raises(ImageInputError, match="总大小"):
        load_local_images([valid, valid], max_total_bytes=13)


def test_local_read_failure_keeps_the_original_cause(tmp_path, monkeypatch):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"\xff\xd8\xffdata")
    error = OSError("offline read failure")

    def fail_read(path):
        raise error

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(ImageInputError, match="无法读取") as caught:
        load_local_images([image])
    assert caught.value.__cause__ is error


@pytest.mark.parametrize(
    "content,mime",
    [
        (b"\xff\xd8\xffimage", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\nimage", "image/png"),
        (b"RIFFabcdWEBPimage", "image/webp"),
    ],
)
def test_both_image_sources_detect_jpeg_png_and_webp_from_signatures(tmp_path, content, mime):
    path = tmp_path / "image.any-extension"
    path.write_bytes(content)
    assert load_local_images([path])[0].mime_type == mime

    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=content)
        )) as client:
            return await load_captured_images(
                [{"url": "https://media.example.test/image"}],
                allowed_hosts=frozenset({"media.example.test"}), client=client,
            )

    assert asyncio.run(load())[0].mime_type == mime


def test_redirects_are_rejected_even_if_the_supplied_client_follows_them():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://unapproved.example.test/image"})

    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            return await load_captured_images(
                [{"url": "https://media.example.test/signed?token=hidden"}],
                allowed_hosts=frozenset({"media.example.test"}), client=client,
            )

    with pytest.raises(ImageInputError, match="重定向"):
        asyncio.run(load())
    assert len(requests) == 1


@pytest.mark.parametrize(
    "urls,hosts,options,message",
    [
        ([{}], frozenset({"*"}), {}, "缺少"),
        (["https://media.example.test/image"], frozenset({"*"}), {}, "缺少"),
        ([{"url": "https://media.example.test/image"}], frozenset(), {}, "白名单"),
        ([{}, {}], frozenset({"*"}), {"max_images": 1}, "超过 1 张"),
    ],
)
def test_capture_input_limits_fail_before_transport(urls, hosts, options, message):
    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: pytest.fail("Invalid inputs must not reach transport")
        )) as client:
            return await load_captured_images(urls, allowed_hosts=hosts, client=client, **options)

    with pytest.raises(ImageInputError, match=message):
        asyncio.run(load())


@pytest.mark.parametrize("urls", [None, [], "not-a-list", {}])
def test_no_capture_images_returns_an_empty_list(urls):
    assert asyncio.run(load_captured_images(urls, allowed_hosts=frozenset())) == []


@pytest.mark.parametrize(
    "content_type,declared_length,content,limit,message",
    [
        ("image/jpeg", "not-a-number", b"\xff\xd8\xffok", 100, "标头"),
        ("image/jpeg", "101", b"\xff\xd8\xffok", 100, "大小"),
        ("image/jpeg", None, b"not an image", 100, "内容"),
        ("text/html", None, b"\xff\xd8\xffok", 100, "内容"),
    ],
)
def test_capture_headers_and_signatures_are_checked(content_type, declared_length, content, limit, message):
    headers = {"content-type": content_type}
    if declared_length is not None:
        headers["content-length"] = declared_length

    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers=headers, content=content)
        )) as client:
            return await load_captured_images(
                [{"url": "https://media.example.test/image?token=hidden"}],
                allowed_hosts=frozenset({"media.example.test"}), max_image_bytes=limit, client=client,
            )

    with pytest.raises(ImageInputError, match=message) as caught:
        asyncio.run(load())
    assert "hidden" not in str(caught.value)


def test_streamed_body_cannot_bypass_the_size_limit_without_a_length_header():
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"\xff\xd8\xfffirst"
            yield b"second-chunk"

    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "image/jpeg"}, stream=Chunks())
        )) as client:
            return await load_captured_images(
                [{"url": "https://media.example.test/image"}],
                allowed_hosts=frozenset({"media.example.test"}), max_image_bytes=10, client=client,
            )

    with pytest.raises(ImageInputError, match="单张大小"):
        asyncio.run(load())


def test_capture_total_byte_limit_covers_all_images():
    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8\xffdata")
        )) as client:
            return await load_captured_images(
                [{"url": "https://media.example.test/one"}, {"url": "https://media.example.test/two"}],
                allowed_hosts=frozenset({"media.example.test"}), max_total_bytes=13, client=client,
            )

    with pytest.raises(ImageInputError, match="总大小"):
        asyncio.run(load())


@pytest.mark.parametrize(
    "url",
    [
        "https://media.example.test/image#fragment",
        "file:///image",
        "ftp://media.example.test/image",
        "https://media.example.test:invalid/image",
        "https://media.example.test.evil/image",
    ],
)
def test_capture_url_restrictions_reject_fragments_schemes_ports_and_other_hosts(url):
    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: pytest.fail("Invalid URL must not reach transport")
        )) as client:
            return await load_captured_images(
                [{"url": url}], allowed_hosts=frozenset({"media.example.test"}), client=client,
            )

    with pytest.raises(ImageInputError, match="地址"):
        asyncio.run(load())


@pytest.mark.parametrize("url", ["http://localhost:8101/image", "http://127.0.0.1/image", "http://[::1]/image"])
def test_http_loopback_remains_available_for_test_media_transports(url):
    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8\xffdata")
        )) as client:
            return await load_captured_images([{"url": url}], allowed_hosts=frozenset({"*"}), client=client)

    assert len(asyncio.run(load())) == 1


def test_download_failure_keeps_cause_and_leaves_supplied_client_open():
    error = httpx.ConnectError("offline download failure https://media.example.test/image?token=hidden")

    def fail_transport(request):
        raise error

    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail_transport)) as client:
            with pytest.raises(ImageInputError, match="下载失败") as caught:
                await load_captured_images(
                    [{"url": "https://media.example.test/image?token=hidden"}],
                    allowed_hosts=frozenset({"media.example.test"}), client=client,
                )
            assert not client.is_closed
            assert caught.value.__cause__ is error
            assert "hidden" not in str(caught.value)

    asyncio.run(load())


def test_local_images_preserve_order_and_encode_supported_types(tmp_path):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.png"
    first.write_bytes(b"\xff\xd8\xfffirst")
    second.write_bytes(b"\x89PNG\r\n\x1a\nsecond")

    images = load_local_images([first, second])
    parts = image_message_parts(images)

    assert [image.path.name for image in images] == ["first.jpg", "second.png"]
    assert [image.mime_type for image in images] == ["image/jpeg", "image/png"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert parts[3]["image_url"]["url"].startswith("data:image/png;base64,")


def test_local_images_reject_invalid_format_and_limits(tmp_path):
    invalid = tmp_path / "fake.jpg"
    invalid.write_bytes(b"not an image")
    with pytest.raises(ImageInputError, match="格式不支持"):
        load_local_images([invalid])

    valid = tmp_path / "large.jpg"
    valid.write_bytes(b"\xff\xd8\xffdata")
    with pytest.raises(ImageInputError, match="单张图片超过"):
        load_local_images([valid], max_image_bytes=4)

    with pytest.raises(ImageInputError, match="最多 1 张"):
        load_local_images([valid, valid], max_images=1)


def test_authorized_capture_images_are_downloaded_in_memory_with_limits():
    content = b"\xff\xd8\xffmeal-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "media.example.test"
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=content)

    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
            return await load_captured_images(
                [{"url": "https://media.example.test/signed?token=never-log"}],
                allowed_hosts=frozenset({"media.example.test"}),
                client=client,
            )

    images = asyncio.run(load())
    assert images == [CapturedImage(name="image-1.jpeg", mime_type="image/jpeg", data=content)]
    parts = image_message_parts(images)
    assert "signed" not in json.dumps(parts)
    assert "never-log" not in json.dumps(parts)


@pytest.mark.parametrize(
    "url,allowed_hosts,headers,content,max_bytes,message",
    [
        ("https://attacker.test/picture?token=secret", frozenset({"media.example.test"}), {}, b"\xff\xd8\xffok", 100, "地址"),
        ("https://media.example.test/picture?token=secret", frozenset({"media.example.test"}), {"content-type": "image/png"}, b"\xff\xd8\xffok", 100, "内容"),
        ("https://media.example.test/picture?token=secret", frozenset({"media.example.test"}), {"content-type": "image/jpeg"}, b"\xff\xd8\xffoversize", 4, "大小"),
    ],
)
def test_authorized_capture_images_fail_closed(url, allowed_hosts, headers, content, max_bytes, message):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, content=content)

    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
            return await load_captured_images(
                [{"url": url}],
                allowed_hosts=allowed_hosts,
                max_image_bytes=max_bytes,
                client=client,
            )

    with pytest.raises(ImageInputError, match=message) as captured:
        asyncio.run(load())
    assert "secret" not in str(captured.value)


@pytest.mark.parametrize(
    "url,allowed_hosts",
    [
        ("https://media.example.test:8444/photo", frozenset({"media.example.test"})),
        ("https://api.lovedage.test:8444/photo", frozenset({"*.lovedage.test"})),
        ("https://deep.api.lovedage.test:65535/photo", frozenset({"*.lovedage.test"})),
        ("https://arbitrary.example:1234/photo", frozenset({"*"})),
    ],
)
def test_authorized_capture_images_accept_wildcard_hosts_and_https_ports(url, allowed_hosts):
    content = b"\xff\xd8\xffimage"

    async def load():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, headers={"content-type": "image/jpeg"}, content=content)
            )
        ) as client:
            return await load_captured_images([{"url": url}], allowed_hosts=allowed_hosts, client=client)

    assert asyncio.run(load())[0].data == content


@pytest.mark.parametrize(
    "url,allowed_hosts",
    [
        ("https://lovedage.test/photo", frozenset({"*.lovedage.test"})),
        ("https://evil-lovedage.test/photo", frozenset({"*.lovedage.test"})),
        ("http://api.lovedage.test:8444/photo", frozenset({"*"})),
        ("https://user:password@api.lovedage.test/photo", frozenset({"*"})),
        ("https://api.lovedage.test:65536/photo", frozenset({"*"})),
    ],
)
def test_authorized_capture_images_preserve_url_restrictions(url, allowed_hosts):
    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
            return await load_captured_images([{"url": url}], allowed_hosts=allowed_hosts, client=client)

    with pytest.raises(ImageInputError, match="地址"):
        asyncio.run(load())


def test_authorized_capture_image_rejects_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://other.example.test/image"})

    async def load():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
            return await load_captured_images(
                [{"url": "https://media.example.test/signed?token=secret"}],
                allowed_hosts=frozenset({"media.example.test"}),
                client=client,
            )

    with pytest.raises(ImageInputError, match="重定向"):
        asyncio.run(load())
