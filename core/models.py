# SQLAlchemy ORM Models for MqttRelay (replacing temod)
from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, LargeBinary, ForeignKey, UniqueConstraint, Index, Float
from sqlalchemy.orm import relationship, foreign
from sqlalchemy.sql import func
from core.db import Base
from datetime import datetime
import uuid
import json


class BaseModel(Base):
    """Base model with common functionality."""
    __abstract__ = True

    # Column names never included in to_dict() output (secrets/hashes).
    SENSITIVE_FIELDS = frozenset()

    def to_dict(self):
        """Convert model to dictionary, excluding SENSITIVE_FIELDS."""
        result = {}
        for column in self.__table__.columns:
            if column.name in self.SENSITIVE_FIELDS:
                continue
            value = getattr(self, column.name)
            
            # Handle datetime serialization
            if isinstance(value, datetime):
                result[column.name] = value.isoformat() if value else None
            # Handle bytes serialization
            elif isinstance(value, bytes):
                try:
                    result[column.name] = value.decode('utf-8')
                except:
                    result[column.name] = value.hex()
            else:
                result[column.name] = value
        
        return result


# ============= APP & SECURITY =============

class MqttRelay(BaseModel):
    """Application version tracking."""
    __tablename__ = "mqtt_relay"
    
    version = Column(String(20), primary_key=True)


class Language(BaseModel):
    """Supported languages for the UI."""
    __tablename__ = "language"
    
    code = Column(String(10), primary_key=True)
    name = Column(String(50), nullable=False)


class Job(BaseModel):
    """Job concurrency lock (used by mqtt_transfer worker)."""
    __tablename__ = "job"
    
    name = Column(String(50), primary_key=True)
    state = Column(String(20), nullable=False, default="IDLE")
    last_state_update = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_exit_code = Column(Integer, nullable=True)


class CryptoConfig(BaseModel):
    """Encryption configuration for secrets."""
    __tablename__ = "crypto_config"
    
    id = Column(Integer, primary_key=True)
    algorithm = Column(String(50), nullable=False, default="aes-256-gcm")
    key_source = Column(String(20), nullable=False, default="env")
    key_id = Column(String(128), nullable=False, default="PRIMARY")
    iv_bytes = Column(Integer, nullable=False, default=12)
    tag_bytes = Column(Integer, nullable=False, default=16)
    encoding = Column(String(20), nullable=False, default="base64")
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, nullable=True)


class CryptoKey(BaseModel):
    """Master encryption keys."""
    __tablename__ = "crypto_key"

    SENSITIVE_FIELDS = frozenset({"key_b64"})

    key_id = Column(String(128), primary_key=True)
    key_b64 = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('key_id', 'version', name='uq_key_id_version'),
    )


class Privilege(BaseModel):
    """User privilege/role definitions."""
    __tablename__ = "privilege"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    label = Column(String(256), nullable=False, unique=True)
    roles = Column(String(256), nullable=False)
    editable = Column(Boolean, nullable=False, default=True)
    
    # Relationships
    users = relationship("User", back_populates="privilege")


class User(BaseModel):
    """System users."""
    __tablename__ = "user"

    SENSITIVE_FIELDS = frozenset({"password"})

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    privilege_id = Column(String(36), ForeignKey("privilege.id"), nullable=False)
    email = Column(String(320), nullable=False, unique=True)
    password = Column(LargeBinary(60), nullable=False)  # bcrypt hash
    is_authenticated = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=False)
    is_disabled = Column(Boolean, nullable=False, default=False)
    language = Column(String(256), nullable=False, default="en")
    track = Column(Boolean, nullable=False, default=False)
    
    # Relationships
    privilege = relationship("Privilege", back_populates="users")
    
    __table_args__ = (
        Index('idx_user_email', 'email'),
    )


# ============= MULTI-TENANT (CLIENT) =============

