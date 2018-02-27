# -*- coding: UTF-8 -*-
import os
import pathlib
import sys

from cherrymusic.common.types import CachedProperty, ImmutableNamespace


class Path(ImmutableNamespace):

    def __init__(self, name, *, parent=None, **kwargs):
        is_simple_name = (
            isinstance(name, str) and
            name not in ('', '.', '..') and
            os.path.sep not in name and
            not (os.path.altsep and os.path.altsep in name)
        )
        if is_simple_name and isinstance(parent, Path):
            # happy path: almost no normalization needed, depth can simply be incremented
            kwargs.setdefault('depth', parent.depth + 1)
            name = os.path.normcase(name)
            if parent.name == '.':
                parent = parent.parent
            else:
                parent = parent.path
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

    @CachedProperty
    def path(self):  # may contain surrogates from errors='surrogateescape')
        # since self.name and self.parent are normalized, we can concat instead of os.path.join
        parent, name = self.parent, self.name
        path = (parent and parent + os.path.sep) + name
        return sys.intern(path)

    def __fspath__(self):  # may contain surrogates from errors='surrogateescape')
        return self.path

    def __str__(self):  # may contain surrogates from errors='surrogateescape')
        return os.fsdecode(self)

    def __hash__(self):
        return hash(os.fspath(self))

    def __eq__(self, other):
        if self is other:  # pragma: no cover
            return True
        if isinstance(other, Path):  # shortcut: no need to build the actual path
            return self.name == other.name and self.parent == other.parent
        if isinstance(other, (str, bytes, os.PathLike)):
            return os.fspath(self) == os.fspath(other)
        return NotImplemented

    def __ne__(self, other):
        equal = self.__eq__(other)
        if equal is NotImplemented:
            return NotImplemented
        return not equal