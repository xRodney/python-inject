import pytest


def injects_to_pytest_fixtures(inject, scope, only_modules=None):
    for key, factory in inject.inject_table.items():
        def get_get_instance(key, factory):
            def get_instance(request):
                request.addfinalizer(factory.finalize)
                return factory.get_instance()

            return get_instance

        pytest_scope = factory.extra_args.get("pytest_scope", "session")
        scope[key] = pytest.fixture(scope=pytest_scope)(get_get_instance(key, factory))
