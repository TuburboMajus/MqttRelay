# Storage repository layer - provides similar interface to temod.storage
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc
from typing import List, Dict, Any, Optional, Type, TypeVar, Generic
from core.db import get_session
from core.models import Base

T = TypeVar('T', bound=Base)


class Repository(Generic[T]):
    """Generic repository for entity access (similar to temod.storage)."""
    
    def __init__(self, model: Type[T]):
        self.model = model
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return get_session()
    
    def get(self, **filters) -> Optional[T]:
        """
        Get a single entity by filters.
        Example: repo.get(id=1) or repo.get(email="test@example.com")
        """
        session = self.get_session()
        try:
            query = session.query(self.model)
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)
            return query.first()
        finally:
            session.close()
    
    def list(self, *conditions, orderby: Optional[str] = None, limit: Optional[int] = None, 
             offset: Optional[int] = None, **filters) -> List[T]:
        """
        List entities matching conditions.
        Example: repo.list(Equals(...), orderby="name ASC", limit=10)
        For backward compatibility, also supports kwargs: repo.list(active=True)
        """
        session = self.get_session()
        try:
            query = session.query(self.model)
            
            # Apply conditions (for advanced filtering)
            for condition in conditions:
                # Conditions can be SQLAlchemy filter expressions
                if hasattr(condition, 'compile'):
                    query = query.filter(condition)
            
            # Apply simple filters
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)
            
            # Apply ordering
            if orderby:
                parts = orderby.split()
                col_name = parts[0]
                direction = parts[1].upper() if len(parts) > 1 else "ASC"
                
                if hasattr(self.model, col_name):
                    col = getattr(self.model, col_name)
                    if direction == "DESC":
                        query = query.order_by(desc(col))
                    else:
                        query = query.order_by(asc(col))
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Apply offset
            if offset:
                query = query.offset(offset)
            
            return query.all()
        finally:
            session.close()
    
    def count(self, *conditions, **filters) -> int:
        """
        Count entities matching conditions.
        Example: repo.count(active=True)
        """
        session = self.get_session()
        try:
            query = session.query(self.model)
            
            # Apply conditions
            for condition in conditions:
                if hasattr(condition, 'compile'):
                    query = query.filter(condition)
            
            # Apply filters
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)
            
            return query.count()
        finally:
            session.close()
    
    def create(self, entity: T) -> T:
        """
        Create and persist a new entity.
        Example: repo.create(User(email="test@example.com", ...))
        """
        session = self.get_session()
        try:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def update(self, entity: T, **updates) -> T:
        """
        Update an existing entity.
        Example: repo.update(user, email="newemail@example.com")
        """
        session = self.get_session()
        try:
            merged = session.merge(entity)
            for key, value in updates.items():
                if hasattr(merged, key):
                    setattr(merged, key, value)
            session.commit()
            session.refresh(merged)
            return merged
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def delete(self, entity_or_id: Any = None, id: Any = None, many: bool = False, **filters) -> bool:
        """
        Delete entity or entities.
        Example: repo.delete(user) or repo.delete(id=1) or repo.delete(rule_id=123, many=True)
        """
        session = self.get_session()
        try:
            if entity_or_id is not None:
                # Delete by entity instance
                merged = session.merge(entity_or_id)
                session.delete(merged)
            elif id is not None:
                # Delete by id
                entity = session.query(self.model).filter(self.model.id == id).first()
                if entity:
                    session.delete(entity)
            elif filters and many:
                # Delete multiple by filters
                query = session.query(self.model)
                for key, value in filters.items():
                    if hasattr(self.model, key):
                        query = query.filter(getattr(self.model, key) == value)
                query.delete()
            elif filters:
                # Delete single by filters
                query = session.query(self.model)
                for key, value in filters.items():
                    if hasattr(self.model, key):
                        query = query.filter(getattr(self.model, key) == value)
                entity = query.first()
                if entity:
                    session.delete(entity)
            
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def generate_value(self, field_name: str) -> Any:
        """
        Generate a value for a field (mainly for IDs).
        For UUIDs, generates a new UUID string.
        """
        if field_name == 'id':
            import uuid
            return str(uuid.uuid4())
        return None


# Convenience instances for common entities
def get_repository(model: Type[T]) -> Repository[T]:
    """Factory to create a repository for a given model."""
    return Repository(model)


# Example: Create repositories for each model
from core.models import (
    User, Privilege, Client, ClientDestination, Device, DeviceType,
    MqttMessage, MqttTopic, Parser, Metric, ParsedPoint, Extraction,
    RoutingRule, RouteDeposit, Dispatch, CryptoConfig, CryptoKey, Job, Language
)

# These can be used like: repos['User'].get(id=1), repos['Client'].list()
repos = {
    'User': Repository(User),
    'Privilege': Repository(Privilege),
    'Client': Repository(Client),
    'ClientDestination': Repository(ClientDestination),
    'Device': Repository(Device),
    'DeviceType': Repository(DeviceType),
    'MqttMessage': Repository(MqttMessage),
    'MqttTopic': Repository(MqttTopic),
    'Parser': Repository(Parser),
    'Metric': Repository(Metric),
    'ParsedPoint': Repository(ParsedPoint),
    'Extraction': Repository(Extraction),
    'RoutingRule': Repository(RoutingRule),
    'RouteDeposit': Repository(RouteDeposit),
    'Dispatch': Repository(Dispatch),
    'CryptoConfig': Repository(CryptoConfig),
    'CryptoKey': Repository(CryptoKey),
    'Job': Repository(Job),
    'Language': Repository(Language),
}
