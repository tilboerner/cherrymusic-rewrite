# -*- coding: UTF-8 -*-
import os
from itertools import chain, groupby
from operator import itemgetter

from cherrymusic import files, media
from cherrymusic.database import SqliteDatabase, SqliteView


def update(database, start_path, *, root=None, commit_every=10_000):
    # root = '/home/til'
    filters = (
        files.circular_symlink_filter(root),
        lambda p: not p.name.startswith('.'),  # suppress UNIX hidden files
    )
    iter_paths = files.recursive_scandir(start_path, root=root, filters=filters)

    def quote_param(p):
        return f'"{p}"'

    def ref_param(p):
        return f':{p}'

    # database = SqliteDatabase('media')
    with database.session() as db:
        INSERT_PATH_PARAMS = ('name', 'is_dir', 'parent_id', 'depth')
        INSERT_PATH_SQL = """
            INSERT INTO paths (""" + ','.join(map(quote_param, INSERT_PATH_PARAMS)) + """) 
                 VALUES (""" + ','.join(map(ref_param, INSERT_PATH_PARAMS)) + """);
        """
        path_ids = {}
        import time
        from operator import attrgetter
        t = t0 = time.time()
        for c, path in enumerate(iter_paths, start=1):
            parent_id = path_ids.get(path.parent)
            params = {name: getattr(path, name, None) for name in INSERT_PATH_PARAMS}
            params['parent_id'] = parent_id
            params['name'] = os.fsencode(path.name)
            path_id = db.execute(INSERT_PATH_SQL, params, cursor_callback=attrgetter('lastrowid'))
            path_ids[path] = path_id
            if c % 10000 == 0:
                now = time.time()
                passed = now - t
                t = now
                print(path_id, path, f'{passed:.3f}')
            if commit_every and c % commit_every == 0:
                db.commit()
        print(f'{c:,} total in {time.time() - t0:.2}s')


class PathByIdView(SqliteView):

    def make_query(self, id_, *ids):
        ids = (id_,) + ids
        sql = """
            SELECT 
              child_id, reldepth, id, name, is_dir
            FROM 
              paths as path, 
              ancestors as ancestor
            WHERE 
              path.id = ancestor.ancestor_id AND
              ancestor.child_id IN ({placeholders})
            ORDER BY 
              child_id, reldepth
        """.format(placeholders=(', '.join('?' * len(ids))))
        return sql, ids

    def process_results(self, results):
        groups = groupby(results, key=itemgetter('child_id'))
        return [
            os.path.join(*(os.fsdecode(r['name']) for r in group))
            for _, group in groups
        ]


@SqliteView.from_sql_func
def PathByIdView(id_, *ids):
    ids = (id_,) + ids
    sql = """
        SELECT 
          id, 
          name AS "name [bytepath]", 
          is_dir AS "is_dir [bool]", 
          BYTE_PATH(name) AS "path [bytepath]"
        FROM 
          paths as path, 
          ancestors as parent
        WHERE
          path.id = parent.ancestor_id AND 
          parent.child_id IN ({placeholders})
        GROUP BY 
          child_id
        ORDER BY 
          child_id, reldepth
    """.format(placeholders=(', '.join('?' * len(ids))))
    return sql, ids


class BytePath:

    def __init__(self):
        self.aggr = []

    def step(self, val):
        self.aggr.append(val)

    def finalize(self):
        return os.path.join(b'', *self.aggr)

import sqlite3
sqlite3.register_converter("bytepath", os.fsdecode)
sqlite3.register_converter("bool", bool)


@SqliteDatabase.connection_hook(media)
def connection_hook(connection):
    connection.create_aggregate('BYTE_PATH', 1, BytePath)


# class IdentifyPathView(SqliteView):

@SqliteView.from_sql_func
def IdentifyPathView(pathstr):
    if os.path.altsep:
        pathstr = pathstr.replace(os.path.altsep, os.path.sep)
    names = [os.fsencode(p) for p in pathstr.split(os.path.sep)]
    depths = tuple(range(1, len(names) + 1))
    params = tuple(chain.from_iterable(zip(names, depths)))
    if len(names) == 1:
        sql = """
          SELECT id, name, BYTE_PATH(name) AS path, is_dir, depth 
          FROM paths 
          WHERE name = ? AND depth = ?
        """
    else:
        name_depth_clauses = ' OR '.join(f"path.name = ? AND path.depth = ?" for _ in names)
        sql = """
            WITH RECURSIVE recurse(id, name, is_dir, parent_id, depth) AS (
              SELECT id, name, is_dir, parent_id, depth FROM paths WHERE name = ? AND depth = ?
              UNION ALL
              SELECT 
                path.id, path.name, path.is_dir, path.parent_id, path.depth
              FROM 
                paths AS path, 
                recurse AS previous
              WHERE 
                path.parent_id = previous.id AND 
                (
                  {name_depth_clauses}
                )
            ) 
            SELECT * FROM (
              SELECT id, name, BYTE_PATH(name) AS path, is_dir, depth 
              FROM recurse 
              ORDER BY depth
            ) 
            WHERE 
              depth = ?;  -- only return data if all parts found
        """.format(name_depth_clauses=name_depth_clauses)
        params = params[:2] + params + (depths[-1],)
    return sql, params
