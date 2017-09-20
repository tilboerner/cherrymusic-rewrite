# -*- coding: UTF-8 -*-

import os
import pathlib
import tempfile
from contextlib import contextmanager


@contextmanager
def tempdir(*paths, links=None):
    """Contextmanager for a temporary directory, containing given paths and symlinks

    Args:
        paths: strings describing paths that will exist within the tempdir; paths ending in '/' will
            become subdirectories, others will be files
        links: A mapping of {link_path: target_path}, describing symlinks and their target paths
            that will exist within the tempdir; target paths will be created as if they were listed
            in *paths

    Yields:
        A ``pathlib.Path`` object for the temporary directory
    """
    links = links or {}
    with tempfile.TemporaryDirectory() as tmp_path:
        for path in paths:
            create_path(path, parent_dir=tmp_path)
        for link, target in links.items():
            create_symlink_to_target(link, target, parent_dir=tmp_path)
        yield pathlib.Path(tmp_path)


def create_path(path_str, *, parent_dir=None, is_dir=None):
    """Make sure the given path exists as a file or directory

    Intermediate directories will be created if necessary.

    Args:
        path_str: The path that should exist. If it ends with a '/', make sure it's a directory;
            otherwise, make sure it's a file.
        parent_dir: For convenience, if path_str is relative, you can pass the directory it's
            relative to, and we'll do the join for you

    Returns:
        A ``pathlib.Path`` object for the path

    Raises:
        FileExistsError: if the path exists, but is of the wrong type (not a file / not a dir)
    """
    assert not (parent_dir and os.path.isabs(path_str))
    if parent_dir:
        path_str = os.path.join(parent_dir, path_str)
    path = pathlib.Path(path_str)
    if is_dir is True:
        path_str = os.path.join(path_str, '')  # ensure trailing os.path.sep
    elif is_dir is False:
        path_str = path_str.rstrip(os.path.sep)  # remove trailing os.path.sep
    dirpath, basename = os.path.split(path_str)  # path_str ending in '/' will be all dirpath
    if dirpath:
        pathlib.Path(dirpath).mkdir(parents=True, exist_ok=True)
    if basename:
        path.touch(exist_ok=True)
    is_right_type = path.is_dir() if path_str.endswith('/') else path.is_file()
    if not is_right_type:  # pragma: no cover
        assert path.exists()
    return path


def create_symlink_to_target(link_path, target_path, *, parent_dir=None):
    """Make sure there is a symlink at the given path, pointing at the given target

    Intermediate directories will vbe created if necessary; as will be the target_path, according
    to the semantics of :func:`create_path`.

    Args:
        link_path: The path of the symlink itself
        target_path: The path the symlink should refer to
        parent_dir: If ``target_path`` is relative, you can pass the directory it's relative to. In
            that case, if ``link_path`` is also relative, it will be interpreted as relative to that
            same path.

    Raises:
        FileExistsError: If ``link_path`` already exists, but is not a symlink to target_path; or if
            ``target_path`` already exists, but is not the desired type (see :func:`create_path`).
    """
    target_path = create_path(target_path, parent_dir=parent_dir)
    link_path = pathlib.Path(os.path.join(parent_dir or '', link_path))
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(target_path, target_is_directory=target_path.is_dir())
    except FileExistsError:  # pragma: no cover
        is_correct_symlink = link_path.is_symlink() and link_path.resolve() == target_path.resolve()
        if not is_correct_symlink:
            raise
    assert link_path.exists() and link_path.is_symlink()
    return link_path
