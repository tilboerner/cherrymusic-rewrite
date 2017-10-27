# -*- coding: UTF-8 -*-

"""Classes for making shared data structures"""

import operator
import threading
from collections import Container, OrderedDict, Callable
from types import MappingProxyType

from cherrymusic import validation
from cherrymusic.types import ImmutableNamespace, sentinel
from cherrymusic.validation import Check, ValidationError

NOT_SET = sentinel('NOT_SET')


class Field(ImmutableNamespace):
    """Attribute descriptor to be declared at class level, with optional validation

    **Type Inference**
    For convenience, if the `fieldtype` is not explicitly set, it will be inferred from the
    `default` value, unless `default` is not set or set to `None`. This means that you can define
    `fieldtype` and `default` at the same time, by passing a default value that is not ``None`` and
    not a type as the sole positional argument. Set `fieldtype=None` for no inference.

    **Validation**
    Validation happens for default values on initialization and when trying to set a value by
    calling :meth:`__set__`. The following validations take place automatically:

    - ``not null``: rejects ``None``;
    - ``fieldtype`` is a type: values must be ``instanceof(value, (type(None), fieldtype))``;
    - ``not empty``: values must be ``!= type(value)()`` if ``value`` is a Container instance.

    Args:
        fieldtype: `None`, or a type object that values will be validated against; inferred from
            `type(default)` if unspecified and a `default` is provided.
        default: The default value if the field does not explicitly receive a value; must be valid.
                 Do not pass an argument for the field to have no default value and raise an
                 `AttributeError` on read access before a value is set.
        null: if `True`, `None` is an allowed value
        empty: if `True`, values may be empty :cls:`collections.Container` instances
        validators: A sequence of additional callables that evaluate to a falsy result or raise a
            :cls:`ValidationError` if a value is not valid

    Raises:
        ValidationError: if the specified default value is invalid
    """

    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with Field._lock:
            # preserve definition order
            # we could use owner.__dict__, but should wait for its ordered nature to become
            # part of the language spec first, see:
            # https://docs.python.org/3.6/whatsnew/3.6.html#whatsnew36-compactdict
            try:
                Field.__counter += 1
            except AttributeError:
                Field.__counter = 0
            order = Field.__counter
        field = super().__new__(cls, *args, **kwargs)
        field.__dict__['order'] = order
        return field

    def __init__(self,
                 fieldtype=NOT_SET,
                 default=NOT_SET,
                 *,
                 null=NOT_SET,
                 empty=NOT_SET,
                 validators=(),
                 name=None):
        # type inference
        invalid_fieldtype = not (fieldtype in (None, NOT_SET) or isinstance(fieldtype, type))
        if default is NOT_SET and invalid_fieldtype:
            # default value can be passed as first positional arg (if it's not None or a type)
            # and then automatically implies the fieldtype
            default, fieldtype = fieldtype, type(fieldtype)
        elif fieldtype is NOT_SET and default not in (None, NOT_SET):
            # otherwise, fieldtype can still be implied by default value
            fieldtype = type(default)
        if fieldtype is NOT_SET:
            fieldtype = None

        # check args
        if not (fieldtype is None or isinstance(fieldtype, type)):  # pragma: no cover
            raise TypeError(f'fieldtype must be None or a type (is {fieldtype})')
        if not all(map(callable, validators)):  # pragma: no cover
            raise TypeError(f'All validators must be callable ({validators})')

        # init validators
        super_validators = ()
        if null is False:
            super_validators += (
                Check(operator.is_not, validation.VALUE, None),
                # Check(operator.is_not, validation.VALUE, NOT_SET)
            )
        if fieldtype is not None:
            # None values are allowed by this type checker
            valid_types = (fieldtype, type(None))
            super_validators += (Check(isinstance, validation.VALUE, valid_types),)
        if empty is False:
            validator = _make_empty_checker(fieldtype) if fieldtype else _check_value_not_empty
            if validator:
                super_validators += (validator,)
        elif callable(empty):
            super_validators += (empty,)  # may pass custom emptiness check function
        validators = super_validators + tuple(validators)  # make sure to copy validators iterable
        # make sure all validators raise ValidationError unless they return a truthy value:
        validators = tuple(Check(v) if not isinstance(v, Check) else v for v in validators)

        super().__init__(
            default=default,
            empty=empty,
            name=name,  # also set by __set_name__
            null=null,
            type=fieldtype,
            validators=validators,
        )
        if default is not NOT_SET:
            self.validate(default)

    def __set_name__(self, owner, name):
        # called by Python 3.6+ (per PEP-487: https://www.python.org/dev/peps/pep-0487/)
        self.__dict__['name'] = name
        assert self.name == name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        values = instance.__dict__
        key = self.name
        try:
            return values[key]
        except KeyError:
            value = self._get_missing(instance, owner)
            self.validate(value)
            values[key] = value
            return value

    def __set__(self, instance, value):
        self.validate(value)
        instance.__dict__[self.name] = value

    # def __delete__(self, instance):
    #   DO NOT define __delete__, or Field becomes a full-blown data descriptor which won't be able
    #   to (meaningfully) cache values in instance attributes anymore

    def __hash__(self):
        return hash(id(self))

    def validate(self, value):
        if value is NOT_SET:
            raise ValidationError({self.name: 'Please provide a value'})
        for validate in self.validators:
            # print(hex(id(self)), validate)
            try:
                validate(value)
            except ValidationError as error:
                raise ValidationError({self.name: str(error)}) from error

    @property
    def is_required(self):
        return self.default is NOT_SET

    def _get_missing(self, instance, owner):
        default = self.default
        if default is NOT_SET:
            raise AttributeError(f'{owner.__name__!r} object has no attribute {self.name!r}')
        return self.default


