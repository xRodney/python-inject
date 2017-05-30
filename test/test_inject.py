import inspect

import pytest

from inject.inject import RecursiveInjectionError, InjectionNotFoundError, Injector, MultipleYieldsError, Injected

tracker = {"hello_factory": 0}


def hello_factory():
    tracker['hello_factory'] += 1
    return "hello"


def test_factory_function_is_called_at_most_once():
    inject = Injector()

    hello = inject(hello_factory)
    assert tracker['hello_factory'] == 0
    assert hello.get_instance() == "hello"
    assert hello.get_instance() == "hello"
    assert tracker['hello_factory'] == 1


def test_injection_in_factory_method():
    tracker['greeter_factory'] = 0
    tracker['hello_factory'] = 0

    inject = Injector()
    inject("hello")(hello_factory)

    @inject("greeter")
    def greeter_factory(hello):
        tracker['greeter_factory'] += 1

        class Greeter:
            @staticmethod
            def greet(name):
                return hello + " " + name

        return Greeter()

    assert greeter_factory.get_instance().greet("Dusan") == "hello Dusan"
    assert tracker['hello_factory'] == 1


def test_injection_in_constructor():
    tracker['greeter_factory'] = 0
    tracker['hello_factory'] = 0

    inject = Injector()
    inject("hello")(hello_factory)

    @inject("greeter_object")
    class GreeterClass:
        def __init__(self, hello):
            self.hello = hello

        def greet(self, name):
            return self.hello + " " + name

    assert GreeterClass.get_instance().greet("Dusan") == "hello Dusan"
    assert tracker['hello_factory'] == 1


def test_transitive_dependency():
    tracker['hello_factory'] = 0

    inject = Injector()
    inject("hello")(hello_factory)

    @inject("greeter")
    class GreeterClass:
        def __init__(self, hello):
            self.hello = hello

        def greet(self, name):
            return self.hello + " " + name

    @inject
    class Logger:
        def __init__(self, greeter):
            self.greeter = greeter

        def log_greet(self, name):
            return "Greeter says: " + self.greeter.greet(name)

    assert Logger.get_instance().log_greet("Dusan") == "Greeter says: hello Dusan"
    assert tracker['hello_factory'] == 1


def test_dependency_graph_is_not_a_tree():
    tracker['hello_factory'] = 0

    inject = Injector()
    inject("hello")(hello_factory)

    @inject("greeter")
    class GreeterClass:
        def __init__(self, hello):
            self.hello = hello

        def greet(self, name):
            return self.hello + " " + name

    @inject
    class LoggerWithVerification:
        def __init__(self, greeter, hello):
            self.hello = hello
            self.greeter = greeter

        def log_greet(self, name):
            return "Greeter says: {}, hello is {}".format(self.greeter.greet(name), self.hello)

    assert LoggerWithVerification.get_instance().log_greet("Dusan") == "Greeter says: hello Dusan, hello is hello"
    assert tracker['hello_factory'] == 1


def test_out_of_order_definition():
    inject = Injector()

    def something1_factory():
        return "You say yes,\n"

    def something2_factory(something1):
        return something1 + "I say no"

    something2 = inject("something2")(something2_factory)  # out of order definition
    something1 = inject("something1")(something1_factory)

    assert something2.get_instance() == "You say yes,\nI say no"


def test_factory_depends_on_itself_directly():
    inject = Injector()

    @inject
    def cyclic(cyclic):
        pass

    with pytest.raises(RecursiveInjectionError) as error:
        cyclic.get_instance()


def test_factory_depends_on_itself_transitively():
    inject = Injector()

    @inject
    def cyclic1(cyclic2):
        pass

    @inject
    def cyclic2(cyclic1):
        pass

    with pytest.raises(RecursiveInjectionError) as error:
        cyclic1.get_instance()


def test_class_depends_on_itself_transitively():
    inject = Injector()

    @inject
    class Cyclic1:
        def __init__(self, cyclic2):
            pass

    @inject
    class Cyclic2:
        def __init__(self, cyclic1):
            pass

    with pytest.raises(RecursiveInjectionError) as error:
        Cyclic1.get_instance()


def test_generator_depends_on_itself_transitively():
    inject = Injector()

    @inject
    def cyclic1(cyclic2):
        yield 1

    @inject
    def cyclic2(cyclic1):
        yield 1

    with pytest.raises(RecursiveInjectionError) as error:
        cyclic1.get_instance()


def test_unfilled_dependency():
    inject = Injector()

    @inject
    def unfilled_dependency_factory(non_existing_object):
        pass

    with pytest.raises(InjectionNotFoundError) as error:
        unfilled_dependency_factory.get_instance()


