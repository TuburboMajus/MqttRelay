#!/usr/bin/env python3
"""
MqttRelay Installation Script (SQLAlchemy/PostgreSQL version)
Sets up database, configuration files, encryption keys, and admin user.
"""

import os
import sys
import toml
import getpass
import secrets
import base64
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from core.db import init_db, engine, Base
from core.models import (
    Language, Privilege, User, CryptoConfig, CryptoKey, Job, MqttRelay
)
from core.repository import Repository, get_session
from core.auth import hash_password


def generate_secret_key(length: int = 32) -> str:
    """Generate a random secret key."""
    return secrets.token_hex(length // 2)


def generate_encryption_key() -> str:
    """Generate a 32-byte encryption key (base64 encoded)."""
    key = secrets.token_bytes(32)
    return base64.b64encode(key).decode('ascii')


def get_yes_no(prompt: str) -> bool:
    """Get yes/no response from user."""
    while True:
        response = input(f"{prompt} (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        print("Please enter 'y' or 'n'")


def setup_database():
    """Initialize database connection and create schema."""
    print("\n=== Database Configuration ===")
    print("MqttRelay uses PostgreSQL (recommended) or MySQL.")
    
    db_type = input("Enter database type (postgresql/mysql) [postgresql]: ").strip().lower() or "postgresql"
    
    if db_type == "postgresql":
        db_host = input("PostgreSQL host [localhost]: ").strip() or "localhost"
        db_port = input("PostgreSQL port [5432]: ").strip() or "5432"
        db_name = input("Database name [mqtt]: ").strip() or "mqtt"
        db_user = input("Database user [mqtt]: ").strip() or "mqtt"
        db_pass = getpass.getpass("Database password: ")
        
        db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{int(db_port)}/{db_name}"
    elif db_type == "mysql":
        print("WARNING: MySQL support is deprecated. PostgreSQL is recommended.")
        db_host = input("MySQL host [localhost]: ").strip() or "localhost"
        db_port = input("MySQL port [3306]: ").strip() or "3306"
        db_name = input("Database name [mqtt]: ").strip() or "mqtt"
        db_user = input("Database user [mqtt]: ").strip() or "mqtt"
        db_pass = getpass.getpass("Database password: ")
        
        db_url = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{int(db_port)}/{db_name}"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
    
    print("Initializing database...")
    try:
        init_db(db_url, echo=False)
        Base.metadata.create_all(engine)
        print("✓ Database schema created successfully")
        return db_url
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        raise


def setup_encryption():
    """Setup encryption keys."""
    print("\n=== Encryption Configuration ===")
    print("MqttRelay encrypts sensitive destination credentials.")
    
    key_source = input("Key storage (env/kms/db) [env]: ").strip().lower() or "env"
    
    if key_source not in ['env', 'kms', 'db']:
        raise ValueError("Invalid key source")
    
    # Create default crypto config
    session = get_session()
    try:
        # Check if crypto config already exists
        crypto_config = session.query(CryptoConfig).filter(CryptoConfig.id == 1).first()
        if not crypto_config:
            crypto_config = CryptoConfig(
                id=1,
                algorithm='aes-256-gcm',
                key_source=key_source,
                key_id='PRIMARY',
                iv_bytes=12,
                tag_bytes=16,
                encoding='base64',
                version=1
            )
            session.add(crypto_config)
            session.commit()
            print("✓ Crypto config created")
        else:
            print("✓ Crypto config already exists")
        
        # Generate and store encryption key if using env or db storage
        if key_source in ['env', 'db']:
            enc_key = generate_encryption_key()
            
            if key_source == 'env':
                print("\nEncryption Key (store this in MQTT_RELAY_ENC_KEY_PRIMARY environment variable):")
                print(f"  {enc_key}")
                print("\nAdd to your .env file:")
                print(f"  MQTT_RELAY_ENC_KEY_PRIMARY={enc_key}")
            elif key_source == 'db':
                # Store in database
                existing_key = session.query(CryptoKey).filter(CryptoKey.key_id == 'PRIMARY').first()
                if not existing_key:
                    crypto_key = CryptoKey(
                        key_id='PRIMARY',
                        key_b64=enc_key,
                        version=1
                    )
                    session.add(crypto_key)
                    session.commit()
                    print("✓ Encryption key stored in database")
        
    finally:
        session.close()


def setup_admin_user():
    """Create admin user."""
    print("\n=== Admin User Setup ===")
    
    email = input("Admin email: ").strip()
    password = getpass.getpass("Admin password: ")
    password_confirm = getpass.getpass("Confirm password: ")
    
    if password != password_confirm:
        print("✗ Passwords don't match")
        return False
    
    if len(password) < 8:
        print("✗ Password must be at least 8 characters")
        return False
    
    session = get_session()
    try:
        # Check if user already exists
        existing_user = session.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"✗ User {email} already exists")
            return False
        
        # Get or create admin privilege
        admin_priv = session.query(Privilege).filter(Privilege.label == 'admin').first()
        if not admin_priv:
            admin_priv = Privilege(
                id='admin-privilege',
                label='admin',
                roles='admin',
                editable=True
            )
            session.add(admin_priv)
            session.flush()
        
        # Create admin user
        admin_user = User(
            email=email,
            privilege_id=admin_priv.id,
            password=hash_password(password),
            is_authenticated=True,
            is_active=True,
            is_disabled=False,
            language='en',
            track=False
        )
        session.add(admin_user)
        session.commit()
        
        print(f"✓ Admin user created: {email}")
        return True
    except Exception as e:
        session.rollback()
        print(f"✗ Failed to create admin user: {e}")
        return False
    finally:
        session.close()


def setup_config():
    """Setup configuration file."""
    print("\n=== Application Configuration ===")
    
    config_path = Path(__file__).parent.parent.parent / "config.toml"
    
    if config_path.exists():
        if not get_yes_no(f"Config file exists at {config_path}. Overwrite?"):
            return
    
    # Load template
    template_path = config_path.with_name("config.toml.template")
    if template_path.exists():
        with open(template_path) as f:
            config = toml.load(f)
    else:
        config = {}
    
    # Set defaults
    if 'app' not in config:
        config['app'] = {}
    
    config['app']['secret_key'] = config['app'].get('secret_key', '') or generate_secret_key()
    config['app']['debug'] = False
    config['app']['host'] = input("App host [127.0.0.1]: ").strip() or "127.0.0.1"
    config['app']['port'] = int(input("App port [5000]: ").strip() or "5000")
    config['app']['threaded'] = True
    
    # Save config
    with open(config_path, 'w') as f:
        toml.dump(config, f)
    
    print(f"✓ Configuration saved to {config_path}")


def setup_mqtt():
    """Setup MQTT broker configuration."""
    print("\n=== MQTT Broker Configuration ===")
    
    broker_host = input("MQTT broker host [localhost]: ").strip() or "localhost"
    broker_port = int(input("MQTT broker port [1883]: ").strip() or "1883")
    
    print(f"✓ MQTT broker: mqtt://{broker_host}:{broker_port}")


def main():
    """Run the installation wizard."""
    print("\n" + "="*50)
    print("MqttRelay Installation Wizard (SQLAlchemy/PostgreSQL)")
    print("="*50)
    
    try:
        # Step 1: Database
        db_url = setup_database()
        
        # Step 2: Encryption
        setup_encryption()
        
        # Step 3: Admin User
        if not setup_admin_user():
            print("\n⚠ Skipping admin user creation")
        
        # Step 4: Configuration
        setup_config()
        
        # Step 5: MQTT
        setup_mqtt()
        
        print("\n" + "="*50)
        print("✓ Installation Complete!")
        print("="*50)
        print("\nNext steps:")
        print("  1. Update .env with encryption key if using env storage")
        print("  2. Configure MQTT broker details in config.toml")
        print("  3. Start the application: python run.py")
        print("  4. Access dashboard at http://localhost:5000/")
        
    except KeyboardInterrupt:
        print("\n\n✗ Installation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Installation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
