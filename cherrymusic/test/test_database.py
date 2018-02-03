# -*- coding: UTF-8 -*-
import sqlite3
from contextlib import closing
from functools import wraps
from unittest import mock

import pytest

from cherrymusic import database
from cherrymusic.database import ISOLATION
from cherrymusic.test import helpers


def test_sqlitedatabase():
    db = database.SqliteDatabase(':memory:')
    with db.connect() as connection:
        assert isinstance(connection, sqlite3.Connection)
    with db.session() as session:
        assert isinstance(session, database.SqliteSession)


def _testdb(name=':memory:', *statements):
    """Create a SqliteDatabase and run some initial statements"""
    db = database.SqliteDatabase(name if name == ':memory:' else f'testdb.{name}')
    with db.connect() as conn:
        with closing(conn.cursor()) as cursor:
            for stmt in statements:
                cursor.execute(stmt)
    return db


def _temp_db_dir(func):
    """Decorator to use a temporary database directory to work with actual files"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with helpers.tempdir() as tempdir:
            with mock.patch.object(database, 'DB_BASEDIR', tempdir):
                func(*args, **kwargs)

    return wrapper


def test_session_errors_when_not_in_context():
    db = _testdb()
    session = db.session()

    with pytest.raises(database.SessionError):
        session.commit()

    with pytest.raises(database.SessionError):
        session.execute('SELECT 1;')


def test_session_errors_when_nesting():
    db = _testdb()
    session = db.session()

    with session:
        with pytest.raises(database.SessionError):
            with session:
                pass  # pragma: no cover


def test_session_enforces_threadlocal():
    from concurrent.futures import ThreadPoolExecutor
    db = _testdb()
    session = db.session()

    def use_session(s):
        with s:
            pass  # pragma: no cover

    with ThreadPoolExecutor() as executor:
        with pytest.raises(database.SessionError):
            executor.submit(use_session, session).result()


@_temp_db_dir
def test_session_auto_commit_and_rollback():
    db = _testdb('autosession', 'CREATE TABLE test(a)')

    with db.session() as session:
        session.execute('INSERT INTO test VALUES(1);')
    with pytest.raises(Exception):
        with db.session() as session:
            session.execute('INSERT INTO test VALUES(2);')
            raise Exception

    with db.session() as check:
        assert check.execute('SELECT * FROM test;') == [(1,)]


@_temp_db_dir
def test_session_isolation():
    # see https://sqlite.org/lang_transaction.html
    db = _testdb('isolation', 'CREATE TABLE test(x);')

    def session(isolation=ISOLATION.DEFAULT):
        return db.session(isolation=isolation, timeout_secs=0)

    with session(ISOLATION.EXCLUSIVE), session() as other:  # EXCLUSIVE lock
        with pytest.raises(sqlite3.OperationalError):
            other.execute('SELECT * FROM test;')

        with pytest.raises(sqlite3.OperationalError):
            with session(ISOLATION.EXCLUSIVE):
                pass  # pragma: no cover

        with pytest.raises(sqlite3.OperationalError):
            with session(ISOLATION.IMMEDIATE):
                pass  # pragma: no cover

    with session(ISOLATION.IMMEDIATE) as test_session, session() as other:  # RESERVED lock
        other.execute('SELECT * FROM test;')

        with pytest.raises(sqlite3.OperationalError):
            other.execute('INSERT INTO test VALUES (1);')

        test_session.execute('INSERT INTO test VALUES (2);')
        assert other.execute('SELECT * FROM test;') == []

    with session(ISOLATION.AUTOCOMMIT) as test_session, session() as other:
        other.execute('SELECT * FROM test;')
        test_session.execute('INSERT INTO test VALUES (3);')

        assert other.execute('SELECT * FROM test;') == [(2,), (3,)]
