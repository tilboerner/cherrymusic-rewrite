# -*- coding: UTF-8 -*-
import os
import pathlib
import sqlite3
import threading
from contextlib import closing
from enum import Enum

from cherrymusic.common.types import sentinel

DB_BASEDIR = '/tmp/data/cherrymusic/db'


class TransactionError(Exception):
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

    def transaction(self, **kwargs):
        return SqliteTransaction(self, **kwargs)

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
        return sqlite3.connect(target, **kwargs)

    def _ensure_db_dir(self):
        db_dir, db_file = os.path.split(self.db_path)
        if not os.path.exists(db_dir):
            pathlib.Path(db_dir).mkdir(mode=0o700, parents=True, exist_ok=True)


class SqliteTransaction:
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
            if connection and connection.in_transaction:  # transaction is open with uncommitted changes
                if exc_type or exc_val:
                    connection.rollback()
                else:
                    connection.commit()
        finally:
            self.close()

    def close(self):
        """Close the transaction manually before leaving context, discarding any pending changes"""
        conn = self._connection(may_be_none=True)
        self.__local.connection = None
        if conn:
            conn.close()

    def commit(self):
        """Manually commit any pending changes during the transaction"""
        self._connection().commit()

    def execute(self, sql, params=(), cursor_callback=sqlite3.Cursor.fetchall):
        """Execute SQL with given params and return (by default: all) results"""
        with closing(self._connection().execute(sql, params)) as cursor:
            return cursor_callback(cursor)

    def _connection(self, *, may_be_none=False):
        """Return the active transaction's db connection, or raise appropriate errors"""
        try:
            conn = self.__local.connection
        except AttributeError:
            raise TransactionError(f'Do not share sessions accross threads! ({self})') from None
        if conn is None and not may_be_none:
            raise TransactionError(f'Do not call outside of transaction context! ({self})')
        return conn

    def _create_connection_once(self):
        """Create the db connection for the transaction, or raise an error when one already exists"""
        conn = self._connection(may_be_none=True)
        if conn is not None:
            raise TransactionError(f'Sessions cannot be nested! ({self})')
        conn = self.__local.connection = self.database.connect(
            isolation=self.isolation,
            timeout_secs=self.timeout_secs,
        )
        return conn
