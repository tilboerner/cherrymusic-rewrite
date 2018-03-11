# -*- coding: UTF-8 -*-
import sqlite3
from contextlib import closing
from functools import wraps
from unittest import mock

import pytest

from cherrymusic.common.test import helpers
from cherrymusic.database import sqlite
from cherrymusic.database.sqlite import ISOLATION


def test_sqlitedatabase():
    db = sqlite.SqliteDatabase(':memory:')
    with db.connect() as connection:
        assert isinstance(connection, sqlite3.Connection)
    with db.transaction() as session:
        assert isinstance(session, sqlite.SqliteTransaction)


def _testdb(name=':memory:', *statements):
    """Create a SqliteDatabase and run some initial statements"""
    db = sqlite.SqliteDatabase(name if name == ':memory:' else f'testdb.{name}')
    with db.connect() as conn:
        with closing(conn.cursor()) as cursor:
            for stmt in statements:
                cursor.execute(stmt)
    return db


def _temp_db_dir(func):
    """Use a temporary database directory to work with actual files"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with helpers.tempdir() as tempdir:
            with mock.patch.object(sqlite, 'DB_BASEDIR', tempdir):
                func(*args, **kwargs)

    return wrapper


def test_transaction_errors_when_not_in_context():
    db = _testdb()
    session = db.transaction()

    with pytest.raises(sqlite.TransactionError):
        session.commit()

    with pytest.raises(sqlite.TransactionError):
        session.execute('SELECT 1;')


def test_transaction_errors_when_nesting():
    db = _testdb()
    session = db.transaction()

    with session:
        with pytest.raises(sqlite.TransactionError):
            with session:
                pass  # pragma: no cover


def test_transaction_enforces_threadlocal():
    from concurrent.futures import ThreadPoolExecutor
    db = _testdb()
    session = db.transaction()

    def use_session(s):
        with s:
            pass  # pragma: no cover

    with ThreadPoolExecutor() as executor:
        with pytest.raises(sqlite.TransactionError):
            executor.submit(use_session, session).result()


@_temp_db_dir
def test_transaction_auto_commit_and_rollback():
    db = _testdb('autosession', 'CREATE TABLE test(a)')

    with db.transaction() as session:
        session.execute('INSERT INTO test VALUES(1);')
    with pytest.raises(Exception):
        with db.transaction() as session:
            session.execute('INSERT INTO test VALUES(2);')
            raise Exception

    with db.transaction() as check:
        assert check.execute('SELECT * FROM test;') == [(1,)]


@_temp_db_dir
def test_transaction_isolation():
    # see https://sqlite.org/lang_transaction.html
    db = _testdb('isolation', 'CREATE TABLE test(x);')

    def txn(isolation=ISOLATION.DEFAULT):
        return db.transaction(isolation=isolation, timeout_secs=0)

    with txn(ISOLATION.EXCLUSIVE), txn() as other:  # EXCLUSIVE lock
        with pytest.raises(sqlite3.OperationalError):
            other.execute('SELECT * FROM test;')

        with pytest.raises(sqlite3.OperationalError):
            with txn(ISOLATION.EXCLUSIVE):
                pass  # pragma: no cover

        with pytest.raises(sqlite3.OperationalError):
            with txn(ISOLATION.IMMEDIATE):
                pass  # pragma: no cover

    with txn(ISOLATION.IMMEDIATE) as test_transaction, txn() as other:  # RESERVED lock
        other.execute('SELECT * FROM test;')

        with pytest.raises(sqlite3.OperationalError):
            other.execute('INSERT INTO test VALUES (1);')

        test_transaction.execute('INSERT INTO test VALUES (2);')
        assert other.execute('SELECT * FROM test;') == []

    with txn(ISOLATION.AUTOCOMMIT) as test_transaction, txn() as other:
        other.execute('SELECT * FROM test;')
        test_transaction.execute('INSERT INTO test VALUES (3);')

        assert other.execute('SELECT * FROM test;') == [(2,), (3,)]


def test_database_execute():
    db = _testdb()
    assert db.execute('SELECT 1') == [(1,)]
