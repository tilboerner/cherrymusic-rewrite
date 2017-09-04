# -*- coding: UTF-8 -*-

import os
import pathlib
import sys

from cherrymusic.types import ImmutableNamespace, CachedProperty


class Path(ImmutableNamespace):

    def __init__(self, name, *, parent=None, **kwargs):
        is_simple_name = (
            isinstance(name, str) and
            name not in ('', '.', '..') and
            os.path.sep not in name and
            (not os.path.altsep or os.path.altsep not in name)
        )
        if is_simple_name and isinstance(parent, Path):
            # happy path: almost no normalization needed, depth can simply be incremented
            kwargs.setdefault('depth', parent.depth + 1)
            name = os.path.normcase(name)
            parent = os.path.join(parent.parent, parent.name)
        else:
            # force to str and normalize (strs may contain surrogates from errors='surrogateescape')
            path = os.path.join(*map(os.fsdecode, (parent or '', name)))
            normpath = os.path.normcase(os.path.normpath(path))
            parent, name = os.path.split(normpath)
        # intern strings for quick comparisons and dict lookups
        parent = sys.intern(parent)
        name = sys.intern(name)
        super().__init__(name=name, parent=parent, **kwargs)

    @CachedProperty
    def depth(self):
        ppath = pathlib.PurePath(self)
        if ppath.root or ppath.drive:
            pparts = ppath.parts[1:]
        else:
            pparts = ppath.parts
        return sum(-1 if p == '..' else 1 for p in pparts)  # '.' is never in PurePath.parts

    @CachedProperty
    def is_dir(self):
        return os.path.isdir(self)

    @CachedProperty
    def is_symlink(self):
        return os.path.islink(self)

    def make_child(self, other, **kwargs):
        return type(self)(other, parent=self, **kwargs)

    @property
    def path(self):
        return sys.intern(os.path.join(self.parent, self.name))

    def __fspath__(self):
        return os.path.join(self.parent, self.name)

    def __str__(self):
        return os.fsdecode(self)  # may contain surrogates from errors='surrogateescape')

    def __hash__(self):
        return hash(os.fspath(self))

    def __eq__(self, other):
        if self is other:  # pragma: no cover
            return True
        if not isinstance(other, (str, os.PathLike, bytes)):
            return NotImplemented
        return os.fspath(self) == os.fspath(other)

    def __ne__(self, other):
        if self is other:  # pragma: no cover
            return False
        if not isinstance(other, (str, os.PathLike, bytes)):
            return NotImplemented
        return not (os.fspath(self) == os.fspath(other))
