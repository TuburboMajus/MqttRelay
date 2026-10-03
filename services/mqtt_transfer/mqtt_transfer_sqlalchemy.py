# mqtt_transfer.py - Background worker for processing MQTT messages (SQLAlchemy version)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

from core.repository import repos, Repository, get_session
from core.models import (
    MqttMessage, MqttTopic, Device, Client, Parser, Metric, ParsedPoint, Extraction,
    RoutingRule, RouteDeposit, Dispatch, ClientDestination, Job
)
from core.db import init_db
from core.crypto import get_key_bytes
from context import init_context, PARSERS_DB
from tools.json_conditions import eval_mongo_dsl
from tools.crypto_envelopes import decrypt_data
from services.mqtt_transfer.dispatchers import DISPATCHERS

from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import importlib
import traceback
import argparse
import logging
import math
import toml
import yaml
import time
import json


MQTTT_JOB_NAME = "MqttTransfer"
MQTTT_LOG_NAME = "mqttt"


# Function to load configuration from TOML file
def load_configs(root_dir):
    """Load configuration from config.toml file in the specified root directory"""
    with open(os.path.join(root_dir, "config.toml")) as config_file:
        config = toml.load(config_file)
    return config


# Function to set up logging
def get_logger(logging_dir):
    """Create and configure a logger with file and console handlers"""
    if logging_dir is not None:
        os.makedirs(logging_dir, exist_ok=True)

    logger = logging.getLogger(MQTTT_LOG_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Set up log message format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Configure file handler if logging directory is valid
    if logging_dir is not None and os.path.isdir(logging_dir):
        fh = RotatingFileHandler(
            os.path.join(logging_dir, f"{MQTTT_JOB_NAME}.log"),
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    else:
        print("No valid logging directory specified. No logs will be kept.")

    # Configure console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# Exceptions
class TopicNotFound(Exception):
    pass


class DeviceNotFound(Exception):
    pass


class ClientNotFound(Exception):
    pass


class MetricNotFound(Exception):
    pass


class ParserCodeNotFound(Exception):
    pass


class DeviceTypeNotFound(Exception):
    pass


class NoRouteFound(Exception):
    pass


class DispatcherNotFound(Exception):
    pass


class DepositNotFound(Exception):
    pass


class DisabledTopic(Exception):
    pass


class LanguageNotHandled(Exception):
    pass


class DestinationNotFound(Exception):
    pass


class MqttTransfer(object):
    """Process unprocessed MQTT messages into time-series points."""

    def __init__(self):
        super().__init__()
        self.metrics_cache = {}
        self.device_types_cache = {}
        self._crypto_config = None

    def clear_caches(self):
        """Drop per-cycle caches so dashboard edits are picked up by this long-running worker."""
        self.metrics_cache.clear()
        self.device_types_cache.clear()
        self._crypto_config = None

    def load_parse_python_function(self, parser):
        """Load a Python parser function from the file system."""
        filename = "_".join([
            parser.name.lower().replace(" ", "_"),
            parser.version.lower().replace(".", "_")
        ])
        
        if not PARSERS_DB.has(filename):
            raise ParserCodeNotFound(
                f"Parser #{parser.id} code not found (should exist at {PARSERS_DB.base_path}/{filename}.py)"
            )

        # Reload if already imported: this worker is long-running, and parser
        # code can be edited from the dashboard between cycles.
        module_name = f"db.parsers.{filename}"
        if module_name in sys.modules:
            module = importlib.reload(sys.modules[module_name])
        else:
            module = importlib.import_module(module_name)
        return module.parse

    def load_parse_function(self, parser):
        """Load a parser function (currently only Python supported)."""
        if parser.language.lower() != "python":
            raise LanguageNotHandled(
                f"Parser #{parser.id} is coded in an unknown language ({parser.language})"
            )
        return self.load_parse_python_function(parser)

    def _load_metric(self, metric_id):
        """Load a metric from cache or database."""
        if metric_id not in self.metrics_cache:
            metric = repos['Metric'].get(id=metric_id)
            if metric is None:
                raise MetricNotFound(f"Metric #{metric_id} doesn't exist in the database")
            self.metrics_cache[metric_id] = metric
        return self.metrics_cache[metric_id]

    def _load_device_type(self, device_type_id):
        """Load a device type from cache or database."""
        if device_type_id not in self.device_types_cache:
            device_type = repos['DeviceType'].get(id=device_type_id)
            if device_type is None:
                raise DeviceTypeNotFound(
                    f"Device Type #{device_type_id} doesn't exist in the database"
                )
            self.device_types_cache[device_type_id] = device_type
        return self.device_types_cache[device_type_id]

    def judge_data_quality(self, *args, **kwargs):
        """Determine data quality (placeholder for future implementation)."""
        # TODO: implement quality judgment logic
        return "good"

    def retrieve_sender(self, message):
        """Retrieve topic, device, and client from a message."""
        topic = repos['MqttTopic'].get(topic=message.topic, active=True)
        if topic is None:
            topic = repos['MqttTopic'].get(topic=message.topic)
            if topic is None:
                raise TopicNotFound(f"Message published to unknown topic {message.topic}")
            raise DisabledTopic(
                f"Message published to disabled topic {message.topic} (topic: #{topic.id})"
            )

        device = repos['Device'].get(id=topic.device_id)
        if device is None:
            raise DeviceNotFound(f"Topic {message.topic} not linked to any device")

        client = repos['Client'].get(id=topic.client_id)
        if client is None:
            raise ClientNotFound(f"Topic {message.topic} not linked to any client")

        return topic, device, client

    def select_route(self, client, device, topic, message):
        """Select the appropriate routing rule for a message."""
        from sqlalchemy import or_

        candidates = []
        evaluated = {}

        # Full rows in the conditions context, matching the documented DSL
        # contract (conditions may reference any column, e.g. device.metadata_json).
        context = {
            "device": device.to_dict(),
            "device_type": self._load_device_type(device.device_type_id).to_dict(),
            "topic": topic.to_dict(),
            "message": message.to_dict(),
        }

        # Find routes matching client, topic, and device (with wildcard support)
        all_routes = repos['RoutingRule'].list(
            client_id=client.id,
            active=True
        )

        for route in all_routes:
            # Check topic match
            if route.topic_id and route.topic_id != topic.id:
                continue

            # Check device match (None means wildcard/any device)
            if route.device_id and route.device_id != device.id:
                continue

            if route.conditions:
                try:
                    conditions = json.loads(route.conditions) if isinstance(route.conditions, str) else route.conditions
                    evaluation = eval_mongo_dsl(conditions, context)
                    if not evaluation:
                        continue
                    evaluated[route.id] = 1
                except Exception as e:
                    LOGGER.warning(
                        f"Condition evaluation failed for route {route.id}: {e}. "
                        f"Route will be considered conditionless and its priority penalized."
                    )
                    evaluated[route.id] = -1

            candidates.append(route)

        if not candidates:
            raise NoRouteFound(f"No route found to manage message #{message.id}")

        # Lowest priority number wins. Within the lowest raw-priority group, a
        # matched condition grants a -1 bonus and a failed condition evaluation
        # a +1 penalty on the effective priority. Ties break on newest route.
        min_priority = min(r.priority for r in candidates)
        prioritary = [r for r in candidates if r.priority == min_priority]
        min_effective = min(r.priority - evaluated.get(r.id, 0) for r in prioritary)
        prioritary = [r for r in prioritary if r.priority - evaluated.get(r.id, 0) == min_effective]
        prioritary = sorted(prioritary, key=lambda r: r.created_at, reverse=True)

        if len(prioritary) > 1:
            LOGGER.warning(
                f"Multiple routes possible for message #{message.id}: "
                f"{','.join([f'route #{r.id}' for r in prioritary[:3]])}. "
                f"Newest one will be selected."
            )

        selected = prioritary[0]
        LOGGER.info(f"Route #{selected.id} selected for message #{message.id}")

        # Validate parser config JSON
        try:
            json.loads(selected.parser_config or "{}")
        except:
            raise ValueError(
                f"Parser config for route #{selected.id} is invalid JSON: {selected.parser_config}"
            )

        return selected

    def process_message(self, message):
        """Process a single MQTT message into parsed points."""
        extraction = Extraction(
            id=str(uuid4()),
            message_id=message.id,
            parsed_at=datetime.utcnow(),
            success=True
        )

        topic, device, client = self.retrieve_sender(message)
        LOGGER.info(
            f"Message #{message.id} from device #{device.id} "
            f"of client {client.name} (#{client.id})"
        )

        route = self.select_route(client, device, topic, message)
        LOGGER.info(f"Route #{route.id} selected for message #{message.id}")

        parser = repos['Parser'].get(id=route.parser_id)
        LOGGER.info(f"Parser {parser.name} selected for message #{message.id}")

        extraction.parser_id = parser.id
        extraction.parser_config = route.parser_config

        parse_function = self.load_parse_function(parser)

        # Parse the payload
        payload = json.loads(message.payload) if isinstance(message.payload, str) else message.payload
        parser_config = json.loads(route.parser_config or "{}")

        try:
            results = parse_function(payload, **parser_config)
        except Exception as e:
            LOGGER.error(f"Parser failed for message #{message.id}: {e}", exc_info=True)
            extraction.success = False
            extraction.error_text = f"Parser failed: {str(e)}"
            extraction.extracted_count = 0
            return [], extraction, route

        if not results:
            extraction.error_text = f"Parser returned no results for message #{message.id}"
            LOGGER.warning(extraction.error_text)
            extraction.success = False
            extraction.extracted_count = 0
        else:
            extraction.extracted_count = len([k for k in results.keys() if isinstance(k, int)])

        # Determine timestamp; a parser-provided "at" must be a datetime or an
        # ISO-8601 string, otherwise fall back to the message timestamp.
        ts = message.at
        if isinstance(results, dict) and "at" in results:
            at = results["at"]
            if isinstance(at, datetime):
                ts = at
            elif isinstance(at, str):
                try:
                    ts = datetime.fromisoformat(at.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    LOGGER.warning(f"Parser returned invalid 'at' ({at!r}); using message timestamp")
            else:
                LOGGER.warning(f"Parser returned invalid 'at' ({at!r}); using message timestamp")

        # Create parsed points
        parsed = []
        for metric_id, value in (results or {}).items():
            if not isinstance(metric_id, int):
                continue

            metric = self._load_metric(metric_id)

            # Determine value type and field. bool must be checked before
            # int/float: bool is a subclass of int, so the number branch
            # would otherwise swallow booleans into num_value.
            if isinstance(value, bool):
                value_field = "bool_value"
                stored_value = value
            elif isinstance(value, (int, float)):
                value_field = "num_value"
                stored_value = value
            elif isinstance(value, str):
                value_field = "str_value"
                stored_value = value
            elif isinstance(value, (dict, list)):
                value_field = "json_value"
                stored_value = json.dumps(value)
            else:
                LOGGER.warning(f"Unsupported value type for metric {metric_id}: {type(value)}")
                continue

            point = ParsedPoint(
                extraction_id=extraction.id,
                device_id=device.id,
                metric_id=metric_id,
                ts=ts,
                unit=metric.default_unit,
                quality=self.judge_data_quality(metric, value),
                meta_json=json.dumps({
                    k: v for k, v in results.items()
                    if not isinstance(k, int) and k != "at"
                }),
                **{value_field: stored_value}
            )
            parsed.append(point)

        return parsed, extraction, route

    def on_data_sent(self, dispatch, **kwargs):
        """Update dispatch status after sending."""
        for key, value in kwargs.items():
            if hasattr(dispatch, key):
                setattr(dispatch, key, value)

        # Update in database
        session = get_session()
        try:
            merged = session.merge(dispatch)
            session.commit()
            return merged.status == "sent"
        finally:
            session.close()

    def _destination_password(self, destination):
        """Return the destination's plaintext password (decrypting password_enc)."""
        if destination.password_enc is None:
            return None
        token = destination.password_enc
        if isinstance(token, (bytes, bytearray)):
            token = token.decode("ascii")
        if self._crypto_config is None:
            configs = repos['CryptoConfig'].list()
            if not configs:
                raise RuntimeError("No crypto config defined; cannot decrypt destination password")
            self._crypto_config = configs[0]
        cc = self._crypto_config
        key = get_key_bytes(cc.key_source, cc.key_id)
        return decrypt_data(token, key, key_id=cc.key_id).decode("utf-8")

    def dispatch_to_deposit(self, deposit, extraction, points):
        """Send points to one deposit's destination; record the outcome in dispatch."""
        destination = repos['ClientDestination'].get(id=deposit.destination_id)
        if destination is None:
            raise DestinationNotFound(f"Client destination #{deposit.destination_id} not found")

        dispatch = Dispatch(
            extraction_id=extraction.id,
            deposit_id=deposit.id,
            status="queued",
            attempts=1,
            created_at=datetime.utcnow(),
        )
        session = get_session()
        try:
            session.add(dispatch)
            session.commit()
        finally:
            session.close()

        dispatcher_class = DISPATCHERS.get((destination.type or "").lower())
        if dispatcher_class is None:
            return self.on_data_sent(
                dispatch, status="failed",
                response_snippet=f"No dispatcher implemented for destination type {destination.type!r}",
            )

        options = destination.options_json
        options = json.loads(options) if isinstance(options, str) else (options or {})
        dispatcher = dispatcher_class(
            host=destination.host,
            port=destination.port,
            database_name=destination.database_name,
            username=destination.username,
            password=self._destination_password(destination),
            **options,
        )
        LOGGER.info(f"Dispatcher {dispatcher_class.__name__} initialized for destination #{destination.id}")

        # Dispatchers expect dicts; enrich with the metric key_name so the
        # default column mapping (device_id/key_name/ts/value/...) works.
        point_dicts = []
        for p in points:
            d = p.to_dict()
            d["key_name"] = self._load_metric(p.metric_id).name
            point_dicts.append(d)

        try:
            results = dispatcher.dispatch(parsed_points=point_dicts)
        except Exception:
            LOGGER.warning(f"Dispatch to destination #{destination.id} failed")
            LOGGER.warning(traceback.format_exc())
            results = {"status": "failed", "response_snippet": traceback.format_exc()[-1000:]}

        return self.on_data_sent(dispatch, **results)

    def send_parsed_data(self, route, extraction, points):
        """Dispatch the extraction's points to every deposit of the route."""
        deposits = repos['RouteDeposit'].list(rule_id=route.id)
        if not deposits:
            LOGGER.info(f"Route #{route.id} has no deposits; extraction #{extraction.id} kept locally only")
            return True

        dispatched = []
        for deposit in deposits:
            LOGGER.info(
                f"Sending {len(points)} points from extraction #{extraction.id} "
                f"to deposit #{deposit.id} (destination #{deposit.destination_id})"
            )
            try:
                sent = self.dispatch_to_deposit(deposit, extraction, points)
                if not sent:
                    LOGGER.warning(f"Dispatch to deposit #{deposit.id} for extraction #{extraction.id} failed")
                dispatched.append(sent)
            except Exception:
                LOGGER.error(f"Error dispatching extraction #{extraction.id} to deposit #{deposit.id}")
                LOGGER.error(traceback.format_exc())
                dispatched.append(False)

        return all(dispatched)

    def process_all_unprocessed(self):
        """Process all unprocessed messages."""
        LOGGER.info("Starting message processing cycle")
        self.clear_caches()

        unprocessed = repos['MqttMessage'].list(processed=False)
        LOGGER.info(f"Found {len(unprocessed)} unprocessed messages")

        for message in unprocessed:
            try:
                LOGGER.info(f"Processing message #{message.id}")
                parsed_points, extraction, route = self.process_message(message)

                # Save extraction
                session = get_session()
                try:
                    session.add(extraction)
                    session.flush()

                    # Save parsed points
                    for point in parsed_points:
                        point.extraction_id = extraction.id
                        session.add(point)

                    # Mark message as processed
                    message.processed = True
                    message.processor = extraction.id
                    session.merge(message)

                    session.commit()
                    LOGGER.info(f"Successfully processed message #{message.id}")
                finally:
                    session.close()

                # Dispatch to the route's destinations. Points are already
                # persisted, so a dispatch failure must not unmark the message
                # (that would duplicate extractions); failures live in the
                # dispatch ledger (status=failed) instead.
                if extraction.success and parsed_points:
                    try:
                        self.send_parsed_data(route, extraction, parsed_points)
                    except Exception:
                        LOGGER.error(f"Dispatch stage failed for message #{message.id}")
                        LOGGER.error(traceback.format_exc())

            except Exception as e:
                LOGGER.error(f"Error processing message #{message.id}: {e}", exc_info=True)
                # Record the failure as an extraction row (audit trail), then
                # mark the message processed to avoid infinite retries.
                session = None
                try:
                    session = get_session()
                    failure = Extraction(
                        id=str(uuid4()),
                        message_id=message.id,
                        parsed_at=datetime.utcnow(),
                        success=False,
                        extracted_count=0,
                        error_text=str(e),
                    )
                    session.add(failure)
                    msg = session.query(MqttMessage).filter(MqttMessage.id == message.id).first()
                    if msg:
                        msg.processed = True
                        msg.processor = failure.id
                    session.commit()
                except Exception:
                    LOGGER.error(f"Failed to record processing failure for message #{message.id}", exc_info=True)
                finally:
                    if session is not None:
                        session.close()

        LOGGER.info("Message processing cycle complete")


# Seconds after which a RUNNING job row is considered stale (crashed worker).
# The loop heartbeats every cycle (~10s), so 60s means several missed beats.
JOB_STALE_SECONDS = 60


def _get_or_create_job(session):
    job = session.query(Job).filter(Job.name == MQTTT_JOB_NAME).first()
    if job is None:
        job = Job(name=MQTTT_JOB_NAME, state="IDLE", last_state_update=datetime.utcnow())
        session.add(job)
        session.commit()
    return job


def acquire_job_lock():
    """Take the job lock, refusing if another live worker holds it."""
    session = get_session()
    try:
        job = _get_or_create_job(session)
        age = (datetime.utcnow() - job.last_state_update).total_seconds()
        if job.state == "RUNNING" and age < JOB_STALE_SECONDS:
            return False
        if job.state == "RUNNING":
            LOGGER.warning(f"Taking over stale job lock (no heartbeat for {int(age)}s)")
        job.state = "RUNNING"
        job.last_state_update = datetime.utcnow()
        session.commit()
        return True
    finally:
        session.close()


def heartbeat_job_lock():
    session = get_session()
    try:
        job = _get_or_create_job(session)
        job.last_state_update = datetime.utcnow()
        session.commit()
    finally:
        session.close()


def release_job_lock(exit_code=0):
    session = get_session()
    try:
        job = _get_or_create_job(session)
        job.state = "IDLE"
        job.last_exit_code = exit_code
        job.last_state_update = datetime.utcnow()
        session.commit()
    finally:
        session.close()


def main():
    """Main entry point for the worker."""
    parser = argparse.ArgumentParser(description='MQTT Transfer Worker')
    parser.add_argument('--root-dir', default=os.getcwd(), help='Root directory of the application')
    parser.add_argument('--logging-dir', default='logs', help='Directory for log files')
    args = parser.parse_args()

    # Load configuration
    config = load_configs(args.root_dir)

    # Set up logging
    global LOGGER
    LOGGER = get_logger(args.logging_dir)
    setattr(__builtins__, 'LOGGER', LOGGER)

    # Initialize database
    init_context(config)

    if not acquire_job_lock():
        LOGGER.warning("Another MqttTransfer worker is already running. Exiting.")
        print("Another MqttTransfer worker is already running. Exiting.")
        return

    # Run transfer
    transfer = MqttTransfer()

    exit_code = 0
    try:
        while True:
            try:
                transfer.process_all_unprocessed()
                heartbeat_job_lock()
                time.sleep(10)  # Wait 10 seconds before next cycle
            except KeyboardInterrupt:
                LOGGER.info("Shutting down")
                break
            except Exception as e:
                LOGGER.error(f"Unexpected error: {e}", exc_info=True)
                exit_code = 2
                time.sleep(10)
    finally:
        release_job_lock(exit_code)


if __name__ == '__main__':
    main()
