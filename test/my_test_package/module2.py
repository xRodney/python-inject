from test.my_test_package.inject import my_test_package_inject

@my_test_package_inject
def goodbye():
    return "Goodbye from module2"