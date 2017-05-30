import inspect

import re

DEFAULT_SERVICE_NAME = "<< default service name >>"

# Object to used as a marker of not initialized fields
UNINITIALIZED = object()

class InjectionError(AttributeError):
    pass


class InjectionNotFoundError(InjectionError):
    def __init__(self, attribute_name, service_name):
        super(AttributeError, self).__init__("Cannot inject attribute {} on service {} - the attribute cannot be found.".format(attribute_name, service_name))


class RecursiveInjectionError(InjectionError):
    def __init__(self, attribute_name):
        super(AttributeError, self).__init__("Cannot inject attribute {}. The object depends (directly or transitively) on itself".format(attribute_name))


class MultipleYieldsError(InjectionError):
    def __init__(self):
        super(AttributeError, self).__init__("Generator inject must yield exactly once.")


class Injector:
    def __init__(self):
        self.inject_table = {}

    def get(self, name, for_service=None):
        if name in self.inject_table:
            obj = self.inject_table[name].get_instance
            return obj

        raise InjectionNotFoundError(name, for_service)

    def all_injectors(self):
        return {key: factory.get_instance for key, factory in self.inject_table.items()}

    def injectors_in_modules(self, *modules):
        module_names = [m.__name__ for m in modules]

        return {key: factory.get_instance for key, factory in self.inject_table.items()
                if factory.raw_factory.__module__ in module_names}

    def _get_wrapper(self, factory_func, service_name, inplace, extra_args):
        if inspect.isclass(factory_func):
            return ClassInjectingWrapper(self, service_name, inplace, extra_args)
        elif inspect.isgeneratorfunction(factory_func):
            return GeneratorInjectingWrapper(self, service_name, inplace, extra_args)
        else:
            return FactoryInjectingWrapper(self, service_name, inplace, extra_args)

    def __call__(self, service_name=DEFAULT_SERVICE_NAME, inplace=False, **extra_args):
        factory_func = None
        if callable(service_name):
            factory_func = service_name
            service_name = DEFAULT_SERVICE_NAME

        def injection_in_progress(factory_func):
            wrapper = self._get_wrapper(factory_func, service_name, inplace, extra_args)
            return wrapper.wrap(factory_func)

        if factory_func:
            return injection_in_progress(factory_func)
        else:
            return injection_in_progress

    def finalize_all(self):
        factories = self.inject_table.values()
        for factory in factories:
            factory.finalize()


class InjectingWrapperBase:
    def __init__(self, inject, service_name=DEFAULT_SERVICE_NAME, inplace=False, extra_args=None):
        super().__init__()
        self.inplace = inplace
        self.extra_args = {} if extra_args is None else extra_args
        self.inject = inject
        self.service_name = service_name

    def _get_name(self, factory_func):
        """
        Helper method to derive the sevice name (i.e. the key under which the service will be accessible in the inject table)
        from the factory function / class / generator / ...
        The input name is derived from the factory's __name__ attribute. If it is in camel case, it is converted to words delimited by underscore.
        Finally the result is lowercased.
        For example: CamelCasedWord -> camel_cased_word
        :param service_name: If this argument is specified, a string representation of it is returned. There is a special default value DEFAULT_SERVICE_NAME
        :param factory_func: The callable whose name will be used to derive the result
        :return: String name of the service
        """
        if self.service_name is DEFAULT_SERVICE_NAME:
            s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', factory_func.__name__)
            return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        else:
            return str(self.service_name)

    def _get_dependencies(self, factory_func, name):
        signature = inspect.signature(factory_func)
        dependencies = []

        if hasattr(factory_func, "_instance_is_being_created"):
            raise RecursiveInjectionError(name)
        factory_func._instance_is_being_created = True

        for par in signature.parameters:
            dependency_factory = self.inject.get(par, name)
            dependency = dependency_factory()
            dependencies.append(dependency)

        del factory_func._instance_is_being_created
        return dependencies

    def wrap(self, factory_func):
        inject_name = self._get_name(factory_func)

        provider, finalizer = self._get_provider_and_finalizer(factory_func)

        result = provider if self.inplace else factory_func
        self.inject.inject_table[inject_name] = result

        result.raw_factory = factory_func
        result.get_instance = provider
        result.finalize = finalizer
        result.extra_args = self.extra_args

        return result

    def _get_provider_and_finalizer(self, factory_func):
        raise NotImplementedError("Must be implemented in subclasses")


