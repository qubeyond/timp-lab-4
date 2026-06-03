import secrets

import pytest
from pydantic import ValidationError

from src.config import Settings

# Полный набор обязательных полей, чтобы создать Settings без чтения .env.
_BASE = {"JWT_SECRET": secrets.token_hex(32)}


def _make(**overrides) -> Settings:
    return Settings(**{**_BASE, **overrides})


def test_debug_allows_weak_secret():
    # В dev-режиме слабый секрет допустим — иначе локальная разработка ломается.
    s = _make(DEBUG=True, JWT_SECRET="dev-secret-change-in-prod")
    assert s.jwt_secret == "dev-secret-change-in-prod"


def test_prod_rejects_default_placeholder():
    with pytest.raises(ValidationError):
        _make(DEBUG=False, JWT_SECRET="dev-secret-change-in-prod")


def test_prod_rejects_example_placeholder():
    with pytest.raises(ValidationError):
        _make(DEBUG=False, JWT_SECRET="change_me_to_a_random_64_char_string")


def test_prod_rejects_short_secret():
    with pytest.raises(ValidationError):
        _make(DEBUG=False, JWT_SECRET="too-short-secret")


def test_prod_accepts_strong_secret():
    strong = secrets.token_hex(32)  # 64 hex-символа = 64 байта
    s = _make(DEBUG=False, JWT_SECRET=strong)
    assert s.jwt_secret == strong
