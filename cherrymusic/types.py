# -*- coding: UTF-8 -*-
from types import SimpleNamespace


class ImmutableNamespace(SimpleNamespace):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __setattr__(self, key, value):
        raise AttributeError(f"Can't set {type(self).__name__}.{key}, attributes are readonly.")
        # SimpleNamespace does not use __setattr__ on initialization. Implementation detail?


class CachedProperty:
    """A descriptor that shadows itself in the instance dict with the value of the first access

    This only works for classes whose instances have a writable __dict__.
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
