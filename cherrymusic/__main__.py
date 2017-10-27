# -*- coding: UTF-8 -*-
import os
import sys
from pprint import pprint

from cherrymusic import database, media

p = sys.argv[1] if len(sys.argv) > 1 else '/'
print('cwd:', os.getcwd(), 'pwd:', p)


db = database.get_module_database(media)
migrations = list(database.load_migrations(media))
for migration in reversed(migrations):
    database.apply_migration_to_db(migration, db, backward=True)
for migration in migrations:
    database.apply_migration_to_db(migration, db)

media.update(db, p, root='/home/til')

print(db.db_path)
path_view = media.PathByIdView(db, qualname='')
id_view = media.IdentifyPathView(db, qualname='')
get_paths = path_view.select_all
identify_path = id_view.select_one
# pprint(path_view.select_all(18, 20, 200, 3000))
pprint(get_paths(18, 20, 200, 3000))
pprint(identify_path('Nebenkosten 2017.docx'))

# pprint(db.execute('SELECT * FROM paths WHERE parent_id=? AND depth = ? AND name=?', (45, 2, b"lexandyacc.mobi")))
# pprint(db.execute('SELECT * FROM paths WHERE id=?', (45,)))
# pprint(db.execute('SELECT * FROM paths WHERE name=?', (b"lexandyacc.mobi",)))
pprint(identify_path('Books/lexandyacc.mobi'))
pprint(identify_path('Books/lexandyacc.mobiXDSFE'))

pprint(identify_path('aaa\udcdc'))

pprint(db.execute('SELECT * FROM _versions'))

