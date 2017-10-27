# -*- coding: UTF-8 -*-
from types import SimpleNamespace

import threading


class ImmutableNamespace(SimpleNamespace):
    """A kind of :cls:`types.SimpleNamespace` that can't change attributes after initialization"""

    def __setattr__(self, key, *args, **kwargs):
        # SimpleNamespace does not use __setattr__ on initialization
        raise AttributeError(f"Can't modify {type(self).__name__}.{key}, attributes are read-only.")

    __delattr__ = __setattr__


class CachedProperty:
    """A descriptor that replaces itself with the return value of the first access

    It works like a regular property, but does not define `__set__` and `__delete__` methods, which
    means Python will try to access actual instance attributes before falling back to the
    descriptor.
    (See `Python doc <https://docs.python.org/3/howto/descriptor.html#descriptor-protocol>`_.)

    The descriptor takes advantage of this mechanism by writing the result of its first access into
    the instance's `__dict__` under its own name, effectively shadowing itself with the resulting
    instance attribute.

    Note:
        This only works for classes whose instances have a writable `__dict__`.

    Args:
        getter: A function to determine the value of the property; it will receive the instance
                as its sole argument.
    """

    def __init__(self, getter):
        assert callable(getter)
        self.getter = getter

    def __set_name__(self, owner, name):
        # called by Py3.6+
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:  # pragma: no cover
            return self
        cache = instance.__dict__
        key = self.name
        try:
            return cache[key]
        except KeyError:
            result = self.getter(instance)
            cache[key] = result
            return result


def sentinel(name):
    """A unique, one-off object with a useful repr"""
    def __repr__(_):
        return f'<{name}>'
    return type(name, (), {'__repr__': __repr__})()


class MemoizedProperty:

    def __init__(self, getter):
        from weakref import WeakKeyDictionary
        self.cache = WeakKeyDictionary
        self.getter = getter

    def __get__(self, instance, owner):
        if instance is None:
            return self
        cache = self.cache
        try:
            return cache[instance]
        except KeyError:
            cache[instance] = value = self.getter(instance)
            return value


def memoized_method(getter):
    from functools import wraps
    from weakref import WeakKeyDictionary
    cache = WeakKeyDictionary()
    local = threading.local()

    @wraps(getter)
    def wrapper(instance):
        if hasattr(local, 'active'):
            return getter(instance)
        local.active = True
        try:
            return cache[instance]
        except KeyError:
            cache[instance] = value = getter(instance)
            return value
        finally:
            del local.active
    return wrapper
