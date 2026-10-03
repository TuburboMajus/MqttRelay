"""Smoke tests for the module-level functions of ``services/mqtt_transfer``:
``load_configs``, ``get_logger``, the job-guard helpers and ``launch``."""
import logging
import logging.handlers
from unittest.mock import MagicMock, patch

import pytest

import services.mqtt_transfer.mqtt_transfer as mtt
from _helpers import FakeStorage, rec


# --------------------------------------------------------------------------- #
# load_configs
# --------------------------------------------------------------------------- #
def test_load_configs_reads_toml(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[app]\nprod = true\n\n[storage.credentials]\nhost = "127.0.0.1"\nport = 3306\n'
    )
    config = mtt.load_configs(str(tmp_path))
    assert config["app"]["prod"] is True
    assert config["storage"]["credentials"]["host"] == "127.0.0.1"
    assert config["storage"]["credentials"]["port"] == 3306


def test_load_configs_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        mtt.load_configs(str(tmp_path))


def test_load_configs_invalid_toml_raises(tmp_path):
    (tmp_path / "config.toml").write_text("not [ valid toml")
    with pytest.raises(Exception):
        mtt.load_configs(str(tmp_path))


# --------------------------------------------------------------------------- #
# get_logger
# --------------------------------------------------------------------------- #
def _root():
    return logging.getLogger()


def _clear_root_handlers():
    for h in list(_root().handlers):
        _root().removeHandler(h)


def test_get_logger_adds_rotating_file_handler(tmp_path):
    # get_logger early-returns if the root logger already has handlers, so start clean
    _clear_root_handlers()
    before = set(_root().handlers)
    try:
        logger = mtt.get_logger(str(tmp_path))
        added = set(logger.handlers) - before
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in added)
        assert (tmp_path / "MqttTransfer.log").exists()
    finally:
        _clear_root_handlers()


def test_get_logger_none_dir_only_console(capsys):
    # start clean so get_logger does not early-return on leftover handlers
    _clear_root_handlers()
    try:
        logger = mtt.get_logger(None)
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
        assert not any(isinstance(h, logging.handlers.RotatingFileHandler)
                       for h in logger.handlers)
        assert "No valid logging directory" in capsys.readouterr().out
    finally:
        _clear_root_handlers()


def test_get_logger_is_idempotent(tmp_path):
    _clear_root_handlers()
    before = set(_root().handlers)
    try:
        first = mtt.get_logger(str(tmp_path))
        second = mtt.get_logger(str(tmp_path))
        assert first is second
    finally:
        _clear_root_handlers()


# --------------------------------------------------------------------------- #
# Job guard helpers
# --------------------------------------------------------------------------- #
def _job_row(state="IDLE", last_exit_code=0):
    from datetime import datetime
    return rec(name="MqttTransfer", state=state, last_exit_code=last_exit_code,
               last_state_update=datetime.now())


def _job_storage(rows=None):
    return FakeStorage("job", rows)


def test_get_or_create_job_creates_row_when_missing():
    storage = _job_storage()
    job = mtt._get_or_create_job(storage)
    assert job["name"] == "MqttTransfer"
    assert job["state"] == "IDLE"
    assert job["last_exit_code"] == 0
    assert job["last_state_update"] is not None
    assert storage.rows == [job]


def test_get_or_create_job_returns_existing_row():
    row = _job_row()
    storage = _job_storage([row])
    assert mtt._get_or_create_job(storage) is row
    assert storage.created == []


def test_already_running_false_when_idle():
    storage = _job_storage([_job_row()])
    with patch.object(mtt, "MysqlEntityStorage", return_value=storage):
        assert mtt.already_running(host="x") is False


def test_already_running_true_when_running():
    storage = _job_storage([_job_row(state="RUNNING")])
    with patch.object(mtt, "MysqlEntityStorage", return_value=storage):
        assert mtt.already_running() is True


def test_start_run_sets_state_running():
    storage = _job_storage([_job_row()])
    with patch.object(mtt, "MysqlEntityStorage", return_value=storage):
        mtt.start_run()
    assert storage.rows[0]["state"] == "RUNNING"
    assert storage.rows[0]["last_state_update"] is not None


def test_start_run_creates_row_when_missing():
    storage = _job_storage()
    with patch.object(mtt, "MysqlEntityStorage", return_value=storage):
        mtt.start_run()
    assert len(storage.rows) == 1
    assert storage.rows[0]["state"] == "RUNNING"
    assert storage.rows[0]["last_exit_code"] == 0


def test_stop_run_sets_idle_and_exit_code():
    storage = _job_storage([_job_row(state="RUNNING")])
    with patch.object(mtt, "MysqlEntityStorage", return_value=storage):
        mtt.stop_run(0)  # exit code 0 -> no sys.exit
    assert storage.rows[0]["state"] == "IDLE"
    assert storage.rows[0]["last_exit_code"] == 0


def test_stop_run_creates_row_when_missing():
    storage = _job_storage()
    with patch.object(mtt, "MysqlEntityStorage", return_value=storage):
        mtt.stop_run(0)
    assert len(storage.rows) == 1
    assert storage.rows[0]["state"] == "IDLE"
    assert storage.rows[0]["last_exit_code"] == 0


def test_stop_run_exits_on_nonzero():
    storage = _job_storage([_job_row()])
    with patch.object(mtt, "MysqlEntityStorage", return_value=storage):
        with pytest.raises(SystemExit) as excinfo:
            mtt.stop_run(3)
    assert excinfo.value.code == 3
    assert storage.rows[0]["last_exit_code"] == 3


# --------------------------------------------------------------------------- #
# launch
# --------------------------------------------------------------------------- #
def test_launch_postpones_when_already_running():
    with patch.object(mtt, "already_running", return_value=True) as already, \
         patch.object(mtt, "start_run") as start, \
         patch.object(mtt, "MqttTransfer") as transfer:
        result = mtt.launch({"storage": {"credentials": {"host": "x"}}})

    assert result is None
    already.assert_called_once_with(host="x")
    start.assert_not_called()
    transfer.assert_not_called()


def test_launch_success_returns_zero():
    fake = MagicMock()
    fake.process.return_value = True
    with patch.object(mtt, "already_running", return_value=False), \
         patch.object(mtt, "start_run"), \
         patch.object(mtt, "MqttTransfer", return_value=fake):
        result = mtt.launch({"storage": {"credentials": {"host": "x"}}})

    assert result == 0
    fake.process.assert_called_once_with()  # no leftover `directory` argument


def test_launch_partial_failure_returns_two():
    fake = MagicMock()
    fake.process.return_value = False
    with patch.object(mtt, "already_running", return_value=False), \
         patch.object(mtt, "start_run"), \
         patch.object(mtt, "MqttTransfer", return_value=fake):
        result = mtt.launch({"storage": {"credentials": {}}})

    assert result == 2
    fake.process.assert_called_once_with()
