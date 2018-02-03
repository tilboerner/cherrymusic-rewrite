# -*- coding: UTF-8 -*-
import pytest

from cherrymusic import types


def test_immutablenamespace():
    assert types.ImmutableNamespace(a=42).a == 42
    assert types.ImmutableNamespace(a=42).__dict__ == {'a': 42}

    with pytest.raises(AttributeError):
        types.ImmutableNamespace(a=42).a = 666

    with pytest.raises(AttributeError):
        types.ImmutableNamespace().b = 43

    with pytest.raises(AttributeError):
        del types.ImmutableNamespace(a=42).a


def test_cachedproperty():
    class Class:
        @types.CachedProperty
        def value(self):
            try:
                self.callcount += 1
            except AttributeError:
                # noinspection PyAttributeOutsideInit
                self.callcount = 1
            return self.callcount

    instance = Class()
    assert instance.value == 1  # first access: descriptor calls property function, sets attribute
    assert instance.value == 1  # following accesses: instance attribute shadows descriptor

    del instance.value          # deleting instance attribute makes descriptor visible
    assert instance.value == 2  # descriptor calls property function again

    instance.value += 1         # increment instance property
    assert instance.value == 3  # yes, it got increased
    assert instance.callcount == 2  # property function was not called!

    with pytest.raises(AttributeError):
        del Class().value       # instance attribute does not exist before descriptor call
