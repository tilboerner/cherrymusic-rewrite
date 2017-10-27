# -*- coding: UTF-8 -*-

"""Common tools and exceptions for data validation"""

import operator
from functools import partial, singledispatch
from itertools import chain
from types import MappingProxyType

from collections import Mapping, Iterable

from cherrymusic.types import sentinel

VALUE = sentinel('VALUE')


def _explain_infix_op(op):
    return lambda a, b: f'{a} {op} {b}'


_EXPLAIN_OP = {
    operator.and_: _explain_infix_op('and'),
    operator.contains: lambda a, b: f'{b} in {a}',  # note reversal of arguments
    operator.eq: _explain_infix_op('=='),
    operator.ge: _explain_infix_op('>='),
    operator.gt: _explain_infix_op('>'),
    operator.is_: _explain_infix_op('is'),
    operator.is_not: _explain_infix_op('is not'),
    operator.le: _explain_infix_op('<='),
    operator.lt: _explain_infix_op('<'),
    operator.ne: _explain_infix_op('!='),
    operator.not_: lambda a: f'not {a}',
    operator.or_: _explain_infix_op('or'),
}


class Call:
    """A "partial application" function call that needs one more positional arg to be executed

    It's like a `functools.partial`, except it will always expect exactly one argument when
    eventually called. It's also possible to mark where that argument will be used with
    `validation.VALUE`, which allows constructs not possible with `functools.partial`::

       >>> Call(isinstance, VALUE, int)(10)
       True

    Args:
        op: A callable that will eventually be called
        *args: Optional positional args to partially apply; values of ``validation.VALUE`` will be
           replaced with the actual value on the final call
        **kwargs: Optional keyword args to partially apply;  values of ``validation.VALUE`` will be
           replaced with the actual value on the final call
    """

    @staticmethod
    def explain(obj, *, depth=0):
        """Get a human-readable str representation of obj

        Args:
            obj: The thing to explain
            depth: Used for recursive calls
        """
        if isinstance(obj, Call):  # pragma: no cover
            return obj._explain(depth=depth)
        if callable(obj):
            return (
                getattr(obj, '__name__', '').replace('_', ' ').strip()
                or
                repr(obj)
            )
        return repr(obj)

    def __init__(self, op, *args, **kwargs):
        self.op = op
        self.args = args
        self.kwargs = MappingProxyType(kwargs)
        if VALUE not in args and VALUE not in kwargs.values():
            self.args += (VALUE,)  # apply VALUE as the final positional arg if not used yet
        if not callable(op):  # pragma: no cover
            raise TypeError(f'op must be callable ({op!r})')

    def __call__(self, value):
        op = self.op
        args = tuple((value if a is VALUE else a) for a in self.args)
        kwargs = {k: (value if a is VALUE else a) for k, a in self.kwargs.items()}
        return op(*args, **kwargs)

    def __repr__(self):
        cls = type(self).__name__
        op = Call.explain(self.op)
        args = self._format_args(repr, self.args, self.kwargs)
        return f'{cls}({op}{", " if args else ""}{args})'

    def __str__(self):
        return self._explain()

    def _explain(self, *, depth=0):
        """Get a human-readable str representation of this Call instance"""
        op, args, kwargs = self.op, self.args, self.kwargs
        explain = partial(Call.explain, depth=depth+1)  # readability: use partial instead of Call
        try:
            custom = _EXPLAIN_OP[op]
        except KeyError:
            result = f'{explain(op)}({self._format_args(explain, args, kwargs)})'
        else:
            result = custom(
                *(explain(a) for a in args),
                **{k: explain(v) for k, v in kwargs.items()}
            )
        if depth:  # pragma: no cover
            result = '(' + result + ')'
        return result

    @classmethod
    def _format_args(cls, fmt, args, kwargs):
        """Get a comma-separated str representation of args and kwargs, by applying `fmt` to them"""
        return ', '.join(
            chain(
                (fmt(a) for a in args),
                (f'{k}={fmt(v)}' for k, v in kwargs.items()),
            ))


# noinspection PyMethodParameters
class ValidationError(ValueError):

    @singledispatch
    def to_message(obj):
        if isinstance(obj, ValidationError):
            return obj.args[0]
        if isinstance(obj, type):
            return obj.__qualname__
        return str(obj).strip() or type(obj).__qualname__

    @to_message.register(str)
    def _(msg):
        return msg.strip()

    @to_message.register(Mapping)
    def _(mapping):
        return {key: ValidationError.to_message(value) for key, value in mapping.items()}

    @to_message.register(Iterable)
    def _(iterable):
        items = set(ValidationError.to_message(item) for item in iterable)
        return items.pop() if len(items) == 1 else tuple(sorted(items))

    def __init__(self, msg='Invalid value'):
        msg = ValidationError.to_message(msg)
        assert isinstance(msg, (str, dict, tuple))
        super().__init__(msg)

    def merge(self, error):
        one, two = self.args[0], ValidationError.to_message(error)
        merged = self._merge_messages(one, two)
        return ValidationError(merged)

    @classmethod
    def _merge_messages(cls, one, two):
        two_is_better = (
            (isinstance(two, dict) and not isinstance(one, dict)) or
            (isinstance(two, tuple) and not isinstance(one, (dict, tuple)))
        )
        if two_is_better:
            one, two = two, one
        if isinstance(one, dict):
            if not isinstance(two, dict):
                two = {'*': two}
            merged = {}
            for key, value in chain(one.items(), two.items()):
                if key in merged:
                    value = cls._merge_messages(merged[key], value)
                merged[key] = value
        elif isinstance(one, tuple):
            if not isinstance(two, tuple):
                two = (two,)
            merged = one + two
        else:
            assert isinstance(one, str) and isinstance(two, str), (one, two)
            merged = (one, two)
        return merged


class Check(Call):
    """A Call subtype that will raise a `ValidationError` if the execution result is not truthy"""

    error_cls = ValidationError

    def __call__(self, value):
        ok = super().__call__(value)
        if not ok:
            cls = type(self).__qualname__
            raise self.error_cls(f'{cls} failed: [ {self} ] for {VALUE}={value!r}')
        return ok