def _make_empty_checker(cls):
    if issubclass(cls, Container):
        empty_val = cls()
        return Check(operator.ne, validation.VALUE, empty_val)


@Check
def _check_value_not_empty(value):
    if isinstance(value, Container):
        empty_val = type(value)()
        print(value, empty_val)
        return value != empty_val
    return True
    # check = _make_empty_checker(type(value))
    # return check is None or check(value)


class DerivedField(Field):
    """Field whose value is derivable from a valid owner instance; can still be set explicitly"""

    calculate = Field(Callable, default=None, null=True)

    def __init__(self, fieldtype, *args, **kwargs):
        called_as_func_decorator = (
            not isinstance(fieldtype, type) and
            callable(fieldtype) and
            not (args or kwargs))
        if called_as_func_decorator:
            func, fieldtype = fieldtype, None  # function return type is unknown
        super().__init__(fieldtype, *args, **kwargs)
        if called_as_func_decorator:
            self(func)

    def __call__(self, func):
        if self.calculate is not None:
            raise TypeError(f'Can only set calculate once! (Is {self.calculate})')
        self.__dict__['calculate'] = func

    @property
    def is_required(self):
        return False

    def _get_missing(self, instance, owner):
        return self.calculate(instance)


class DataType(type):
    """Metaclass for classes using fields as attributes"""

    @classmethod
    def __prepare__(mcs, name, bases):
        # return default namespace dict for created class
        return {
            'Meta': type('Meta', (), {}),  # dummy Meta namespace which class can override
            'get_meta': classmethod(mcs.get_meta),
        }

    def __new__(mcs, name, bases, namespace):
        mcs.inject_meta(namespace)

        model_cls = super().__new__(mcs, name, bases, dict(namespace))  # force namespace to dict

        fields = mcs.get_fields(model_cls)
        mcs.set_meta_default_attrs(
            model_cls,
            model=model_cls,
            namespace=model_cls.__module__,
            fields=MappingProxyType(fields),
            required_fields=MappingProxyType({
                name: field for name, field in fields.items() if field.is_required
            })
        )
        return model_cls

    @classmethod
    def get_fields(mcs, model_cls):
        attributes = ((name, getattr(model_cls, name)) for name in dir(model_cls))
        fields = [(name, value) for name, value in attributes if isinstance(value, Field)]
        assert all(name == field.name for name, field in fields), fields
        return OrderedDict(sorted(fields, key=lambda i: i[1].order))

    @classmethod
    def get_meta(mcs, cls_or_instance):
        cls = cls_or_instance if isinstance(cls_or_instance, type) else type(cls_or_instance)
        return getattr(cls, '__meta')

    @classmethod
    def inject_meta(mcs, namespace):
        """Remove namespace['Meta'] and turn it into an immutable instance in namespace['__meta']"""
        custom_meta = namespace.pop('Meta')
        meta_dict = {
            name: getattr(custom_meta, name)
            for name in dir(custom_meta)
            if not name.startswith('__')
        }
        namespace['__meta'] = type('Meta', (ImmutableNamespace,), {})(**meta_dict)

    @classmethod
    def set_meta_default_attrs(mcs, model_cls, **default_attrs):
        meta = mcs.get_meta(model_cls)
        meta_dict = meta.__dict__
        for name, attr in default_attrs.items():
            meta_dict.setdefault(name, attr)


class DataModel(ImmutableNamespace, metaclass=DataType):
    """Immutable type that assumes all attributes are :cls:`Field`"""

    def __init__(self, **kwargs):
        #     meta = DataType.get_meta(self)
        # #     present_keys = kwargs.keys()
        # #     unknown = present_keys - meta.fields.keys()
        # #     if unknown:
        # #         unknown = ', '.join(map(repr, sorted(unknown)))
        # #         raise TypeError(f'Unknown arguments for {type(self).__name__} constructor: {unknown}')
        # #     missing = meta.required_fields.keys() - present_keys
        # #     if missing:
        # #         missing = ', '.join(map(repr, sorted(missing)))
        # #         raise TypeError(f'Missing arguments for {type(self).__name__} constructor: {missing}')
        #     for name, field in meta.fields.items():
        #         field.validate(kwargs.get(name, field.default))
        self.validate(kwargs)
        super().__init__(**kwargs)

    def validate(self, data):
        fields = DataType.get_meta(self).fields
        for name, field in fields.items():
            try:
                value = data.pop(name)
            except KeyError:
                value = getattr(self, name, field.default)
            field.validate(value)
        if data:
            raise ValidationError({k: 'Unknown field' for k in data})

    def as_dict(self, *, cls=dict):
        fields = DataType.get_meta(self).fields
        return cls((name, getattr(self, name)) for name in fields)  # names in fields are ordered

    def replace(self, **kwargs):
        if not kwargs:  # pragma: no cover
            return self
        values = self.as_dict()
        values.update(kwargs)
        return type(self)(**values)
