#!/usr/bin/python
import os
import sys
from easyrunner import PythonUnittestRunner


class ExampleTestRunner(PythonUnittestRunner):

    def __init__(self):
        super(ExampleTestRunner, self).__init__()
        search_path = os.path.join(
            os.path.split(os.path.realpath(__file__))[0],
            'example_tests'
        )
        self.set_command_path(search_path)

    def update_log(self, target_file, output):
        last_line = output.strip().splitlines()[-1].strip()
        if last_line == "OK":
            self.log_pass()
        else:
            self.log_failure(target_file)


if __name__ == "__main__":
    runner = ExampleTestRunner()
    runner.set_cli_args(sys.argv)
    runner.run()

