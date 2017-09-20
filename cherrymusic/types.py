# -*- coding: UTF-8 -*-
from types import SimpleNamespace


class ImmutableNamespace(SimpleNamespace):
    """A kind of :cls:`types.SimpleNamespace` that can't change attributes after initialization"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __setattr__(self, key, value):
        # SimpleNamespace does not use __setattr__ on initialization
        raise AttributeError(f"Can't set {type(self).__name__}.{key}, attributes are readonly.")

    def __delattr__(self, key):
        raise AttributeError(f"Can't del {type(self).__name__}.{key}, attributes are readonly.")


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
    """Create one-off objects with a useful repr"""
    def __repr__(_):
        return f'<{name}>'
    return type(name, (), {'__repr__': __repr__})()
