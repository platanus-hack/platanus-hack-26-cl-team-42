"""Unit tests for the uncouple configuration library.

These exercise environment-variable loading in isolation, focusing on the
``InsecureDefault`` marker: it should provide a working fallback while warning,
defer to a real environment value when present, and become fatal when
``UNCOUPLE_REQUIRE_SECURE`` is set.
"""

from __future__ import annotations

import warnings

import pytest

from uncouple import (
    Config,
    InsecureConfigError,
    InsecureDefault,
    InsecureDefaultWarning,
)


class SampleConfig(Config):
    SECRET_KEY: str = InsecureDefault("dev-key")
    PLAIN: str = "plain-default"


def test_insecure_default_used_when_unset(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    monkeypatch.delenv("UNCOUPLE_REQUIRE_SECURE", raising=False)

    with pytest.warns(InsecureDefaultWarning, match="DJANGO_SECRET_KEY"):
        cfg = SampleConfig.load(prefix="DJANGO")

    assert cfg.SECRET_KEY == "dev-key"


def test_environment_value_overrides_without_warning(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "from-env")
    monkeypatch.delenv("UNCOUPLE_REQUIRE_SECURE", raising=False)

    with warnings.catch_warnings():
        warnings.simplefilter("error", InsecureDefaultWarning)
        cfg = SampleConfig.load(prefix="DJANGO")

    assert cfg.SECRET_KEY == "from-env"


def test_require_secure_rejects_insecure_default(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    monkeypatch.setenv("UNCOUPLE_REQUIRE_SECURE", "1")

    with pytest.raises(InsecureConfigError) as excinfo:
        SampleConfig.load(prefix="DJANGO")

    assert excinfo.value.keys == ["DJANGO_SECRET_KEY"]


def test_require_secure_allows_explicit_value(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "from-env")
    monkeypatch.setenv("UNCOUPLE_REQUIRE_SECURE", "1")

    cfg = SampleConfig.load(prefix="DJANGO")

    assert cfg.SECRET_KEY == "from-env"
