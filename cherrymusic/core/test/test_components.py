# -*- coding: UTF-8 -*-
import sys
from unittest import mock

import pytest

from cherrymusic.core import components
from cherrymusic.core.components import Component, ComponentType


@pytest.fixture
def mock_registry():
    with mock.patch.object(components, '_registry', {}) as registry:
        yield registry


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
        class LocalComponentWithSameNamespace(Component):
            pkg_name = 'UNIMPORTABLE_MODULE'

    class ExtraLocalComponent(Component):
        namespace = 'OTHER_NAMESPACE'

    assert 'OTHER_NAMESPACE' in mock_registry
    assert set(components.iter_components()) == set(mock_registry.values())


# noinspection PyShadowingNames
def test_component_may_register_same_type_again(mock_registry):

    class LocalComponent(Component):
        pass

    component = mock_registry['core.test']

    # all of the following should be allowed:
    ComponentType.register(component)
    ComponentType.register(LocalComponent)
    ComponentType(LocalComponent.__name__, (Component,), {})  # same name, defined in same module


# noinspection PyUnusedLocal,PyShadowingNames
def test_components_collective_methods(mock_registry):

    class A(components.Component):
        namespace = 'A'
        method = mock.Mock()

    class B(components.Component):
        namespace = 'B'
        method = mock.Mock()

    components.Components().method(42, a=1)

    A.method.assert_called_once_with(42, a=1)
    B.method.assert_called_once_with(42, a=1)


# noinspection PyUnusedLocal,PyShadowingNames
def test_components_reset_order(mock_registry):

    calls = []

    class A(components.Component):
        namespace = 'A'

        def set_up(self):
            calls.append(f'{type(self).__name__}.set_up')

        def tear_down(self):
            calls.append(f'{type(self).__name__}.tear_down')

    class B(A):
        namespace = 'B'

    components.Components().reset()

    assert calls == ['B.tear_down', 'A.tear_down', 'A.set_up', 'B.set_up']
