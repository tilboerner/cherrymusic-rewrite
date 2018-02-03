# -*- coding: UTF-8 -*-
import logging
import os
import pathlib
import sys

from cherrymusic.types import CachedProperty, ImmutableNamespace

log = logging.getLogger(__name__)


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


def recursive_scandir(path, *, root=None, filters=()):
    if not root:
        root = path = os.path.abspath(path)
    else:
        root = os.path.abspath(root)
    startpath = os.path.join(root, path)
    start = Path(os.path.relpath(startpath, root), is_dir=os.path.isdir(startpath))

    # path is not a directory -> no recursion
    if not start.is_dir:
        if not os.path.exists(startpath):
            raise FileNotFoundError(f'No such file or directory: {startpath!r}')
        yield start
        return

    # path is a directory -> recursive scanning
    if start != '.':
        yield start
    dirstack = [start]  # LIFO == depth-first
    while dirstack:
        current = dirstack.pop()
        try:
            scanpath = os.path.join(root, current.path)
            dir_entries = os.scandir(scanpath)
            for entry in dir_entries:
                child = current.make_child(
                    entry.name,
                    is_dir=entry.is_dir(),
                    is_symlink=entry.is_symlink(),
                )
                if not all(accept(child) for accept in filters):
                    continue
                if child.is_dir:
                    dirstack.append(child)
                yield child
        except OSError as error:  # pragma: no cover
            log.error('Error scanning directory %r: %s', scanpath, error)
            continue


def canonical_path(path, *, root=None):
    if not os.path.isabs(path):
        if root:
            root = canonical_path(root)
        else:
            getcwd = os.getcwdb if isinstance(path, bytes) else os.getcwd
            root = getcwd()
        path = os.path.join(root, path)
    return os.path.normcase(os.path.realpath(path))  # resolve symlinks and normalize


def circular_symlink_filter(root):
    root = os.fspath(root)
    canonical_root = os.path.join(canonical_path(root), '')  # end in path sep
    known_roots = {canonical_root}

    def is_noncircular_symlink(path):
        try:
            is_link, is_dir = path.is_symlink, path.is_dir
            assert isinstance(is_link, bool)  # pragma: no cover
            assert isinstance(is_dir, bool)  # pragma: no cover
        except AttributeError:
            is_link = os.path.islink(os.path.join(root, path))
            is_dir = os.path.isdir(os.path.join(root, path))
        if is_link and is_dir:
            testpath = os.path.join(canonical_path(path, root=root), '')  # end in path sep
            if any(r.startswith(testpath) or testpath.startswith(r) for r in known_roots):
                log.info('Skipping circular symlink %r -> %r', str(path), testpath)
                return False
            known_roots.add(testpath)
        return True

    return is_noncircular_symlink
