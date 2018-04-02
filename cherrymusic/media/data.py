# -*- coding: UTF-8 -*-
import os
import pathlib
import sys
from urllib.parse import quote_from_bytes, unquote_to_bytes

from cherrymusic.common.types import CachedProperty, FrozenNamespace


def _pathcodec():
    # This works very much like os.fs(en|de)code, except that encoding and error handling
    # remain parameters.
    fs_encoding = sys.getfilesystemencoding()
    fs_errors = sys.getfilesystemencodeerrors()  # probably 'surrogateescape'
    fspath = os.fspath

    def encode_path(path, *, encoding=fs_encoding, errors=fs_errors):
        """Encode a path to bytes."""
        path = fspath(path)
        if isinstance(path, str):
            return path.encode(encoding, errors)
        else:  # pragma: no cover
            return path

    def decode_path(path, *, encoding=fs_encoding, errors=fs_errors):
        """Decode a path to str."""
        path = fspath(path)
        if isinstance(path, bytes):
            return path.decode(encoding, errors)
        else:
            return path

    return encode_path, decode_path


encode_path, decode_path = _pathcodec()
del _pathcodec


class Path(FrozenNamespace):

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
            path = os.path.join(*map(decode_path, (parent or '', name)))
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
    def path(self):  # may contain surrogates from errors='surrogateescape'
        # since self.name and self.parent are normalized, we can concat instead of os.path.join
        parent, name = self.parent, self.name
        path = (parent and parent + os.path.sep) + name
        return sys.intern(path)

    @CachedProperty
    def display(self) -> str:
        """Get a display version of the path with easy-on-the-eye placeholders for decode errors.

        .. warning::
        Lossy conversion: information un-decodable bytes will be unrecoverably lost, and the
        resulting path will not work in place of the original one.
        """
        bytes_path = encode_path(self.path)  # turn potential surrogate escapes into original bytes
        return decode_path(bytes_path, errors='replace')

    @CachedProperty
    def as_url(self) -> str:
        """Escape path to make it usable in a URL."""
        return quote_from_bytes(bytes(self))

    @classmethod
    def from_url(cls, url_path: str):
        """Turn a URL-escaped path into a Path object."""
        return cls(unquote_to_bytes(url_path))

    def __bytes__(self):
        return encode_path(self.path)

    def __fspath__(self):  # may contain surrogates from errors='surrogateescape')
        return self.path

    def __str__(self):
        return self.display

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
