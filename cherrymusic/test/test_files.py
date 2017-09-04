# -*- coding: UTF-8 -*-
import os

from cherrymusic import files


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
