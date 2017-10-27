# -*- coding: UTF-8 -*-
from functools import partial
from itertools import zip_longest

from cherrymusic import database

SQL_STATEMENTS = (
    (
        """
          CREATE TABLE paths(
            id INTEGER PRIMARY KEY ASC AUTOINCREMENT NOT NULL UNIQUE,
            name BLOB NOT NULL,
            is_dir INTEGER NOT NULL,
            depth INTEGER NOT NULL CHECK (depth >= 0),
            parent_id INTEGER REFERENCES paths ON DELETE RESTRICT ON UPDATE CASCADE,
            UNIQUE (name, parent_id)
          );
        """,
        """DROP TABLE IF EXISTS paths;""",
    ),
    (
        """
          CREATE TABLE ancestors(
            child_id INTEGER NOT NULL REFERENCES paths ON DELETE CASCADE ON UPDATE CASCADE,
            ancestor_id INTEGER NOT NULL REFERENCES paths ON DELETE CASCADE ON UPDATE CASCADE,
            reldepth INTEGER NOT NULL CHECK (reldepth <= 0),
            UNIQUE (child_id, ancestor_id) ON CONFLICT IGNORE
          );
        """,
        """DROP TABLE IF EXISTS ancestors;"""
    ),
    (
        """
          CREATE INDEX ancestors_child_depth_ancestor 
          ON ancestors(child_id, reldepth, ancestor_id);
        """,
    ),
    (
        """
          CREATE TRIGGER paths_after_insert_create_ancestors 
          AFTER INSERT ON paths
          FOR EACH ROW
          BEGIN
            INSERT INTO ancestors(child_id, ancestor_id, reldepth)
            WITH RECURSIVE new_ancestors(child_id, parent_id, reldepth) AS (
              VALUES(NEW.id, NEW.id, 0)
              UNION ALL
              SELECT 
                previous.child_id, 
                current.parent_id, 
                previous.reldepth - 1 
              FROM 
                paths AS current, 
                new_ancestors AS previous
              WHERE 
                current.id = previous.parent_id AND 
                current.parent_id IS NOT NULL
            )
            SELECT * FROM new_ancestors;
          END;
        """,
    ),
)

_FORWARD_STATEMENTS, _BACKWARD_STATEMENTS = zip_longest(*SQL_STATEMENTS)


class Migration(database.Migration):

    def forward_steps(self, session):
        for sql_statement in _FORWARD_STATEMENTS:
            if sql_statement:
                yield partial(session.execute, sql_statement, ())

    def backward_steps(self, session):
        for sql_statement in _BACKWARD_STATEMENTS:
            if sql_statement:
                yield partial(session.execute, sql_statement, ())
