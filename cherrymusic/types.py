# -*- coding: UTF-8 -*-
from collections import MutableMapping
from types import SimpleNamespace
from weakref import WeakKeyDictionary


class ImmutableNamespace(SimpleNamespace):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __setattr__(self, key, value):
        raise AttributeError(f"Can't set {type(self).__name__}.{key}, attributes are readonly.")
        # SimpleNamespace does not use __setattr__ on initialization. Implementation detail?


class CachedProperty:
    """A descriptor that shadows itself in the instance dict with the value of the first access

    It works like a regular property, but does not define `__set__` and `__delete__` methods, which
    means Python will try to access actual instance attributes before falling back to the
    descriptor.
    (See `Python doc <https://docs.python.org/3/howto/descriptor.html#descriptor-protocol>`_.)

    The descriptor takes advantage of this mechanism by writing the result of its first access into
    the instance's `__dict__` under its own name, effectively shadowing itself with the resulting
    instance attribute.

    Note:
        This only works for classes whose instances have a writable `__dict__`.
        You can use a different cache (and key function) by using the respective init kwargs.

    Args:
        getter: A function to determine the value of the property; it will receive the instance
                as its sole argument.
        cache: A MutableMapping to use as cache instead of `instance.__dict__`.
        key: A function to derive the cache key from the arguments (descriptor, instance, owner).
             If none is specified, the instance will be used as the cache key.
    """

    def __init__(self, getter, *, cache=None, key=None):
        assert callable(getter)
        assert cache is None or isinstance(cache, MutableMapping)
        self.getter = getter
        self.cache = cache
        self.key = key

    def __set_name__(self, owner, name):
        # called by Py3.6+
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:  # pragma: no cover
            return self
        if self.cache is None:
            cache = instance.__dict__
            key = self.name
        else:
            cache = self.cache
            key = instance if self.key is None else self.key(self, instance, owner)
        try:
            return cache[key]
        except KeyError:
            result = self.getter(instance)
            cache[key] = result
            return result


class WeakrefCachedProperty(CachedProperty):
    def __init__(self, getter):
        super().__init__(getter, cache=WeakKeyDictionary())
