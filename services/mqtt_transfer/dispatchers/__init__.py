from .mysql import MysqlDispatcher
from .postgres import PostgresDispatcher

DISPATCHERS = {
    "mysql": MysqlDispatcher,
    "postgres": PostgresDispatcher,
    "postgresql": PostgresDispatcher,
}
