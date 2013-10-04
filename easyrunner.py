import os
import sys
import datetime
import subprocess as sub
import re
import pickle
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
LOGHANDLER = logging.StreamHandler()
LOGFORMATTER = logging.Formatter('[%(name)s:%(lineno)d] - %(levelname)s - %(message)s')
LOGHANDLER.setFormatter(LOGFORMATTER)
LOGHANDLER.setLevel(logging.DEBUG)
logger.addHandler(LOGHANDLER)


class EasyRunner(object):
    """
    Abstract parent class. This must be subclassed for each type of test
    in order to provide the specifics such pass/fail regexes and witty titles.
    """

    title = 'EasyRunner'
    command = None
    command_preps = set()
    command_path = None
    command_prefixes = set()
    command_suffixes = set()
    search_paths = set()
    file_optional_res = set()
    file_required_res = set()
    target_files = []
    use_all_files = False
    start_time = None

    cli_args = None
    config_parts = []

    verbose = False

    pass_count_re = None
    fail_count_re = None
    test_log = {
        'files': {},
        'passes': 0,
        'failures': 0,
        'failed_tests': []
    }

    clr = {
        'HEADER': '\033[95m',
        'BLUE': '\033[94m',
        'GREEN': '\033[92m',
        'WARN': '\033[93m',
        'FAIL': '\033[91m',
        'ENDC': '\033[0m'
    }

    def __init__(self):
        self.set_command_path(os.getcwd())

    def set_cli_args(self, args):
        """Accepts the command line arguments for the current invocation."""
        # Not sure why I don't just grab them in __init__(). Maybe I had a
        # reason? Maybe they shouldn't be processed until whatever is
        # instantiating the runner does some setup work.
        # Revisit this.
        self.cli_args = args
        self.process_cli_args()

    def set_title(self, title):
        """
        Sets the title. This has no impact on anything but the header that's
        printed on execution. This allows each subclass to distinguish
        itself.
        """
        self.title = title

    def set_command(self, command):
        """
        Sets the command that runs the tests. python, nosetests, bin/behat,
        whatever.
        """
        self.command = command

    def set_command_path(self, path):
        """
        Sets the path from which the test-runner command should be executed.
        """
        if os.path.isdir(path):
            self.command_path = path
        else:
            print(self._bad("Bad command path provided: {}".format(path)))

    def add_search_path(self, path):
        """Adds a path where to go for a test searchin'."""
        if path[0] == '~':
            path = os.path.expanduser(path)
        if os.path.exists(path):
            self.search_paths.add(path)

    def add_optional_regex(self, regex):
        """
        Adds an *optional* regular expression. A test file must match at least
        one of these to be included.
        """
        self.file_optional_res.add(re.compile(regex, re.I))

    def add_required_regex(self, regex):
        """
        Adds a *required* regular expression. If a test file does not match this,
        it is excluded.
        """
        self.file_required_res.add(re.compile(regex, re.I))

    def add_prefix(self, prefix):
        """
        Adds a command option/prefix. This will be included in the shell command
        string after the command itself, but before the test file path.
        """
        self.command_prefixes.add(prefix)

    def add_suffix(self, suffix):
        """
        Adds a command suffix. This will be appended to the command shell
        command after the test file path.
        """
        self.command_suffixes.add(suffix)

    def set_verbose(self, verbose):
        """Sets verbosity mode."""
        self.verbose = bool(verbose)

    def time_passed(self):
        """Returns how much time has passed since the tests began."""
        diff = datetime.datetime.now() - self.start_time
        return str(diff).split('.')[0]

    def log_failure(self, target):
        """Log that a test has failed."""

        # Obviously we don't need the separate count field if it's always going
        # to match the number of test files that have failed. However, I
        # think the plan was to let them diverge under certain circumstances.
        # Need to revisit this.
        self.test_log['failures'] += 1

        # A set would be cleaner here, but I like keeping the failures
        # in order. It makes the progressive tally more readable.
        if target not in self.test_log['failed_tests']:
            self.test_log['failed_tests'].append(target)

    def log_pass(self):
        """
        Log that a test has passed. This is all we save for now, since we
        want additional details only for tests that failed.
        """
        self.test_log['passes'] += 1

    def strip_ansi(self, text):
        """Remove ansi codes from text (such as text from the console)."""
        return re.sub(r'\033\[[0-9;]+m|\[2K', '', text)

    def run(self):
        """Starts the tests a runnin'."""
        self.print_title()

        # If no search string, try to resume state from the prior run
        if len(self.cli_args) == 1:
            self.resume_state()
        else:
            self.validate()
            self.find_target_files()

            if len(self.target_files) == 0:
                print(self._bad('No matches found.'))
                self._quit()

            self.print_test_scope()
            self.prompt_user()

    def print_title(self):
        """
        Wipes the /usr directory.

        Just kidding. Prints the title.
        """
        print(self._header('\n----- ' + self.title + ' -----\n'))

    def print_test_scope(self):
        """Prints the target files and related parameters (verbosity, etc.)"""
        print(self._status('Target Files:'))
        count = 1
        for f in self.target_files:
            number_prefix = "[{0}]".format(count)
            parts = os.path.split(self.get_path_rel_to_command_path(f))
            print("\t{0}: {1}".format(
                number_prefix,
                (parts[0] + '/' + self._warn(parts[1]))
            ))
            count += 1

        if self.verbose:
            if 'silent' not in self.config_parts:
                self.config_parts.append('silent')
            try:
                self.config_parts.remove('verbose')
            except ValueError:
                pass
        else:
            if 'verbose' not in self.config_parts:
                self.config_parts.append('verbose')
            try:
                self.config_parts.remove('silent')
            except ValueError:
                pass

        colored_config_parts = [self._good(cp) for cp in self.config_parts]
        config_str = '[ ' + ' | '.join(colored_config_parts) + ' ]'
        print('{0}'.format(config_str))

    def print_commands(self):
        """Print available command-prompt commands."""
        command_sets = [
            ('Enter', 'Run the listed test files'),
            ('#, #, #-#', 'Limit to specified file numbers'),
            ('v', 'Toggle verbosity'),
            ('q | ^C', 'Quit')
        ]

        max_command_len = 0
        for command_set in command_sets:
            if len(command_set[0]) > max_command_len:
                max_command_len = len(command_set[0])

        max_command_len += 5
        for command_set in command_sets:
            command_ = command_set[0]
            c_len = len(command_)
            print('{0}{1}{2}'.format(
                command_,
                ' '.join('' for i in range(max_command_len - c_len)),
                command_set[1]
            ))

    def prompt_user(self):
        """Prompts the user and deals with the response."""
        try:
            print
            c = raw_input(self._status('Command [? for options]: '))
        except:
            self._quit()
        c = c.lower()
        if c == '?':
            self.print_test_scope()
            self.print_commands()
            self.prompt_user()
            return
        elif c == 'v':
            self.verbose = not self.verbose
            print
            self.print_test_scope()
            self.prompt_user()
            return
        elif c == 'n' or c == 'q':
            self._quit()

        numbers = set()
        parts = [part.strip() for part in c.split(',')]

        for part in parts:
            if '-' in part:
                span_parts = part.split('-')
                start = int(span_parts[0])
                end = int(span_parts[1])
                for i in range(start, end + 1):
                    numbers.add(i)
                continue
            try:
                # Handle number input
                num = int(part)
                if num < 1 or num > len(self.target_files):
                    print(self._bad((
                        'That number is not in the list! Try again.\n')))
                    return self.prompt_user()
                    numbers.add(num)
            except ValueError:
                pass

        if len(numbers) > 0:
            self.target_files = [self.target_files[i-1] for i in numbers]
            self.print_test_scope()
            self.prompt_user()
            return

        self.save_state()
        self.run_tests()

    def prompt_resume_state(self):
        """Prompts the user to resume prior state."""
        try:
            print
            c = raw_input(
                self._status("Hit anything but 'q' to re-run last batch: ")
            )
        except:
            self._quit()
        c = c.lower()
        if c == 'q' or c == 'n':
            self._quit()
        self.run_tests()

    def get_state_save_path(self):
        """Gets the path at which to save the pickled state."""
        filename = '.{0}_state'.format(
            ('_'.join(self.title.split(' '))).lower())
        script_path = '/'.join(os.path.realpath(__file__).split('/')[:-1])
        return os.path.join(script_path, filename)

    def load_state(self):
        """Tries to fetch the pickled state from the save file."""
        try:
            with open(self.get_state_save_path()) as f:
                return pickle.load(f)
        except IOError:
            return False

    def save_state(self):
        """Saves the runner's state."""
        state = {
            'files': self.target_files,
            'verbose': self.verbose
        }
        child_state = self.get_state()
        for key in child_state:
            state[key] = child_state[key]
        pickle.dump(state, file(self.get_state_save_path(), "w"))

    def get_state(self):
        """
        Override me and return a dict of stuff to save in the pickled state.
        """
        return {}

    def apply_state(self, state_obj):
        """
        Override me to rehydrate the pickled state dict.
        """
        pass

    def run_tests(self):
        """Run all target test files."""
        if self.command_path:
            os.chdir(self.command_path)

        self.start_time = datetime.datetime.now()
        for t in self.target_files:
            self.run_command(t)
        self.finish()

    def run_command(self, target_file):
        """Runs the shell command to execute the target file."""
        cmd = self.build_command(target_file)

        print('\n' + self._warn("[RUNNING]" +
              self.get_path_rel_to_command_path(target_file)))

        try:
            p = sub.Popen(cmd, stdout=sub.PIPE, stderr=sub.PIPE, shell=True)
            output = ''
            if self.verbose is True:
                for line in iter(p.stdout.readline, ""):
                    output += line
                    print(line.rstrip())
            else:
                out, err = p.communicate()
                output = err + out

            self.handle_output(target_file, output)

        except KeyboardInterrupt:
            if p:
                print(self._warn('\nABORTING...'))
                print('Terminating current process...')
                p.terminate()
                print('... done.')
                self._quit()

    def build_command(self, target_file):
        """Builds the command string to run the test file."""
        prefixes = ' '.join(self.command_prefixes)
        suffixes = ' '.join(self.command_suffixes)
        return '{0} {1}'.format(
            self.command,
            ' '.join([prefixes, target_file, suffixes]))

    def handle_output(self, target_file, output):
        """Handles test output."""
        self.test_log['files'][target_file] = output
        self.update_log(target_file, output)
        self.print_tally()

    def update_log(self, target_file, output):
        """Override me to update the test log."""
        pass

    def format_progress_str(self, progress, total):
        """Formats a basic, text progress bar for printing."""
        length = 76
        dashes = int(float(progress) / float(total) * length)

        buffer = '['
        for i in range(dashes - 1):
            buffer += '-'
        buffer += '>'
        for i in range(length - dashes):
            buffer += ' '
        buffer += ']'
        return buffer

    def print_tally(self):
        """Prints tally of failed tests, time passed, tests left, etc."""
        pass_str = self._good('{0} passed'.format(self.test_log['passes']))
        fail_str = self._bad('{0} failed'.format(self.test_log['failures']))

        tests_run_count = len(self.test_log['files'])
        total_count = len(self.target_files)

        f_count_str = self._status('{0}/{1} tests run'.format(
            tests_run_count,
            total_count))

        print('\n{0}: {1} | {2}  [{3}] [{4}]'.format(
            self._header('Test File Tally'),
            pass_str,
            fail_str,
            self._status(self.time_passed()),
            f_count_str)
        )

        if total_count > 1:
            print(self.format_progress_str(tests_run_count, total_count))

        if len(self.test_log['failed_tests']) > 0:
            print(self._warn('Failures:\n{0}'.format(
                '\n'.join(self.test_log['failed_tests'])))
            )

    def print_search_parameters(self):
        """Prints summary of test file search params."""
        if len(self.file_required_res) + len(self.file_optional_res) == 0:
            print(self._bad('No search patterns provided.'))
            self._quit()

        print(self._status('Search Parameters'))
        if len(self.file_required_res) > 0:
            pats = [self._warn(r.pattern) for r in self.file_required_res]
            s = '\tFile must match {0} of these patterns: '.format(
                self._warn('all'))
            s += ' | '.join(pats)
            print(s)
        if len(self.file_optional_res) > 0:
            pats = [self._status(r.pattern) for r in self.file_optional_res]
            s = '\tFile must match {0} of these patterns: '.format(
                self._status('any'))
            s += ' | '.join(pats)
            print(s)

    def find_target_files(self):
        """Find target test files and populate the list."""
        self.print_search_parameters()
        print(self._status('Searching...'))
        total_file_count = 0

        if len(self.search_paths) == 0:
            self.search_paths.add(self.command_path)

        for path in self.search_paths:
            for root, subFolders, files in os.walk(path):
                count = 0
                for f in files:
                    total_file_count += 1
                    file_path = os.path.join(root, f)
                    if self.evaluate_candidate_file(file_path):
                        self.target_files.append(file_path)
                        count += 1

                root_path_str = '\t' + root
                if count == 0:
                    print(root_path_str)
                else:
                    print(self._status(root_path_str + ' [{0}]'.format(count)))

    def evaluate_candidate_file(self, file_path):
        """Returns True if test file matches filter params."""
        # Check if it fails any of the required patterns
        for r in self.file_required_res:
            if not r.search(file_path):
                return False

        # If all required patterns match and the --all flag has been passed,
        # return True
        if self.use_all_files:
            return True

        if len(self.file_optional_res) == 0:
            return True

        # Make sure it matches at least one optional pattern.
        # (And handle the case when only required patterns are
        # provided.)
        for r in self.file_optional_res:
            if r.search(file_path) is not None:
                return True

        return False

    def validate(self):
        """Makes sure necessary paths exist."""
        paths = self.search_paths.copy()
        paths.add(self.command_path)
        for p in paths:
            if not os.path.isdir(p):
                print(self._bad('Bad path: ' + p))
                self._quit()

    def process_cli_args(self):
        """Processes each command-line argument."""
        for a in self.cli_args[1:]:
            self._process_cli_arg(a)

    def _process_cli_arg(self, arg):
        """Processes a particular command line argument."""

        # TODO: Do we need all this?
        idx = self.cli_args.index(arg)
        if arg == '-sp':
            self.add_search_path(self.cli_args[idx + 1])
        elif arg == '-cp':
            self.set_command_path(self.cli_args[idx + 1])
        elif arg == '-op':
            self.add_optional_regex(self.cli_args[idx + 1])
        elif arg == '--all':
            self.use_all_files = True
            self.config_parts.append(arg)
        elif arg == '-v' or arg == '--verbose':
            self.set_verbose(True)
        else:
            self.add_required_regex(self.cli_args[idx])

    def resume_state(self):
        """Tries to resume state from last execution of the test runnner."""
        state_obj = self.load_state()
        if not state_obj:
            print('No arguments. Need to add a usage statement!')
            self._quit()
        self.target_files = state_obj.get('files')
        self.verbose = state_obj.get('verbose')
        if hasattr(self, 'apply_state'):
            self.apply_state(state_obj)
        self.print_test_scope()
        self.prompt_resume_state()

    def print_log(self):
        """Prints the test tally."""
        if len(self.test_log) == 0:
            print(self._warn('\nNO RESULTS'))
            return

        print(self._header('\nRESULTS'))
        for tf in self.target_files:
            if not tf in self.test_log['files']:
                continue

            print(self._status(tf))
            print(' - ' + ' | '.join(self.test_log['files'][tf]))

    def finish(self):
        """Override me to do cleanup / final log output / whatever."""
        pass

    def get_path_rel_to_command_path(self, file_path):
        """
        Returns path relative to the command path. This is helpful for printing
        results, where the user does not need to see the whole thing.
        """
        if self.command_path in file_path:
            return file_path.split(self.command_path)[1][1:]
        return file_path

    def _status(self, text):
        return self.clr.get('BLUE') + text + self.clr.get('ENDC')

    def _good(self, text):
        return self.clr.get('GREEN') + text + self.clr.get('ENDC')

    def _bad(self, text):
        return self.clr.get('FAIL') + text + self.clr.get('ENDC')

    def _warn(self, text):
        return self.clr.get('WARN') + text + self.clr.get('ENDC')

    def _header(self, text):
        return self.clr.get('HEADER') + text + self.clr.get('ENDC')

    def _quit(self):
        """Peace out."""
        print('\nFare thee well.')
        sys.exit()


