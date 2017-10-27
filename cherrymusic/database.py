# -*- coding: UTF-8 -*-
import os
import pathlib
import sqlite3
import threading
from collections import defaultdict
from contextlib import closing
from enum import Enum
from operator import itemgetter

from cherrymusic.types import sentinel

DB_BASEDIR = '/tmp/data/cherrymusic/db'


class SessionError(Exception):
    pass


class ISOLATION(Enum):
    DEFAULT = sentinel('DEFAULT')
    AUTOCOMMIT = None
    DEFERRED = "DEFERRED"
    IMMEDIATE = "IMMEDIATE"
    EXCLUSIVE = "EXCLUSIVE"


class SqliteDatabase:
    """Simple OOP Wrapper for a SQLite database

    Args:
        qualname: The qualified name of the database consists of a number of names separated by
            dots. It gets translated to the file path like by replacing the dots with path
            separators and appending `.sqlite`. Use ':memory:' for an in-memory database.
    """

    _connection_hooks = defaultdict(list)

    @classmethod
    def connection_hook(cls, module):
        qualname = module if isinstance(module, str) else module.__name__

        def decorator(func):
            cls.register_connection_hook(qualname, func)
            return func

        return decorator

    @classmethod
    def register_connection_hook(cls, qualname, hook):
        cls._connection_hooks[qualname].append(hook)

    def __init__(self, qualname):
        self.qualname = qualname
        if qualname == ':memory:':
            self.db_path = ':memory:'
        else:
            subpath = qualname.replace('.', os.path.sep) + '.sqlite'
            self.db_path = os.path.join(DB_BASEDIR, subpath)

    def __repr__(self):
        clsname = type(self).__name__
        return f'{clsname}({self.qualname!r})'

    def execute(self, sql, params=(), *, isolation=ISOLATION.DEFAULT, cursor_callback=None):
        with self.session(isolation=isolation) as session:
            kwargs = {}
            if cursor_callback:
                kwargs['cursor_callback'] = cursor_callback
            return session.execute(sql, params, **kwargs)

    def session(self, **kwargs):
        return SqliteSession(self, **kwargs)

    def connect(self, *, isolation=ISOLATION.DEFAULT, timeout_secs=None):
        """Create a connection to the SQLite database represented by this instance

        Args:
            isolation: Isolation mode; same default as sqlite3.connect
            timeout_secs: Seconds to wait on a locked database; same defaults as sqlite3.connect

        Returns:
            A sqlite3.Connection object for this database

        See Also:
            - https://docs.python.org/3/library/sqlite3.html#sqlite3.connect
            - https://docs.python.org/3/library/sqlite3.html#sqlite3-controlling-transactions
            - https://sqlite.org/lang_transaction.html
        """
        target = self.db_path
        if target != ':memory:':
            self._ensure_db_dir()
        kwargs = {}
        if isolation is not ISOLATION.DEFAULT:
            kwargs['isolation_level'] = isolation.value
        if timeout_secs is not None:
            kwargs['timeout'] = timeout_secs

        connection = sqlite3.connect(target, **kwargs)

        for hook in self.connection_hooks:
            hook(connection)

        return connection

    @property
    def connection_hooks(self):
        if self.qualname in self._connection_hooks:
            yield from self._connection_hooks[self.qualname]

    def _ensure_db_dir(self):
        db_dir, db_file = os.path.split(self.db_path)
        if not os.path.exists(db_dir):
            pathlib.Path(db_dir).mkdir(mode=0o700, parents=True, exist_ok=True)


class SqliteSession:
    """Context manager that wraps an sqlite3.Connection, with commit or rollback on exit

    ..note:: Session contexts can not be nested.
    """

    def __init__(self, database, *, isolation=ISOLATION.DEFAULT, timeout_secs=3):
        self.database = database
        self.isolation = isolation
        self.timeout_secs = timeout_secs
        self.__local = threading.local()  # we'll cache the connection thead-locally
        self.__local.connection = None  # only the current thread will have this attribute

    def __repr__(self):
        clsname = type(self).__name__
        kwargs = (f'{key}={val!r}' for key, val in self.__dict__.items() if not key.startswith('_'))
        return f"{clsname}({', '.join(kwargs)})"

    def __str__(self):
        is_open = bool(getattr(self.__local, 'connection', None))
        return f"<Session: {self.database}{' *' if is_open else ''}>"

    def __enter__(self):
        self._create_connection_once()

        # Python's sqlite3 module does not immediately issue BEGIN statements to the db,
        # making it difficult to reason about when the necessary locks will be applied.
        # To make the context manager more deterministic, we BEGIN transactions immediately on
        # entering the context, unless DEFAULT or AUTOCOMMIT modes are in force.
        isolation = self.isolation
        if isolation not in {ISOLATION.DEFAULT, ISOLATION.AUTOCOMMIT}:
            self.execute(f'BEGIN {isolation.value}')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        connection = self._connection(may_be_none=True)
        try:
            if connection and connection.in_transaction:  # session is open with uncommitted changes
                if exc_type or exc_val:
                    connection.rollback()
                else:
                    connection.commit()
        finally:
            self.close()

    def close(self):
        """Close the session manually before leaving context, discarding any pending changes"""
        conn = self._connection(may_be_none=True)
        self.__local.connection = None
        if conn:
            conn.close()

    def commit(self):
        """Manually commit any pending changes during the session"""
        self._connection().commit()

    def execute(self, sql, params=(), cursor_callback=sqlite3.Cursor.fetchall):
        """Execute SQL with given params and return (by default: all) results"""
        with closing(self._connection().execute(sql, params)) as cursor:
            return cursor_callback(cursor)

    def _connection(self, *, may_be_none=False):
        """Return the active session's db connection, or raise appropriate errors"""
        try:
            conn = self.__local.connection
        except AttributeError:
            raise SessionError(f'Do not share sessions accross threads! ({self})') from None
        if conn is None and not may_be_none:
            raise SessionError(f'Do not call outside of session context! ({self})')
        return conn

    def _create_connection_once(self):
        """Create the db connection for the session, or raise an error when one already exists"""
        conn = self._connection(may_be_none=True)
        if conn is not None:
            raise SessionError(f'Sessions cannot be nested! ({self})')
        conn = self.__local.connection = self.database.connect(
            isolation=self.isolation,
            timeout_secs=self.timeout_secs,
        )
        return conn