def test_all_injectors():
    inject = Injector()

    @inject
    def aaa():
        pass

    @inject
    def bbb():
        pass

    assert "aaa" in inject.all_injectors()
    assert "bbb" in inject.all_injectors()
    assert "xxx" not in inject.all_injectors()


def test_finalize():
    inject = Injector()

    @inject
    class X:
        instance_closed = False
        instance_created = 0

        def __init__(self):
            X.instance_created += 1

        def _finalize(self):
            X.instance_closed = True

    # Instance is closed only if object is initialized
    X.finalize()
    assert X.instance_closed is False

    # After the instance is initialized, the close_instance is called
    X.get_instance()
    X.get_instance()
    assert X.instance_closed is False
    assert X.instance_created == 1

    X.finalize()
    # after finalized, a new instance is created
    X.get_instance()
    assert X.instance_closed is True
    assert X.instance_created == 2


def test_finalize_all_instances():
    inject = Injector()

    @inject
    class X:
        instance_closed = False

        def _finalize(self):
            X.instance_closed = True

    # Instance is closed only if object is initialized
    inject.finalize_all()
    assert X.instance_closed is False

    # After the instance is initialized, the close_instance is called
    X.get_instance()
    assert X.instance_closed is False
    inject.finalize_all()
    assert X.instance_closed is True


def test_finalize_function():
    inject = Injector()

    @inject
    def x():
        def _finalize():
            x.finalized = True
        x._finalize = _finalize
        return "x"
    x.finalized = False

    # Instance is closed only if object is initialized
    inject.finalize_all()
    assert x.finalized is False

    # After the instance is initialized, the close_instance is called
    x.get_instance()
    assert x.finalized is False
    inject.finalize_all()
    assert x.finalized is True


def test_finalize_generator():
    inject = Injector()

    @inject
    def x():
        x.initiliazed += 1
        yield "x"
        x.finalized += 1
    x.initiliazed = 0
    x.finalized = 0

    # Instance is closed only if object is initialized
    inject.finalize_all()
    assert x.finalized == 0

    x.get_instance()
    assert x.initiliazed == 1
    assert x.finalized == 0
    x.finalize()
    assert x.finalized == 1


def test_finalize_all_with_generator():
    inject = Injector()

    @inject
    def x():
        x.initiliazed += 1
        yield "x"
        x.finalized += 1
    x.initiliazed = 0
    x.finalized = 0

    # Instance is closed only if object is initialized
    inject.finalize_all()
    assert x.finalized == 0

    x.get_instance()
    assert x.initiliazed == 1
    assert x.finalized == 0
    inject.finalize_all()
    assert x.finalized == 1


def test_generator_multiple_yields():
    inject = Injector()

    @inject
    def x():
        x.initiliazed += 1
        yield "x"
        x.finalized += 1
        yield "y"
    x.initiliazed = 0
    x.finalized = 0

    # After the instance is initialized, the close_instance is called
    x.get_instance()
    with pytest.raises(MultipleYieldsError):
        x.finalize()

def test_decorated_class_is_still_class():
    inject = Injector()

    @inject
    class X:
        def __init__(self):
            pass

    @inject
    class Y:
        def __init__(self, x):
            pass

    assert inspect.isclass(X)
    assert inspect.isclass(Y)


def test_decorated_class_scope():
    inject = Injector()

    @inject
    class X:
        instances = 0
        def __init__(self):
            X.instances += 1

    assert inspect.isclass(X)
    X.get_instance()
    X.get_instance()
    assert X.instances == 1
    X()
    assert X.instances == 2


def test_decorated_class_inplace():
    inject = Injector()

    @inject(inplace=True)
    class X:
        instances = 0
        def __init__(self):
            X.instances += 1

    assert inspect.isclass(X)
    X.get_instance()
    X.get_instance()
    assert X.instances == 1
    X()
    assert X.instances == 1


def test_decorated_factory_scope():
    inject = Injector()

    @inject
    def x():
        x.instances += 1
        return "x"
    x.instances = 0

    assert inspect.isfunction(x)
    x.get_instance()
    x.get_instance()
    assert x.instances == 1
    x()
    assert x.instances == 2


def test_decorated_factory_inplace():
    inject = Injector()

    @inject(inplace=True)
    def x():
        x.instances += 1
        return "x"
    x.instances = 0

    assert inspect.isfunction(x)
    x.get_instance()
    x.get_instance()
    assert x.instances == 1
    x()
    assert x.instances == 1


