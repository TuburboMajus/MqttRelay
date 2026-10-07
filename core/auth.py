# Authentication helpers for SQLAlchemy-based user management
from flask_login import UserMixin, current_user
from flask import abort
from core.models import User as UserModel
from core.repository import repos
import bcrypt
import functools
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

    @property
    def roles(self):
        """Roles granted to this user, read through the linked Privilege row.

        Privilege.roles is stored as a single semicolon-delimited String(256)
        column (no relational roles table), so split on ';' here. The
        underlying User row is detached from its session by the time this is
        read (repos close their session after each call), so the privilege is
        looked up explicitly rather than through the (now unusable) lazy
        relationship.
        """
        if not self._user.privilege_id:
            return set()
        privilege = repos['Privilege'].get(id=self._user.privilege_id)
        if not privilege or not privilege.roles:
            return set()
        return {role.strip() for role in privilege.roles.split(';') if role.strip()}

    def get_id(self):
        return str(self._user.id)
    
    def __repr__(self):
        return f"<User {self.email}>"


MIN_PASSWORD_LENGTH = 8


def validate_password(pwd: str) -> Optional[str]:
    """Validate a candidate password's length.

    Returns 'password_too_short' when pwd is falsy or shorter than
    MIN_PASSWORD_LENGTH, else None.
    """
    if not pwd or len(pwd) < MIN_PASSWORD_LENGTH:
        return 'password_too_short'
    return None


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


def roles_required(*roles):
    """Route decorator that aborts with HTTP 403 unless the current user's
    roles intersect the given required role set.
    """
    required_roles = set(roles)

    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            user_roles = getattr(current_user, 'roles', set())
            if not (user_roles & required_roles):
                return abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator
