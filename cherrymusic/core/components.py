# -*- coding: UTF-8 -*-

"""Standards for look and behavior of concrete, functional parts of the system"""
import logging
import operator
import sys
from importlib import import_module
from operator import attrgetter

from cherrymusic.common.types import ImmutableNamespace

log = logging.getLogger(__name__)


_registry = {}


def _fix_namespace(namespace):
    if namespace.startswith('cherrymusic.'):
        namespace = namespace[len('cherrymusic.'):]
    else:
        namespace = '_.' + namespace
    assert namespace and '.' not in {namespace[0], namespace[-1]}
    return namespace


def _unfix_namespace(namespace):
    if namespace[:2] == '_.':
        return namespace[2:]
    return 'cherrymusic.' + namespace


def iter_components():
    yield from _registry.values()


def get(namespace):
    namespace = _fix_namespace(namespace)
    try:
        return _registry[namespace]
    except KeyError:
        pkg_name = _unfix_namespace(namespace)
        module_name = pkg_name + '.components'
        try:
            import_module(module_name)  # this should register the component under namespace
            return _registry[namespace]
        except KeyError:  # pragma: no cover
            raise ImportError(f'{module_name} does not define a Component class') from None


get_component = get


class ComponentType(type):
    """Metaclass that instantiates and collects component classes as they are defined"""

    def __new__(mcs, name, bases, attrs):
        dependencies = tuple(attrs.pop('depends', ()))
        assert all(
            isinstance(d, ComponentType) or isinstance(d, tuple) and isinstance(d[0], ComponentType)
            for d in dependencies
        )
        attrs['depends'] = dependencies
        cls = super().__new__(mcs, name, bases, attrs)
        pkg = mcs.get_component_package(cls)
        # always make sure namespace and pkg_name are set on every class:
        cls.namespace = _fix_namespace(attrs.get('namespace') or pkg.__name__)
        if not attrs.get('pkg_name'):
            cls.pkg_name = pkg.__name__
        mcs.register(cls)
        return cls

    @classmethod
    def get_component_package(mcs, cls):
        """Get package for cls.pkg_name if given, or the package the cls was defined in

        Top-level modules are treated the same as packages.
        """
        pkg_name = cls.__dict__.get('pkg_name')
        if not pkg_name:
            assert sys.version_info >= (3, 6)
            module = sys.modules[cls.__module__]
            log.debug('Looking up package name from %r.__module__: %r', cls, module)
            if module.__package__ is None and module.__spec__ is None:  # pragma: no cover
                # https://docs.python.org/3/reference/import.html#main-spec
                assert module.__name__ == '__main__'
                pkg_name = '__main__'
            elif module.__package__ is None:  # pragma: no cover
                # https://docs.python.org/3/reference/import.html#__spec__
                pkg_name = module.__spec__.parent  # Python 3.6+
            elif module.__package__ in (module.__name__, ''):  # pragma: no cover
                # https://docs.python.org/3/reference/import.html#__package__
                return module  # module is a package or top-level module
            else:
                pkg_name = module.__package__
        else:
            log.debug('Using custom pkg_name from class %s: %r', cls, pkg_name)
        log.debug('Getting component package for pkg_name: %r', pkg_name)
        try:
            return sys.modules[pkg_name]
        except KeyError:
            return import_module(pkg_name)

    @classmethod
    def register(mcs, component):
        """Register the component under its namespace

        Args:
            component: An instance of a ComponentType class

        Raises:
            ValueError: if a different component is already registered under the same namespace

        """
        key = component.namespace
        if key in _registry:
            old = _registry[key]
            if str(old) == str(component):  # check str representation in case cls got reloaded
                log.debug(f'Allowing component re-registration: {component}')
            else:
                raise ValueError(f"Can't register {component} as {key!r}: already in use by {old}")
        _registry[key] = component
        log.debug('Registered component %s: %r', key, component)


class Component(ImmutableNamespace, metaclass=ComponentType):
    """Represents a code package that conforms to a certain API and gives it a private namespace

    The namespace can be used for isolation from other components, for instance in the filesystem or
    database space.
    """

    abstract: bool = True

    pkg_name: str = None
    """Importable name of the package described by the component (default set by metaclass)"""

    namespace: str = None
    """Namespace prefix used by the component (default set by metaclass)"""

    depends = ()
    """Sequence of Component subclasses whose instances this component will use"""

    def __init__(self, **dependencies):
        super().__init__(**dependencies)

    def __hash__(self):
        return hash(id(self))

    def __eq__(self, other):
        return self is other

    def set_up(self):  # pragma: no cover
        pass

    def tear_down(self):  # pragma: no cover
        pass

    def reset(self):  # pragma: no cover
        self.tear_down()
        self.set_up()


def init_components():
    comps = {}
    for comp_cls in iter_components():
        if comp_cls.__dict__.get('abstract'):  # ignore abstract attribute of superclasses
            continue
        deps = {}
        for dep_info in comp_cls.depends:
            dep_cls, *rest = dep_info
            if rest:
                dep_name, = rest  # unpack single rest
            else:
                dep_name = dep_cls.namespace.split('.')[-1]
            if dep_name in deps:
                raise ValueError(f'Dependency name conflict:'
                                 f' {dep_name} is {type(deps[dep_name])} and {dep_cls}')
            dep_instance = comps[dep_cls.namespace]
            deps[dep_name] = dep_instance
        comps[comp_cls.namespace] = comp_cls(**deps)
    return comps


class Components:

    def __init__(self):
        self._comps = init_components()

    def __iter__(self):
        yield from self._comps.values()

    def __getattr__(self, name):
        # Treat unknown attributes as component methods
        get_method = attrgetter(name)  # get method from individual components for dynamic dispatch

        def apply_to_all(*args, **kwargs):
            for component in self:
                method = get_method(component)
                log.info('%s: %s', component.namespace, getattr(method, '__name__', method))
                method(*args, **kwargs)

        setattr(self, name, apply_to_all)
        return apply_to_all

    def reset(self):
        """Tear-down these components in reverse order, then set them up again"""
        # noinspection PyTypeChecker
        components = tuple(self)

        def tear_down_in_reverse_even_during_exceptions(todo):
            if not todo:
                return
            current, *todo = todo
            try:
                tear_down_in_reverse_even_during_exceptions(todo)
            finally:
                current.tear_down()

        tear_down_in_reverse_even_during_exceptions(components)
        for components in components:
            components.set_up()
