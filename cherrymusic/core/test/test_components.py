# -*- coding: UTF-8 -*-
import sys
from unittest import mock

import pytest

from cherrymusic.core import components
from cherrymusic.core.components import Component, ComponentType


@pytest.fixture(autouse=True)
def mock_registry():
    with mock.patch.object(components, '_registry', {}) as registry:
        yield registry


def test_component_namespace_pkg_name(mock_registry):

    class A(Component):
        pass

    assert A.namespace == 'core.test'
    assert A.pkg_name == 'cherrymusic.core.test'
    mock_registry.clear()

    class B(Component):
        namespace = 'pytest'

    assert B.namespace == 'pytest'
    assert B.pkg_name == 'cherrymusic.core.test'
    mock_registry.clear()

    class C(Component):
        namespace = '_.pytest'

    assert C.namespace == '_.pytest'
    assert C.pkg_name == 'cherrymusic.core.test'
    mock_registry.clear()

    class D(Component):
        pkg_name = 'pytest'

    assert D.namespace == 'pytest'
    assert D.pkg_name == 'pytest'

    class E(Component):
        namespace = '.pytest'

    assert E.namespace == '.pytest'


# noinspection PyUnusedLocal,PyShadowingNames
def test_component_registration(mock_registry):

    class LocalComponent(Component):
        pass

    component = mock_registry['core.test']

    assert component is LocalComponent
    parent_module = sys.modules[__package__]
    assert component.pkg_name == __package__
    assert component.namespace == 'core.test'

    with pytest.raises(ValueError):
        class LocalComponentWithSameNamespace(Component):
            pass

    with pytest.raises(ImportError):
        class LocalComponentWithUnimportablePkg(Component):
            pkg_name = 'UNIMPORTABLE_MODULE'

    class ExtraLocalComponent(Component):
        namespace = 'OTHER_NAMESPACE'

    assert 'OTHER_NAMESPACE' in mock_registry
    assert set(components.iter_components()) == set(mock_registry.values())


def test_get_component():
    assert components.get_component('core') is components.Component

    with pytest.raises(LookupError):
        components.get_component('pytest')


# noinspection PyShadowingNames
def test_component_may_register_same_type_again(mock_registry):

    class LocalComponent(Component):
        pass

    component = mock_registry['core.test']

    # all of the following should be allowed:
    ComponentType.register(component)
    ComponentType.register(LocalComponent)
    ComponentType(LocalComponent.__name__, (Component,), {})  # same name, defined in same module


def test_component_hashable_equality():

    class A(Component):
        pass

    a1, a2 = A(), A()
    assert a1 is not a2
    assert a1 == a1
    assert a1 != a2
    assert tuple({a1, a1, a2}) in {(a1, a2), (a2, a1)}


def test_components_collective_methods():

    class A(Component):
        namespace = 'A'
        method = mock.Mock()

    class B(Component):
        namespace = 'B'
        method = mock.Mock()

    components.Components().method(42, a=1)

    A.method.assert_called_once_with(42, a=1)
    B.method.assert_called_once_with(42, a=1)


# noinspection PyUnusedLocal
def test_components_reset_order():

    calls = []

    class A(Component):
        namespace = 'A'

        def set_up(self):
            calls.append(f'{type(self).__name__}.set_up')

        def tear_down(self):
            calls.append(f'{type(self).__name__}.tear_down')

    class B(A):
        namespace = 'B'

    components.Components().reset()

    assert calls == ['B.tear_down', 'A.tear_down', 'A.set_up', 'B.set_up']


def test_init_components():

    class A(Component):
        abstract = True
        namespace = 'NA'

    class B(A):
        namespace = 'NB'

    class C(Component):
        namespace = 'NC'
        depends = [(B,), (B, 'foo')]

    result = components.init_components()

    assert sorted(result) == ['NB', 'NC']
    assert isinstance(result['NB'], B)
    assert isinstance(result['NC'], C)
    assert result['NC'].nb is result['NC'].foo is result['NB']


# noinspection PyUnusedLocal
def test_init_components_conflict():

    class A(Component):
        namespace = 'A'

    class B(Component):
        namespace = 'B'
        depends = [(A,), (A,)]

    with pytest.raises(ValueError):
        components.init_components()