class FactoryInjectingWrapper(InjectingWrapperBase):
    def _get_provider_and_finalizer(self, factory_func):

        def provider():
            if not provider._instance:
                dependencies = self._get_dependencies(factory_func, factory_func.__name__)
                provider._instance = factory_func(*dependencies)
                if hasattr(factory_func, "_finalize"):
                    provider._finalize = factory_func._finalize
            return provider._instance

        provider._instance = None

        def finalizer():
            if provider._instance is not None:
                if hasattr(provider, "_finalize"):
                    provider._finalize()
                provider._instance = None

        return provider, finalizer


class ClassInjectingWrapper(InjectingWrapperBase):
    @staticmethod
    def _get_delegates(clazz):
        return ((name, delegate) for name, delegate in clazz.__dict__.items() if isinstance(delegate, Injected))

    def _inject_delegates(self, clazz, instance, name):
        if hasattr(clazz, "_instance_is_being_created"):
            raise RecursiveInjectionError(name)
        clazz._instance_is_being_created = True

        for name, delegate in self._get_delegates(clazz):
            delegate.init(name, instance, self.inject.get(name, self.service_name))

        del clazz._instance_is_being_created

    def _reset_delegates(self, clazz, instance):
        for name, delegate in self._get_delegates(clazz):
            delegate.reset(instance)

    def _get_provider_and_finalizer(self, clazz):

        class Provider(clazz):
            def __new__(cls):
                if getattr(clazz, "_instance", None) is None:
                    dependencies = self._get_dependencies(clazz, self.service_name)
                    clazz._instance = clazz(*dependencies)
                    self._inject_delegates(clazz, clazz._instance, self.service_name)

                return clazz._instance

            def __init__(self):
                pass

        def finalizer():
            if getattr(clazz, "_instance", None) is not None:
                if hasattr(clazz._instance, "_finalize"):
                    clazz._instance._finalize()
                self._reset_delegates(clazz, clazz._instance)
                del clazz._instance

        return Provider, finalizer


class GeneratorInjectingWrapper(InjectingWrapperBase):
    def _get_provider_and_finalizer(self, generator):

        def provider():
            if not provider._instance:
                dependencies = self._get_dependencies(generator, generator.__name__)
                provider._generator = generator(*dependencies)
                provider._instance = next(provider._generator)
            return provider._instance

        provider._instance = None
        provider._generator = None

        def finalizer():
            if provider._instance is not None:
                if provider._generator is not None:
                    try:
                        next(provider._generator)  # This should raise StopIteration, otherwise the generator contains multiple yields, which is not allowed
                        raise MultipleYieldsError()
                    except StopIteration:
                        pass
                    provider._generator = None
                provider._instance = None

        return provider, finalizer


class Injected:
    FACTORY = ":factory"
    INSTANCE = ":instance"
    
    def __init__(self, lazy=False):
        self.name = None
        self.lazy = lazy
        self.__factory_key = None
        self.__instance_key = None

    def init(self, name, instance, factory):
        self.name = name

        if self.lazy:
            self.__factory_key = name + Injected.FACTORY
            instance.__dict__[self.__factory_key] = factory
        else:
            self.__instance_key = name + Injected.INSTANCE
            instance.__dict__[self.__instance_key] = factory()

    def reset(self, instance):
        instance.__dict__.pop(self.__factory_key, None)
        instance.__dict__.pop(self.__instance_key, None)

    def __get__(self, instance, owner):
        if self.lazy:
            return instance.__dict__[self.__factory_key]()
        else:
            return instance.__dict__[self.__instance_key]


inject = Injector()
