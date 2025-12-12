import os
import sys
import unittest

if __name__ == "__main__":

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    loader = unittest.TestLoader()
    start_dir = "tests"
    suite = loader.discover(start_dir)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    sys.exit(0 if result.wasSuccessful() else 1)
