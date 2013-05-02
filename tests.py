import os
import easyrunner
import unittest
from mock import patch


def mock_os_walk(path):
    paths = [
        ('.', [], ['fakeTest', 'fakeTest2'])
    ]
    return (p for p in paths)

def mock_input(prompt_msg):
    return 'y'

def return_true(*args):
    return True

class EasyRunnerTests(unittest.TestCase):
    def setUp(self):
        pass

    @patch('easyrunner.os.path.isfile', return_true)
    @patch('easyrunner.os.walk', mock_os_walk)
    @patch('builtins.raw_input', mock_input)
    def test_behat_runner(self):
        runner = easyrunner.EasyRunner()
        # mock_os.walk = self.mock_os_walk

        runner.add_required_regex(r'fakeTest')
        runner.add_search_path('.')
        runner.set_cli_args('fakeTest')
        runner.run()

if __name__ == '__main__':
    unittest.main()
