# -*- coding: UTF-8 -*-
import os

import pytest

from cherrymusic import files
from cherrymusic.common.test.helpers import tempdir


def test_path_attributes():
    assert files.Path('SOME/PARENT/SOME_NAME').name == 'SOME_NAME'
    assert files.Path('SOME/PARENT/SOME_NAME').parent == 'SOME/PARENT'
    assert files.Path('.').is_dir is True
    assert files.Path('SOME/PARENT/NOTHING_EXISTS').is_dir is False
    assert files.Path('SOME/PARENT/NOTHING_EXISTS').is_symlink is False

    sentinel = object()
    assert files.Path('', is_dir=sentinel).is_dir is sentinel
    assert files.Path('', is_symlink=sentinel).is_symlink is sentinel

    assert files.Path('.').name == '.'
    assert files.Path('.').parent == ''
    assert files.Path('..').parent == ''


def test_path_depth():
    assert files.Path('').depth == 0
    assert files.Path('.').depth == 0
    assert files.Path('/.').depth == 0
    assert files.Path('..').depth == -1
    assert files.Path('FOO').depth == 1
    assert files.Path('/FOO').depth == 1
    assert files.Path('/FOO/BAR/').depth == 2
    assert files.Path('FOO').make_child('BAR').depth == 2
    assert files.Path('FOO/BAR').make_child('').depth == 2
    assert files.Path('FOO/BAR').make_child('BAZ').depth == 3


def test_path_equality():
    assert files.Path('SOME_NAME') == files.Path('SOME_NAME')
    assert not (files.Path('SOME_NAME') != files.Path('SOME_NAME'))
    assert hash(files.Path('SOME_NAME')) == hash(files.Path('SOME_NAME'))

    assert files.Path('SOME_NAME') == 'SOME_NAME'
    assert files.Path('.') == '.'
    assert '.' == files.Path('.')
    assert not ('.' != files.Path('.'))

    assert files.Path('') != ''
    assert not (files.Path('') == '')
    assert files.Path('./') != './'

    assert files.Path(b'.') != b'.'
    assert files.Path(b'.') == '.'

    assert files.Path('') != object()
    assert not (files.Path('') == object())

    # HASH & EQUALITY: DICT INDEX BEHAVIOR
    sentinel_a = object()
    sentinel_b = object()
    sentinel_c = object()
    d = {
        'foo': sentinel_a,
        files.Path('foo'): sentinel_b,
        files.Path('foo/./bar/../'): sentinel_c,
    }
    assert d[files.Path('foo/./bar/../')] is sentinel_c
    assert d[files.Path('foo')] is sentinel_c
    assert d['foo'] is sentinel_c


def test_path_is_pathlike():
    assert os.fsencode(files.Path('.')) == b'.'
    assert os.fsencode(files.Path(b'.')) == b'.'
    assert os.fsdecode(files.Path('.')) == '.'


def test_path_normalization():
    assert files.Path('SOME_NAME/') == files.Path('SOME_NAME')
    assert files.Path('SOME_NAME/.') == files.Path('SOME_NAME')
    assert files.Path('SOME_NAME/CHILD/..') == files.Path('SOME_NAME')
    assert files.Path('./').make_child('SOME_NAME') == files.Path('SOME_NAME')


def test_path_root():
    assert files.Path('//.') == files.Path('//')
    assert files.Path('/.//.') == files.Path('/')
    assert files.Path('/./..') == files.Path('/')


def test_path_special_dirs():
    assert files.Path('.') == files.Path('.')
    assert files.Path('') == files.Path('.')
    assert files.Path('./') == files.Path('.')
    assert files.Path('./.') == files.Path('.')
    assert files.Path('./..') == files.Path('..')


def test_path_surrogates():
    assert str(files.Path(b'\xfe')) == '\udcfe'


def test_path_string_attributes_are_interned():
    assert files.Path('SOME_NAME').name is files.Path('SOME_NAME').name
    assert files.Path('PARENT/NAME').path is files.Path('PARENT/NAME').path
    assert files.Path('PARENT/NAME').parent is files.Path('PARENT/NAME').parent


def test_recursive_scandir():
    with tempdir('file', 'dir/subfile') as tmp_path:
        found_paths = {str(p): p for p in files.recursive_scandir(tmp_path)}

    assert found_paths.keys() == {'file', 'dir', 'dir/subfile'}
    assert found_paths['dir'].is_dir is True
    assert found_paths['file'].is_dir is False
    assert found_paths['dir/subfile'].is_dir is False


def test_recursive_scandir_yields_startpath_if_file_or_subdir():
    with tempdir('dir/file') as tmp_dir:
        assert list(files.recursive_scandir('file', root=tmp_dir / 'dir')) == ['file']
        assert list(files.recursive_scandir('dir', root=tmp_dir)) == ['dir', 'dir/file']
        assert list(files.recursive_scandir(tmp_dir / 'dir')) == ['file']


def test_recursive_scandir_filters():
    def no_fizz(path):
        return int(path.name) % 2 != 0

    def no_buzz(path):
        return int(path.name) % 3 != 0

    with tempdir(*[str(i) for i in range(10)]) as tmp_path:
        objs = {
            str(o): o
            for o in files.recursive_scandir(tmp_path, filters=(no_fizz, no_buzz))
        }

    assert objs.keys() == {'1', '5', '7'}


def test_recursive_scandir_symlinks():
    links = {
        'root/link': 'other/file',
        'root/dirlink': 'other/',
    }
    with tempdir(links=links) as tmp_path:
        root_path = tmp_path / 'root'
        objs = {
            str(o): o
            for o in files.recursive_scandir('.', root=root_path)
        }

        assert objs.keys() == {'link', 'dirlink/file', 'dirlink'}
        assert objs['dirlink'].is_dir
        assert not objs['dirlink/file'].is_dir
        assert not objs['link'].is_dir
        assert os.path.samefile(root_path / objs['dirlink/file'], root_path / objs['link'])


def test_recursive_scandir_raises_error_when_invalid_startpath():
    with pytest.raises(FileNotFoundError):
        list(files.recursive_scandir('STARTPATH_DOES_NOT_EXIST'))


def test_canonical_path():
    with tempdir('file', links={'link': 'file'}) as testdir:
        assert files.canonical_path(testdir / 'file') == str(testdir / 'file')
        assert files.canonical_path(testdir / 'file', root=testdir) == str(testdir / 'file')
        assert files.canonical_path('file', root=testdir) == str(testdir / 'file')
        assert files.canonical_path('link', root=testdir) == str(testdir / 'file')
        assert files.canonical_path('.', root='.') == os.getcwd()
        assert files.canonical_path(b'.') == os.getcwdb()


def test_circular_symlink_filter():
    links = {
        'root/safe_always': 'root/links_to_files_are_safe',
        'root/safe_once': 'other/safe_once/',
        'root/above_known_root': 'other/',
        'root/below_known_root': 'other/safe_once/child/',
        'root/back_to_root': 'root/',
        'root/safe_despite_common_suffix': 'other/safe_once_2/'
    }
    with tempdir(links=links) as testpath:
        filter_allows = files.circular_symlink_filter(root=testpath / 'root')

        assert filter_allows('not_a_link')
        assert filter_allows('safe_always') and filter_allows('safe_always')
        assert filter_allows('safe_once') and not filter_allows('safe_once')  # no idempotence!
        assert not filter_allows('above_known_root')
        assert not filter_allows('below_known_root')
        assert not filter_allows('back_to_root')
        assert filter_allows('safe_despite_common_suffix')
