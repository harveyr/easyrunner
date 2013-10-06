import easyrunner
import unittest
from mock import patch
from nose import tools as nt


def mock_os_walk(path):
    for fake_structure in [
        ('fakedir', [], [
            'some_great_test.py',
            'some_feature_test.py',
            'another_feature_test.py'
        ]),
        ('elsewhere', [], [
            'truly_terrible_test.py',
            'one_more_feature_test.py'
        ])
    ]:
        yield fake_structure


def return_true(*args):
    return True


class EasyRunnerTests(unittest.TestCase):
    def setUp(self):
        pass

    def test_progress_str(self):
        runner = easyrunner.EasyRunner()
        nt.assert_equal(
            runner.progress_str(1, 100),
            '[->                                                                         ]'
        )
        nt.assert_equal(
            runner.progress_str(50, 100),
            '[------------------------------------->                                     ]'
        )

    @patch('os.path.exists', return_true)
    @patch('os.walk', mock_os_walk)
    def test_find_target_files(self):
        runner = easyrunner.EasyRunner()
        runner.add_required_pattern(r'.py$')
        runner.add_optional_pattern(r'feature')
        runner.add_search_path('arbitrary')

        expected_targets = [
            'fakedir/some_feature_test.py',
            'fakedir/another_feature_test.py',
            'elsewhere/one_more_feature_test.py'
        ]

        nt.assert_equal(
            expected_targets,
            runner.find_target_files()
        )

