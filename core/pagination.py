# Pagination utilities for SQLAlchemy blueprints
from core.repository import Repository
from typing import Any, List, Dict, Optional


class Pagination:
    """Pagination helper for query results."""
    
    def __init__(self, items: List[Any], total: int, page: int = 1, per_page: int = 20):
        self.items = items
        self.total = total
        self.page = page
        self.per_page = per_page
    
    @property
    def current(self) -> List[Any]:
        """Alias for `items`, kept for templates written against the old temod-flask Paginator API."""
        return self.items
    
    @property
    def pages(self) -> int:
        """Total number of pages."""
        return (self.total + self.per_page - 1) // self.per_page
    
    @property
    def has_prev(self) -> bool:
        """Whether there is a previous page."""
        return self.page > 1
    
    @property
    def has_next(self) -> bool:
        """Whether there is a next page."""
        return self.page < self.pages
    
    @property
    def prev_num(self) -> Optional[int]:
        """Number of the previous page."""
        return self.page - 1 if self.has_prev else None
    
    @property
    def next_num(self) -> Optional[int]:
        """Number of the next page."""
        return self.page + 1 if self.has_next else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert pagination to dictionary."""
        return {
            'items': [
                item.to_dict() if hasattr(item, 'to_dict') else item.__dict__
                for item in self.items
            ],
            'total': self.total,
            'page': self.page,
            'per_page': self.per_page,
            'pages': self.pages,
            'has_prev': self.has_prev,
            'has_next': self.has_next,
            'prev_num': self.prev_num,
            'next_num': self.next_num,
        }


def paginate(repo: Repository, page: int = 1, per_page: int = 20, **filters) -> Pagination:
    """
    Paginate repository results.
    
    Args:
        repo: Repository instance
        page: Page number (1-indexed)
        per_page: Items per page
        **filters: Query filters to apply
    
    Returns:
        Pagination object with results
    """
    if page < 1:
        page = 1
    
    offset = (page - 1) * per_page
    
    # Get paginated results
    items = repo.list(offset=offset, limit=per_page, **filters)
    
    # Get total count
    total = repo.count(**filters)
    
    return Pagination(items, total, page, per_page)
