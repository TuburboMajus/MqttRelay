# Authentication helpers for SQLAlchemy-based user management
from flask_login import UserMixin
from core.models import User as UserModel
from core.repository import repos
import bcrypt
from typing import Optional


class SQLAlchemyUserProxy(UserMixin):
    """Proxy object that implements Flask-Login UserMixin for SQLAlchemy User model."""
    
    def __init__(self, user: UserModel):
        self._user = user
    
    @property
    def id(self):
        return self._user.id
    
    @property
    def is_active(self):
        return self._user.is_active and not self._user.is_disabled
    
    @property
    def is_authenticated(self):
        # Flask-Login contract: any successfully loaded user is authenticated.
        # The `user.is_authenticated` DB column is never set by the login flow,
        # so delegating to it would lock every user out right after login.
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    @property
    def email(self):
        return self._user.email
    
    @property
    def privilege_id(self):
        return self._user.privilege_id
    
    def get_id(self):
        return str(self._user.id)
    
    def __repr__(self):
        return f"<User {self.email}>"


def hash_password(password: str) -> bytes:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())


def verify_password(password: str, hashed: bytes) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)


def authenticate_user(email: str, password: str) -> Optional[SQLAlchemyUserProxy]:
    """Authenticate a user by email and password."""
    user = repos['User'].get(email=email)
    if user and verify_password(password, user.password):
        return SQLAlchemyUserProxy(user)
    return None


def get_user_by_id(user_id: str) -> Optional[SQLAlchemyUserProxy]:
    """Get a user by ID."""
    user = repos['User'].get(id=user_id)
    return SQLAlchemyUserProxy(user) if user else None