class Client(BaseModel):
    """Tenant/client."""
    __tablename__ = "client"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=True)
    phone = Column(String(150), nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active, paused, disabled
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    destinations = relationship("ClientDestination", back_populates="client", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="client", cascade="all, delete-orphan")
    topics = relationship("MqttTopic", back_populates="client")
    routes = relationship("RoutingRule", back_populates="client", cascade="all, delete-orphan")


class ClientDestination(BaseModel):
    """Destination sink for client (where to dispatch parsed points)."""
    __tablename__ = "client_destination"

    SENSITIVE_FIELDS = frozenset({"password_enc"})

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey("client.id"), nullable=False)
    type = Column(String(20), nullable=False)  # mysql, postgres, http, kafka, file, other
    host = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    database_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    password_enc = Column(LargeBinary(1024), nullable=True)
    encryption_version = Column(String(130), nullable=True)
    uri = Column(String(1024), nullable=True)
    options_json = Column(Text, nullable=True)  # JSON as text
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    client = relationship("Client", back_populates="destinations")
    deposits = relationship("RouteDeposit", back_populates="destination", cascade="all, delete-orphan")


# ============= IOT (DEVICES) =============

class DeviceType(BaseModel):
    """Device type catalog (vendor/model/kind)."""
    __tablename__ = "device_type"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor = Column(String(128), nullable=False)
    model = Column(String(128), nullable=False)
    kind = Column(String(64), nullable=False)
    capabilities = Column(Text, nullable=True)  # JSON
    payload_schema = Column(Text, nullable=True)  # JSON
    defaults_json = Column(Text, nullable=True)  # JSON
    notes = Column(String(512), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    devices = relationship("Device", back_populates="device_type")
    
    __table_args__ = (
        UniqueConstraint('vendor', 'model', name='uq_vendor_model'),
    )


class Device(BaseModel):
    """IoT device instance."""
    __tablename__ = "device"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(Integer, ForeignKey("client.id"), nullable=False)
    device_type_id = Column(Integer, ForeignKey("device_type.id"), nullable=False)
    topic = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    external_ref = Column(String(128), nullable=True)
    description = Column(String(512), nullable=True)
    location = Column(String(512), nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON as text (e.g. lat/lng)
    active = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="unknown")
    emission_rate = Column(Integer, nullable=True)  # expected ms between messages, used for availability calc
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    client = relationship("Client", back_populates="devices")
    device_type = relationship("DeviceType", back_populates="devices")


# ============= MQTT =============

class MqttTopic(BaseModel):
    """MQTT topic metadata."""
    __tablename__ = "mqtt_topic"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String(255), nullable=False, unique=True)
    description = Column(String(512), nullable=True)
    qos_default = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    client_id = Column(Integer, ForeignKey("client.id"), nullable=True)
    device_id = Column(Integer, ForeignKey("device.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    client = relationship("Client", back_populates="topics", lazy="joined")
    device = relationship("Device", lazy="joined")
    # No FK: mqtt_message.topic is a plain string matched against this unique topic name.
    messages = relationship(
        "MqttMessage",
        primaryjoin="MqttTopic.topic == foreign(MqttMessage.topic)",
        back_populates="mqtt_topic",
        viewonly=True,
    )


class MqttMessage(BaseModel):
    """Raw MQTT message (ingested by dashboard)."""
    __tablename__ = "mqtt_message"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client = Column(String(255), nullable=False)  # Client slug
    topic = Column(String(255), nullable=False)
    payload = Column(Text, nullable=True)
    qos = Column(Integer, nullable=False, default=0)
    processed = Column(Boolean, nullable=False, default=False)
    processor = Column(String(36), nullable=True)  # UUID of extraction
    at = Column(DateTime, nullable=False)
    
    # Relationships
    # No FK: topic is a plain string matched against mqtt_topic's unique topic name.
    mqtt_topic = relationship(
        "MqttTopic",
        primaryjoin="foreign(MqttMessage.topic) == MqttTopic.topic",
        back_populates="messages",
        viewonly=True,
    )
    
    __table_args__ = (
        Index('idx_mqtt_msg_processed', 'processed'),
        Index('idx_mqtt_msg_topic', 'topic'),
        Index('idx_mqtt_msg_at', 'at'),
    )


class MqttBroker(BaseModel):
    """MQTT broker configuration."""
    __tablename__ = "mqtt_broker"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    uri = Column(String(512), nullable=False)
    client_id = Column(Integer, ForeignKey("client.id"), nullable=True)
    auth_json = Column(Text, nullable=True)  # JSON
    last_seen_at = Column(DateTime, nullable=True)
    active = Column(Boolean, nullable=False, default=True)


# ============= PARSERS =============

class Parser(BaseModel):
    """Parser metadata."""
    __tablename__ = "parser"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    description = Column(String(512), nullable=True)
    language = Column(String(50), nullable=False, default="python")
    config_schema = Column(Text, nullable=True)  # JSON as text
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    routes = relationship("RoutingRule", back_populates="parser")
    
    __table_args__ = (
        UniqueConstraint('name', 'version', name='uq_parser_name_version'),
    )


class Metric(BaseModel):
    """Metric catalog (time-series metric definitions)."""
    __tablename__ = "metric_catalog"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    unit = Column(String(50), nullable=True)
    type = Column(String(50), nullable=False)
    description = Column(String(512), nullable=True)
    default_unit = Column(String(50), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    points = relationship("ParsedPoint", back_populates="metric")


class ParsedPoint(BaseModel):
    """Normalized time-series point."""
    __tablename__ = "parsed_point"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    extraction_id = Column(String(36), ForeignKey("extraction.id"), nullable=False)
    device_id = Column(Integer, nullable=False)
    metric_id = Column(Integer, ForeignKey("metric_catalog.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    num_value = Column(Float, nullable=True)
    str_value = Column(String(1024), nullable=True)
    bool_value = Column(Boolean, nullable=True)
    json_value = Column(Text, nullable=True)
    unit = Column(String(50), nullable=True)
    quality = Column(String(20), nullable=False, default="good")
    meta_json = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    extraction = relationship("Extraction", back_populates="points")
    metric = relationship("Metric", back_populates="points")
    
    __table_args__ = (
        Index('idx_parsed_point_ts', 'ts'),
        Index('idx_parsed_point_metric', 'metric_id'),
    )


class Extraction(BaseModel):
    """Parse run metadata."""
    __tablename__ = "extraction"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(Integer, ForeignKey("mqtt_message.id"), nullable=False)
    # Audit of what ran: intentionally no FK so extractions survive parser deletion.
    parser_id = Column(Integer, nullable=True)
    parser_config = Column(Text, nullable=True)
    parsed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    success = Column(Boolean, nullable=False, default=True)
    extracted_count = Column(Integer, nullable=True)
    error_text = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    points = relationship("ParsedPoint", back_populates="extraction", cascade="all, delete-orphan")


# ============= ROUTING =============

class RoutingRule(BaseModel):
    """Route definition (client → parser → destinations)."""
    __tablename__ = "routing_rule"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(Integer, ForeignKey("client.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("mqtt_topic.id"), nullable=True)
    device_id = Column(Integer, ForeignKey("device.id"), nullable=True)
    parser_id = Column(Integer, ForeignKey("parser.id"), nullable=False)
    parser_config = Column(Text, nullable=True)  # JSON
    active = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
    conditions = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    client = relationship("Client", back_populates="routes", lazy="joined")
    topic = relationship("MqttTopic", lazy="joined")
    device = relationship("Device", lazy="joined")
    parser = relationship("Parser", back_populates="routes", lazy="joined")
    deposits = relationship("RouteDeposit", back_populates="route", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_route_client', 'client_id'),
        Index('idx_route_active', 'active'),
    )


class RouteDeposit(BaseModel):
    """Link between routing rule and destination."""
    __tablename__ = "route_deposit"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(String(36), ForeignKey("routing_rule.id"), nullable=False)
    destination_id = Column(Integer, ForeignKey("client_destination.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    route = relationship("RoutingRule", back_populates="deposits")
    destination = relationship("ClientDestination", back_populates="deposits")


class Dispatch(BaseModel):
    """Dispatch ledger."""
    __tablename__ = "dispatch"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    extraction_id = Column(String(36), ForeignKey("extraction.id"), nullable=False)
    deposit_id = Column(Integer, ForeignKey("route_deposit.id"), nullable=False)
    status = Column(String(20), nullable=False, default="queued")  # queued, sent, failed
    attempts = Column(Integer, nullable=False, default=1)
    http_status = Column(Integer, nullable=True)
    response_snippet = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_dispatch_status', 'status'),
    )
