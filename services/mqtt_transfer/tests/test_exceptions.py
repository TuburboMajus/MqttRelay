"""Smoke tests for every exception class defined in ``services/mqtt_transfer``."""
import pytest

import services.mqtt_transfer.mqtt_transfer as mtt

EXCEPTION_NAMES = [
    "TopicNotFound",
    "DeviceNotFound",
    "ClientNotFound",
    "MetricNotFound",
    "ParserCodeNotFound",
    "DeviceTypeNotFound",
    "NoRouteFound",
    "DispatcherNotFound",
    "DepositNotFound",
    # fixed: previously raised but never declared
    "DisabledTopic",
    "LanguageNotHandled",
    "DestinationNotFound",
]


@pytest.mark.parametrize("name", EXCEPTION_NAMES)
def test_exception_is_defined_and_subclasses_exception(name):
    cls = getattr(mtt, name)
    assert isinstance(cls, type)
    assert issubclass(cls, Exception)


@pytest.mark.parametrize("name", EXCEPTION_NAMES)
def test_exception_can_be_raised_with_message(name):
    cls = getattr(mtt, name)
    with pytest.raises(cls, match="smoke"):
        raise cls("smoke failure")
