"""Pytest fixtures for the ``services/mqtt_transfer`` smoke tests."""
import pytest

from _helpers import FakeAsyncDispatcher, FakeDispatcher, build_instance


@pytest.fixture
def instance():
    """A ``MqttTransfer`` instance with all storages replaced by fakes."""
    return build_instance()


@pytest.fixture(autouse=True)
def _reset_fake_dispatcher_state():
    """Keep class-level fake-dispatcher instance lists clean between tests."""
    FakeDispatcher.instances = []
    FakeAsyncDispatcher.instances = []
    yield
    FakeDispatcher.instances = []
    FakeAsyncDispatcher.instances = []