class SqliteView:

    @classmethod
    def from_sql_func(cls, func):
        return type(func.__name__, (cls,), {'make_query': staticmethod(func)})

    def __init__(self, executor, qualname):
        self.executor = executor
        self.qualname = qualname

    def make_query(self, **kwargs):
        qualname = self.qualname
        param_names = sorted(kwargs)
        param_values = tuple(kwargs[name] for name in param_names)
        if param_names:
            clauses = ' AND '.join(f'{name} = ?' for name in param_names)
            sql = f'SELECT * FROM {qualname} WHERE {clauses}'
        else:
            sql = f'SELECT * FROM {qualname}'
        return sql, param_values

    def select_one(self, *args, **kwargs):
        sql, params = self.make_query(*args, **kwargs)
        result = self.executor.execute(
            sql,
            params,
            cursor_callback=self._fetch_single_item_from_cursor,
        )
        if result is not None:
            return next(self.process_results([result]))

    def select_all(self, *args, **kwargs):
        sql, params = self.make_query(*args, **kwargs)
        results = self.executor.execute(
            sql,
            params,
            cursor_callback=self._fetch_all_items_from_cursor,
        )
        return list(self.process_results(results))

    @staticmethod
    def get_row_factory(cursor):
        keys = tuple(map(itemgetter(0), cursor.description))

        def row_factory(cursor_, row):
            assert cursor_ is cursor
            return dict(zip(keys, row))

        return row_factory

    process_result = staticmethod(lambda r: r)

    @classmethod
    def process_results(cls, results):
        process = cls.process_result
        return (process(r) for r in results)

    @staticmethod
    def _fetch_single_item_from_cursor(cursor):
        cursor.row_factory = SqliteView.get_row_factory(cursor)
        return cursor.fetchone()

    @staticmethod
    def _fetch_all_items_from_cursor(cursor):
        cursor.row_factory = SqliteView.get_row_factory(cursor)
        return cursor.fetchall()


def get_module_database(owner_module):
    return SqliteDatabase(owner_module.__name__)


def apply_migration_to_db(migration, db, *, backward=False):
    with db.session(isolation=ISOLATION.EXCLUSIVE, timeout_secs=0) as session:
        session.execute("""
            CREATE TABLE IF NOT EXISTS _versions(name, comment, direction, applied_at_utc)
        """)
        steps = migration.backward_steps if backward else migration.forward_steps

        for step in steps(session):
            step()

        from datetime import datetime
        version = {
            'name': migration.name,
            'comment': migration.comment,
            'direction': 'BACKWARD' if backward else 'FORWARD',
            'applied_at_utc': datetime.utcnow().isoformat()
        }
        session.execute(
            """
              INSERT INTO _versions(name, comment, direction, applied_at_utc)
              VALUES (:name, :comment, :direction, :applied_at_utc);
            """,
            version
        )


def load_migrations(owner_module):
    from importlib import import_module
    owner_name = owner_module.__name__

    # get owner's migrations package
    migrations_package_name = f'{owner_name}.migrations'
    try:
        import sys
        migrations_package = sys.modules[migrations_package_name]
    except KeyError:
        migrations_package = import_module(migrations_package_name)
    assert hasattr(migrations_package, '__file__')  # must not be namespace package
    assert hasattr(migrations_package, '__path__')  # must be package

    # scan migrations package dir for eligible .py files
    migration_dir = os.path.dirname(migrations_package.__file__)
    migration_names = []
    for dir_entry in os.scandir(migration_dir):
        name = dir_entry.name
        if dir_entry.is_file() and name[0] not in '~_.' and name.endswith('.py'):
            migration_name, _ = name.rsplit('.', 1)
            migration_names.append(migration_name)

    # load migration modules from found names
    for migration_name in sorted(migration_names):
        migration_module = import_module(migrations_package_name + '.' + migration_name)
        assert issubclass(getattr(migration_module, 'Migration', None), Migration)
        yield migration_module.Migration(migration_name, owner_name)


class Migration:

    def __init__(self, name, module_name):
        if '_' in name[1:]:
            self.name, self.comment = name.split('_', 1)
        else:
            self.name, self.comment = name, ''
        self.module_name = module_name

    def forward_steps(self):
        raise NotImplementedError

    def backward_steps(self):
        raise NotImplementedError
