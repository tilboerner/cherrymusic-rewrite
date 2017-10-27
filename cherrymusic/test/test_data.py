# -*- coding: UTF-8 -*-
import pytest

from cherrymusic import data


def test_field_set_name():
    class Test:
        the_name = data.Field()
    assert Test.the_name.name == 'the_name'


def test_field_checks_type():
    class Test:
        field = data.Field(int)
    test = Test()

    test.field = 1
    assert test.field == 1

    test.field = True
    assert test.field is True

    with pytest.raises(ValueError):
        Test().field = 'WRONG TYPE'


def test_field_default_value():
    class Test:
        field = data.Field(int, 0)

    assert Test.field.default == 0
    assert Test().field == 0

    with pytest.raises(ValueError):
        data.Field(int, 'WRONG TYPE')


def test_field_default_implies_type():
    assert data.Field(default=0).type is int

    # exceptions:
    assert data.Field().type is None
    assert data.Field(default=None, null=True).type is None
    assert data.Field(fieldtype=None, default=0).type is None


def test_field_default_can_be_single_positional_arg():
    field = data.Field('DEFAULT')
    assert field.type is str
    assert field.default == 'DEFAULT'

    # exceptions:
    assert data.Field(None).default is data.NOT_SET
    assert data.Field(None).type is None
    assert data.Field(object).default is data.NOT_SET
    assert data.Field(object).type is object


def test_field_is_required_if_no_default():
    assert data.Field().is_required is True
    assert data.Field(default=0).is_required is False

    class Test:
        field = data.Field()

    assert Test.field.is_required is True
    with pytest.raises(AttributeError):
        Test().field


def test_field_nullable():
    with pytest.raises(ValueError):
        data.Field(default=None)
    assert data.Field(default=None, null=True).default is None


def test_field_empty():
    with pytest.raises(ValueError):
        data.Field(default='', empty=False)
    with pytest.raises(ValueError):
        data.Field(default=''), 'checks emptiness by default'
    with pytest.raises(ValueError):
        data.Field().validate(''), 'check works when fieldtype not set'
    with pytest.raises(ValueError):
        data.Field(empty=str.strip).validate('  '), 'may pass custom emptiness function'

    assert data.Field(default='', empty=True).default == ''
    assert data.Field(default=0, empty=False).default == 0


def test_field_custom_validator():
    data.Field(validators=(lambda _: True,)).validate(0)
    data.Field(validators=(lambda _: 'TRUTHY',)).validate(0)
    with pytest.raises(ValueError):
        data.Field(validators=(lambda _: False,)).validate(0)
    with pytest.raises(ValueError):
        data.Field(validators=(lambda _: None,)).validate(0)

    def invalid(_):
        raise data.ValidationError
    with pytest.raises(ValueError):
        data.Field(validators=(invalid,)).validate(object())


def test_field_is_hashable():
    field = data.Field()
    assert field in {field}


def test_derived_field():
    class Test:
        c = 0

        def __init__(self, **kwargs):
            for name, value in kwargs.items():
                setattr(self, name, value)

        @data.DerivedField
        def derived_field(self):
            value = Test.c
            Test.c += 1
            return value

    assert Test.derived_field.is_required is False

    assert Test().derived_field == 0
    assert Test().derived_field == 1

    test = Test()
    assert test.derived_field == 2 == test.derived_field, 'value is only derived once'

    old = Test.c
    assert Test(derived_field=12345).derived_field == 12345, 'can be initialized'
    assert Test.c == old, 'direct initialization does not call the derived field func'

    assert issubclass(data.DerivedField, data.Field), 'should behave like a Field'


def test_data_meta_defaults():
    class Test(data.DataModel):
        field = data.Field()

    assert Test.get_meta().model is Test
    assert Test.get_meta().namespace == Test.__module__
    assert Test.get_meta().fields == {'field': Test.field}


def test_data_meta_customized():
    class Test(data.DataModel):
        class Meta:
            foo = 'FOO'
            model = object
            namespace = 'MY_NAMESPACE'
        field = data.Field()

    assert Test.get_meta().foo == 'FOO'
    assert Test.get_meta().model is object
    assert Test.get_meta().namespace == 'MY_NAMESPACE'
    assert Test.get_meta().fields == {'field': Test.field}

    assert hasattr(Test, 'Meta') is False


def test_data_as_dict():
    class Test(data.DataModel):
        frst = data.Field(1)
        scnd = data.Field(2)
        thrd = data.Field(3)
        frth = data.Field(4)

    assert list(Test().as_dict().items()) == [('frst', 1), ('scnd', 2), ('thrd', 3), ('frth', 4)]


def test_data_replace():
    class Test(data.DataModel):
        a = data.Field(1)
        b = data.Field(2)
        c = data.Field(3)
        d = data.Field(4)

    assert Test().replace(a=13, d=42).as_dict() == {'a': 13, 'b': 2, 'c': 3, 'd': 42}


def test_data_immutable():
    class Test(data.DataModel):
        a = data.Field()

    with pytest.raises(AttributeError):
        Test(a=13).a = 14
    with pytest.raises(AttributeError):
        del Test(a=13).a
    with pytest.raises(AttributeError):
        data.DataModel().a = 14


def test_data_kwargs():
    class Test(data.DataModel):
        a = data.Field(int)  # no default

    assert data.DataModel().as_dict() == {}
    assert Test(a=99).as_dict() == {'a': 99}
    with pytest.raises(TypeError):
        Test(), 'must give value for field without default'
    with pytest.raises(TypeError):
        data.DataModel(x=1), 'must not use kwargs that are not fields'
    with pytest.raises(ValueError):
        Test(a='NOT_AN_INT')

