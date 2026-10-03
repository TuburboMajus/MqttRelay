import os
import dotenv
import random
from pathlib import Path

# Import all models
from core.models import (
    User, Privilege, Client, ClientDestination, Device, DeviceType,
    MqttMessage, MqttTopic, MqttBroker, Parser, Metric, ParsedPoint, Extraction,
    RoutingRule, RouteDeposit, Dispatch, CryptoConfig, CryptoKey, Job, Language, MqttRelay
)
from core.repository import repos, Repository
from core.db import init_db as db_init_db


# Parser file storage (directory-based, database-agnostic)
class DirectoryStorage:
    """Simple file-based storage for parser code."""
    def __init__(self, base_path: str):
        self.base_path = base_path
        Path(base_path).mkdir(parents=True, exist_ok=True)
    
    def has(self, name: str) -> bool:
        """Check if a file exists."""
        return (Path(self.base_path) / f"{name}.py").exists()
    
    def read(self, name: str) -> str:
        """Read a file."""
        with open(Path(self.base_path) / f"{name}.py", 'r') as f:
            return f.read()
    
    def write(self, name: str, content: str) -> None:
        """Write a file."""
        with open(Path(self.base_path) / f"{name}.py", 'w') as f:
            f.write(content)
    
    def delete(self, name: str) -> None:
        """Delete a file."""
        (Path(self.base_path) / f"{name}.py").unlink(missing_ok=True)
    
    def list(self) -> list:
        """List all parser names."""
        return [f.stem for f in Path(self.base_path).glob("*.py") if f.is_file()]


PARSERS_DB = DirectoryStorage(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "db", "parsers")
)


def init_context(config):
    """Initialize the application context with database and entities."""
    # Initialize database connection
    db_url = config.get('database_url')
    if not db_url:
        # Build PostgreSQL connection string from credentials
        creds = config.get('storage', {}).get('credentials', {})
        db_host = creds.get('host', 'localhost')
        db_port = creds.get('port', 5432)
        db_name = creds.get('database', 'mqtt')
        db_user = creds.get('user', 'mqtt')
        db_pass = creds.get('password', '')
        db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    
    db_init_db(db_url)
    
    # Register models as global builtins for easy access in blueprints
    models = {
        'User': User,
        'Privilege': Privilege,
        'Client': Client,
        'ClientDestination': ClientDestination,
        'Device': Device,
        'DeviceType': DeviceType,
        'MqttMessage': MqttMessage,
        'MqttTopic': MqttTopic,
        'MqttBroker': MqttBroker,
        'Parser': Parser,
        'Metric': Metric,
        'ParsedPoint': ParsedPoint,
        'Extraction': Extraction,
        'RoutingRule': RoutingRule,
        'RouteDeposit': RouteDeposit,
        'Dispatch': Dispatch,
        'CryptoConfig': CryptoConfig,
        'CryptoKey': CryptoKey,
        'Job': Job,
        'Language': Language,
        'MqttRelay': MqttRelay,
        'Repository': Repository,
    }
    
    for name, model in models.items():
        if name in __builtins__:
            print(f'Warning: cannot register {name} in global context as it is already used')
            continue
        __builtins__[name] = model
    
    # Register repositories for easy access
    for name, repo in repos.items():
        # Create a storage-like interface with models
        # This allows syntax like Client.storage.get() in blueprints
        setattr(model, 'storage', repo)
        for model_name, model_class in models.items():
            if name == model_name:
                setattr(model_class, 'storage', repo)
    
    dotenv.load_dotenv()


# ** Section ** GenerateSecretKey
def generate_secret_key(length=8):
	alphabet = "abcdefghijklmnopqrstuvwxyz0123456789?!,;:./§$£*µù%+=°)àç_è-('é&²~"
	return "".join([
		getattr(alphabet[random.randint(0,len(alphabet)-1)],["upper","lower"][random.randint(0,1)])()
		for _ in range(length)
	])
# ** EndSection ** GenerateSecretKey