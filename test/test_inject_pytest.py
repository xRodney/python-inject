from inject.inject import Injector
from inject.inject_pytest import injects_to_pytest_fixtures

inject = Injector()


@inject
def hello2():
    return "hello"


@inject(pytest_scope="function")
class Finalized():
    initialized = 0
    finalized = 0

    def __init__(self, hello2):
        Finalized.initialized += 1

    def _finalize(self):
        Finalized.finalized += 1


injects_to_pytest_fixtures(inject, vars())


def test_cooperation_with_pytest(hello2):
    assert hello2 == "hello"


def test_finalizer(finalized):
    assert Finalized.initialized == 1
    assert Finalized.finalized == 0


# Note: This test must be run after the previous test
def test_finalizer_continued(finalized):
    assert Finalized.initialized == 2
    assert Finalized.finalized == 1
