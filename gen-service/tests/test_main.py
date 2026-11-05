import asyncio

import pytest
from fastapi import HTTPException

from app import main


def test_internal_token_required_when_configured(monkeypatch):
    monkeypatch.setattr(main.settings, "internal_api_token", "secret")
    with pytest.raises(HTTPException):
        asyncio.run(main.verify_internal_token("wrong"))
    with pytest.raises(HTTPException):
        asyncio.run(main.verify_internal_token(None))
    asyncio.run(main.verify_internal_token("secret"))  # correct token: no error


def test_internal_token_not_required_when_unset(monkeypatch):
    monkeypatch.setattr(main.settings, "internal_api_token", "")
    asyncio.run(main.verify_internal_token(None))  # local development: no error