class PythonUnittestRunner(EasyRunner):
    def __init__(self):
        self.set_title('Unittest Runner')
        self.set_command('python')
        self.add_required_regex(r'.*py$')


class PythonNoseRunner(EasyRunner):
    def __init__(self):
        self.set_title('Runny Nose')
        self.set_command('nosetests')
        self.add_required_regex(r'.*py$')


class BehatRunner(EasyRunner):
    features = []
    config_file = None
    outcome_re = None

    tags = set()

    def __init__(self):
        super(BehatRunner, self).__init__()
        self.set_title('Behat Runner')
        self.set_command('bin/behat')
        self.add_suffix('--ansi')
        self.outcome_re = re.compile(r'\d+\Wscenarios?\W\(.+\)')
        self.pass_re = re.compile(r'[1-9]+ passed\)')

        self.add_required_regex(r'.*feature$')

    def get_state(self):
        return {
            'tags': self.tags
        }

    def apply_state(self, state_obj):
        self.tags = state_obj.get('tags')
        self.add_tag_suffix()

    def update_log(self, feature_file, output):
        outcome = self.outcome_re.findall(output)
        if len(outcome) > 0:
            self.test_log['files'][feature_file] = outcome

        stripped = self.strip_ansi(output)
        passed = self.pass_re.search(stripped)
        if passed:
            self.log_pass()
        else:
            self.log_failure(feature_file)

    def process_cli_args(self):
        super(BehatRunner, self).process_cli_args()
        self._extract_tags()
        self._extract_config_file()

    def _extract_tags(self):
        args = self.cli_args
        if '--tags' in args:
            for t in args[args.index('--tags')].split(','):
                self.tags.add(t)
        for a in args:
            if a[:1] == '@':
                self.tags.add(a[1:])

        self.add_tag_suffix()

    def add_tag_suffix(self):
        if len(self.tags) > 0:
            self.add_suffix('--tags ' + ','.join(self.tags))

            for t in self.tags:
                self.config_parts.append('@{0}'.format(t))

    def _extract_config_file(self):
        if '-c' in self.cli_args:
            idx = self.cli_args.index('-c')
            self.config_file = self.cli_args[idx + 1]
        else:
            self.config_file = 'behat.yml'

        path = os.path.join(self.command_path, self.config_file)
        if not os.path.isfile(path):
            print(self._bad('Bad config file: ' + path))
            self._quit()

        self.add_prefix('-c ' + self.config_file)
        self.config_parts.insert(0, self.config_file)

    def finish(self):
        pass


if __name__ == '__main__':
    if '--behat' in sys.argv:
        runner = BehatRunner()
        runner.set_cli_args(sys.argv)
        runner.run()

    if '--nose' in sys.argv:
        runner = PythonNoseRunner()
        runner.set_cli_args(sys.argv)
        runner.run()
