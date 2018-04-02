# -*- coding: UTF-8 -*-
import logging
import os
import pathlib

from .data import Path

log = logging.getLogger(__name__)


def recursive_scandir(path, *, root=None, filters=(), max_depth=None):
    if not root:
        root = startpath = os.path.abspath(path)
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
        # start is not root
        yield start
    dirstack = [start]  # LIFO == depth-first
    while dirstack:
        current = dirstack.pop()
        if max_depth and current.depth - start.depth > max_depth:
            continue
        scanpath = os.path.join(root, current.path)
        try:
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


def hidden_file_filter():
    return lambda path: (
        path.name[0:1] != '.' and
        all(part[0] != '.' for part in pathlib.PurePath(path.parent).parts)
    )
