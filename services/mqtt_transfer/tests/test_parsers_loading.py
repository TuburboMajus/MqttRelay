"""Smoke tests for parser loading (``load_parse_function`` /
``load_parse_python_function``)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import services.mqtt_transfer.mqtt_transfer as mtt
from _helpers import parser_row


class FakeParsersDB:
    """Stand-in for the ``PARSERS_DB`` DirectoryStorage."""

    def __init__(self, present=()):
        self.present = set(present)
        self.directory = "/fake/parsers"
        self.calls = []

    def has(self, filename):
        self.calls.append(filename)
        return filename in self.present


def test_load_parse_function_unsupported_language():
    parser = parser_row(language="javascript")
    with pytest.raises(mtt.LanguageNotHandled):
        mtt.MqttTransfer.load_parse_function(parser)


def test_load_parse_python_function_missing_file_raises():
    parser = parser_row(name="Missing Parser", version="1.0.0")
    with patch.object(mtt, "PARSERS_DB", FakeParsersDB(present=())):
        with pytest.raises(mtt.ParserCodeNotFound):
            mtt.MqttTransfer.load_parse_python_function(parser)


def test_load_parse_python_function_derives_filename_and_returns_parse():
    parser = parser_row(name="LSE01 Soil", version="1.0.0")
    fake_parse = lambda data, **cfg: {"ok": True}  # noqa: E731
    fake_module = SimpleNamespace(parse=fake_parse)
    fake_importlib = SimpleNamespace(import_module=lambda name: fake_module)
    parsers_db = FakeParsersDB(present=("lse01_soil_1_0_0",))

    with patch.object(mtt, "PARSERS_DB", parsers_db), \
         patch.object(mtt, "importlib", fake_importlib):
        result = mtt.MqttTransfer.load_parse_python_function(parser)

    assert parsers_db.calls == ["lse01_soil_1_0_0"]
    assert result is fake_parse


def test_load_parse_function_python_delegates_to_python_loader():
    parser = parser_row(language="python")
    fake_parse = lambda data, **cfg: {}  # noqa: E731
    fake_module = SimpleNamespace(parse=fake_parse)
    fake_importlib = SimpleNamespace(import_module=lambda name: fake_module)
    parsers_db = FakeParsersDB(present=("lse01_soil_1_0_0",))

    with patch.object(mtt, "PARSERS_DB", parsers_db), \
         patch.object(mtt, "importlib", fake_importlib):
        result = mtt.MqttTransfer.load_parse_function(parser)

    assert result is fake_parse
