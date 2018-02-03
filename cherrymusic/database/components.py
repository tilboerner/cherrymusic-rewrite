# -*- coding: UTF-8 -*-
from pathlib import Path

from cherrymusic.core.components import Component


class DatabaseComponent(Component):

    def set_up(self):
        p = Path('/tmp/cherrymusic') / self.namespace.replace('.', '/')
        p.mkdir(mode=0o700, parents=True, exist_ok=True)
