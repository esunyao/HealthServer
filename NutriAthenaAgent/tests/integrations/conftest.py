from __future__ import annotations

import socket

import httpx
import pytest


@pytest.fixture(autouse=True)
def _offline_integrations(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("Integration adapter tests must use offline transports")

    async def reject_async_network(*args, **kwargs):
        reject_network()

    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket, "getaddrinfo", reject_network)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_async_network)
