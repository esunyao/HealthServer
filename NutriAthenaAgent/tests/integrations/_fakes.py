"""Shared synthetic context and tool doubles; no project configuration loading."""

from __future__ import annotations

from typing import Any

TASK_ID = "11111111-1111-4111-8111-111111111111"
ATTEMPT_ID = "22222222-2222-4222-8222-222222222222"


def capture_payload(*, notes: str | None = None, include_notes: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "capture_session_id": "33333333-3333-4333-8333-333333333333",
        "meal_id": 42,
        "meal_type": "lunch",
        "consumed_at": "2026-10-26T12:30:00+08:00",
        "timezone": "Asia/Shanghai",
        "image_urls": [
            {
                "content_type": "image/jpeg",
                "content_length": 128,
                "captured_at": "2026-10-26T12:29:00+08:00",
                "url": "https://media.example.test/signed",
                "expires_in_seconds": 300,
            },
        ],
    }
    if include_notes:
        payload["notes"] = notes
    return payload


def capture_context_payload(*, url: str = "https://media.example.test/photo") -> dict[str, Any]:
    payload = capture_payload(notes="米饭约半碗")
    payload["image_urls"][0]["url"] = url
    return payload


class FakeMcpTool:
    def __init__(self, name: str, result: Any):
        self.name = name
        self.result = result
        self.calls: list[dict[str, str]] = []
        self.metadata: list[dict[str, str]] = []

    async def ainvoke(self, arguments):
        self.calls.append(arguments.get("args", arguments))
        self.metadata.append(arguments.get("_meta", {}))
        return self.result