def test_decorated_generator_scope():
    inject = Injector()

    @inject
    def x():
        x.initiliazed += 1
        yield "x"
        x.finalized += 1
    x.initiliazed = 0
    x.finalized = 0

    assert inspect.isfunction(x)
    assert x.get_instance() == "x"
    assert x.get_instance() == "x"
    assert x.initiliazed == 1
    xx = x()
    assert x.initiliazed == 1
    next(xx)
    assert x.initiliazed == 2


def test_decorated_generator_inplace():
    inject = Injector()

    @inject(inplace=True)
    def x():
        x.initiliazed += 1
        yield "x"
        x.finalized += 1
    x.initiliazed = 0
    x.finalized = 0

    assert inspect.isfunction(x)
    assert x.get_instance() == "x"
    assert x.get_instance() == "x"
    assert x.initiliazed == 1
    xx = x()
    assert x.initiliazed == 1
    # x is no longer a generator, so next(xx) raises error
    with pytest.raises(TypeError):
        next(xx)
        assert x.initiliazed == 1


def test_lazy_object():
    inject = Injector()

    @inject
    def x():
        x.initiliazed += 1
        yield "x"
        x.finalized += 1
    x.initiliazed = 0
    x.finalized = 0

    @inject
    class MyLazyObject:
        initiliazed = 0
        finalized = 0

        def __init__(self, x):
            super().__init__()
            MyLazyObject.initiliazed += 1

        def _finalize(self):
            MyLazyObject.finalized += 1

        def return_something(self):
            return 13


    @inject
    class MyNeverUsedLazyObject:
        initiliazed = 0
        finalized = 0

        def __init__(self, x):
            super().__init__()
            MyNeverUsedLazyObject.initiliazed += 1

        def _finalize(self):
            MyNeverUsedLazyObject.finalized += 1

        def return_something(self):
            return 0


    @inject
    class MyEagerObject:
        initiliazed = 0
        finalized = 0

        def __init__(self):
            super().__init__()
            MyEagerObject.initiliazed += 1

        def _finalize(self):
            MyEagerObject.finalized += 1

        def return_something(self):
            return 29


    @inject
    class MyObject:
        my_lazy_object = Injected(lazy=True)
        my_never_used_lazy_object = Injected(lazy=True)
        my_eager_object = Injected(lazy=False)

        def do_work(self):
            return self.my_lazy_object.return_something() + self.my_eager_object.return_something()

    assert MyObject.get_instance() is not None

    assert x.initiliazed == 0
    assert x.finalized == 0
    assert MyLazyObject.initiliazed == 0
    assert MyLazyObject.finalized == 0
    assert MyNeverUsedLazyObject.initiliazed == 0
    assert MyNeverUsedLazyObject.finalized == 0
    assert MyEagerObject.initiliazed == 1
    assert MyEagerObject.finalized == 0

    assert MyObject.get_instance().do_work() == 42

    assert x.initiliazed == 1
    assert x.finalized == 0
    assert MyLazyObject.initiliazed == 1
    assert MyLazyObject.finalized == 0
    assert MyNeverUsedLazyObject.initiliazed == 0
    assert MyNeverUsedLazyObject.finalized == 0
    assert MyEagerObject.initiliazed == 1
    assert MyEagerObject.finalized == 0

    inject.finalize_all()

    assert x.initiliazed == 1
    assert x.finalized == 1
    assert MyLazyObject.initiliazed == 1
    assert MyLazyObject.finalized == 1
    assert MyNeverUsedLazyObject.initiliazed == 0
    assert MyNeverUsedLazyObject.finalized == 0
    assert MyEagerObject.initiliazed == 1
    assert MyEagerObject.finalized == 1


def test_repeated_init():
    inject = Injector()

    @inject
    def x():
        x.initiliazed += 1
        yield "x" + str(x.initiliazed)
        x.finalized += 1
    x.initiliazed = 0
    x.finalized = 0

    @inject
    class MyObject:
        x = Injected(lazy=True)

        initiliazed = 0
        finalized = 0

        def __init__(self):
            super().__init__()
            MyObject.initiliazed += 1

        def _finalize(self):
            MyObject.finalized += 1

        def do_work(self):
            return self.x

    assert MyObject.get_instance() is not None

    assert x.initiliazed == 0
    assert x.finalized == 0

    assert MyObject.get_instance().do_work() == "x1"

    assert x.initiliazed == 1
    assert x.finalized == 0

    assert MyObject.get_instance().do_work() == "x1"

    assert x.initiliazed == 1
    assert x.finalized == 0

    # X is finalized, but MyObject still depends on it, it should get a new instance next time it is required
    x.finalize()

    assert x.initiliazed == 1
    assert x.finalized == 1

    assert MyObject.get_instance().do_work() == "x2"

    assert x.initiliazed == 2
    assert x.finalized == 1














