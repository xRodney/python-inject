from test.my_test_package.inject import my_test_package_inject
import test.my_test_package


def test_all_injectors():
    all = my_test_package_inject.all_injectors()
    assert "hello" in all
    assert "goodbye" in all


def test_injectors_in_all_modules():
    all = my_test_package_inject.injectors_in_modules(test.my_test_package.module1, test.my_test_package.module2)
    assert "hello" in all
    assert "goodbye" in all


def test_injectors_in_module():
    mod1 = my_test_package_inject.injectors_in_modules(test.my_test_package.module1)
    assert "hello" in mod1
    assert "goodbye" not in mod1

    mod2 = my_test_package_inject.injectors_in_modules(test.my_test_package.module2)
    assert "hello" not in mod2
    assert "goodbye" in mod2
