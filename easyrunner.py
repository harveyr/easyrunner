import os
import sys
import datetime
import subprocess as sub
import re
import urllib2
import pickle

class EasyRunner(object):
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
    cli_handlers = []
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
        self.cli_args = args
        self.process_cli_args()

    def set_base_path(self, path):
        self.base_path = path

    def set_title(self, title):
        self.title = title

    def set_command(self, command):
        self.command = command

    def set_command_path(self, path):
        if os.path.isdir(path):
            self.command_path = path
        else:
            print self._bad("Bad command path provided: " + str(path))

    def add_search_path(self, path):
        if path[0] == '~':
            path = os.path.expanduser(path)
        if os.path.exists(path):
            self.search_paths.add(path)

    def add_optional_regex(self, regex):
        self.file_optional_res.add(re.compile(regex, re.I))

    def add_required_regex(self, regex):
        self.file_required_res.add(re.compile(regex, re.I))

    def add_prefix(self, prefix):
        self.command_prefixes.add(prefix)

    def add_suffix(self, suffix):
        self.command_suffixes.add(suffix)

    def add_cli_handler(self, func):
        self.cli_handlers.append(func)

    def set_verbose(self, verbose):
        self.verbose = bool(verbose)

    def time_passed(self):
        diff = datetime.datetime.now() - self.start_time
        return str(diff).split('.')[0]

    def log_failure(self, target):
        self.test_log['failures'] += 1
        if target not in self.test_log['failed_tests']:
            self.test_log['failed_tests'].append(target)

    def log_pass(self):
        self.test_log['passes'] += 1

    def run(self):
        self.print_title()

        # If no CLI args, try to resume state of the last time this was run
        if len(self.cli_args) == 1:
            self.resume_state()
        else:
            self.validate()
            self.find_target_files()

            if len(self.target_files) == 0:
                print self._bad('No matches found.')
                self._quit()

            self.print_test_scope()
            self.prompt_user()

    def print_title(self):
        print self._header('\n----- ' + self.title + ' -----\n')

    def print_test_scope(self):
        print self._status('Target Files:')
        count = 1
        for f in self.target_files:
            parts = self._get_relative_search_path(f).split('/')
            number_prefix = "[{0}]".format(count)
            print "\t{0}: {1}".format(
                number_prefix,
                ('/'.join(parts[:-1]) + '/' + self._warn(parts[-1]))
            )
            count += 1

        if self.verbose != True:
            if 'silent' not in self.config_parts:
                self.config_parts.append('silent')
            try:
                self.config_parts.remove('verbose')
            except:
                pass
        else:
            if 'verbose' not in self.config_parts:
                self.config_parts.append('verbose')
            try:
                self.config_parts.remove('silent')
            except:
                pass

        colored_config_parts = [self._good(cp) for cp in self.config_parts]
        config_str = '[ ' + ' | '.join(colored_config_parts) + ' ]'
        print '{0} {1} {2}'.format(
            self._status('Targets:'),
            self._warn(str(len(self.target_files))),
            config_str)

    def print_commands(self):
        print
        print self._status('Commands')
        print '--------'
        print 'Enter\t\tRun the listed test files'
        print '#, #, #-#\tLimit to specified file numbers'
        print 'v\t\tToggle verbosity mode'
        print 'q | ^C\t\tQuit'


    def prompt_user(self):
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

        numbers = []
        parts = [part.strip() for part in c.split(',')]

        for part in parts:
            if '-' in part:
                span_parts = part.split('-')
                start = int(span_parts[0])
                end = int(span_parts[1])
                for i in range(start, end + 1):
                    numbers.append(i)
                continue
            try:
                num = int(part)
                if num < 1 or num > len(self.target_files):
                    print self._bad(('That number is not in the list, is it? ' +
                        'Try again.\n'))
                    return self.prompt_user()
                if num not in numbers:
                    numbers.append(num)
            except Exception as e:
                pass

        if len(numbers) > 0:
            filtered = [self.target_files[i-1] for i in numbers]
            self.target_files = filtered
            self.print_test_scope()
            self.prompt_user()
            return

        self.save_state()
        self.run_tests()

    def prompt_resume_state(self):
        try:
            print
            c = raw_input(self._status('Re-run last batch?'))
        except:
            self._quit()
        c = c.lower()
        if c == 'q' or c == 'n':
            self._quit()
        self.run_tests()


    def get_state_save_path(self):
        filename = '.{0}_state'.format(
            ('_'.join(self.title.split(' '))).lower())
        script_path = '/'.join(os.path.realpath(__file__).split('/')[:-1])
        return os.path.join(script_path, filename)

    def load_state(self):
        try:
            with open(self.get_state_save_path()) as f:
                return pickle.load(f)
        except IOError as e:
            return False

    def save_state(self):
        state = {
            'files': self.target_files,
            'verbose': self.verbose
        }
        child_state = self.get_state()
        for key in child_state:
            state[key] = child_state[key]

        f = file(self.get_state_save_path(), "w")
        pickle.dump(state, f)

    def get_state(self):
        """Override me"""
        return {}

    def apply_state(self, state_obj):
        """Override me"""
        pass

    def run_tests(self):
        if self.command_path:
            os.chdir(self.command_path)

        self.start_time = datetime.datetime.now()
        for t in self.target_files:
            self._run_command(t)
        self._finish()


    def _run_command(self, target_file):
        cmd = self._build_command(target_file)

        print '\n' + target_file
        print self._status(cmd)

        try:
            p = sub.Popen(cmd, stdout=sub.PIPE, stderr=sub.PIPE, shell=True)
            output = ''
            if self.verbose is True:
                for line in iter(p.stdout.readline, ""):
                    output += line
                    print line.rstrip()
            else:
                output, errors = p.communicate()
                if errors:
                    print errors

            self._handle_output(target_file, output)

        except KeyboardInterrupt:
            if p:
                print self._warn('\nABORTING...')
                print 'Terminating current process...'
                p.terminate()
                print '... done.'
                self._quit()

        # except Exception as e:
        #     print self._bad('Exception: ') + str(e)


    def _build_command(self, target_file):
        prefixes = ' '.join(self.command_prefixes)
        suffixes = ' '.join(self.command_suffixes)
        return '{0} {1}'.format(
            self.command,
            ' '.join([prefixes, target_file, suffixes]))

    def _handle_output(self, target_file, output):
        self.test_log['files'][target_file] = output
        self._update_log(target_file, output)
        self.print_tally()

    def _update_log(self, target_file, output):
        # Override me
        pass

    def _format_progress_str(self, progress, total):
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
        pass_str = self._good('{0} passed'.format(self.test_log['passes']))
        fail_str = self._bad('{0} failed'.format(self.test_log['failures']))

        tests_run_count = len(self.test_log['files'])
        total_count = len(self.target_files)

        f_count_str = self._status('{0}/{1} tests run'.format(
            tests_run_count,
            total_count))

        print '\n{0}: {1} | {2}  [{3}] [{4}]'.format(
            self._header('Test Suite Tally'),
            pass_str,
            fail_str,
            self._status(self.time_passed()),
            f_count_str)

        if total_count > 1:
            print self._format_progress_str(tests_run_count, total_count)

        if len(self.test_log['failed_tests']) > 0:
            print self._warn('Failures:\n{0}'.format(
                '\n'.join(self.test_log['failed_tests'])))

    def _print_search_parameters(self):
        if len(self.file_required_res) + len(self.file_optional_res) == 0:
            self._bad('No search patterns provided.')
            self._quit()

        print self._status('Search Parameters')
        if len(self.file_required_res) > 0:
            pats = [self._warn(r.pattern) for r in self.file_required_res]
            s = '\tFile must match {0} of these patterns: '.format(
                self._warn('all'))
            s += ' | '.join(pats)
            print s
        if len(self.file_optional_res) > 0:
            pats = [self._status(r.pattern) for r in self.file_optional_res]
            s = '\tFile must match {0} of these patterns: '.format(
                self._status('any'))
            s += ' | '.join(pats)
            print s

    def find_target_files(self):
        self._print_search_parameters()
        print self._status('Searching...')
        total_file_count = 0
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
                    print root_path_str
                else:
                    print self._status(root_path_str + ' [{0}]'.format(count))

        print '... finished searching {0} files.\n'.format(
            total_file_count)

    def evaluate_candidate_file(self, file_path):
        """Returns True if test file matches filter params."""
        skip = False
        # Check if it fails any of the required patterns
        for r in self.file_required_res:
            if not r.search(file_path):
                return False

        # If all required patterns match and the --all flag has been passed,
        # return True
        if self.use_all_files is True:
            return True

        # Make sure it matches at least one optional pattern.
        # (And handle the case when only required patterns are
        # provided.)
        for r in self.file_optional_res:
            if r.search(file_path) is not None:
                return True

        return False

    def validate(self):
        """Make sure necessary paths exist."""
        paths = self.search_paths.copy()
        paths.add(self.command_path)
        for p in paths:
            if not os.path.isdir(p):
                self._bad('Bad path: ' + p)
                self._quit()

    def process_cli_args(self):
        for a in self.cli_args[1:]:
            self._process_cli_arg(a)

    def _process_cli_arg(self, arg):
        idx = self.cli_args.index(arg)
        if arg == '-sp':
            self.add_search_path(self.cli_args[idx + 1])
        elif arg == '-cp':
            self.set_command_path(self.cli_args[idx + 1])
        elif arg == '-op':
            self.add_optional_regex(self.cli_args[idx + 1])
        elif arg == '-rp':
            self.add_required_regex(self.cli_args[idx + 1])
        elif arg == '--all':
            self.use_all_files = True
            self.config_parts.append(arg)
        elif arg == '-v' or arg == '--verbose':
            self.set_verbose(True)

    def resume_state(self):
        state_obj = self.load_state()
        if not state_obj:
            print 'No arguments. Need to add a usage statement.'
            self._quit()
        self.target_files = state_obj.get('files')
        self.verbose = state_obj.get('verbose')
        self.apply_state(state_obj)
        self.print_test_scope()
        self.prompt_resume_state()


    def print_log(self):
        if len(self.test_log) == 0:
            print self._warn('\nNO RESULTS')
            return

        print self._header('\nRESULTS')
        for tf in self.target_files:
            if not tf in self.test_log['files']:
                continue

            print self._status(tf)
            print ' - ' + ' | '.join(self.test_log['files'][tf])


    def _finish(self):
        pass

    def _get_relative_search_path(self, file_path):
        for path in self.search_paths:
            if path in file_path:
                return file_path.split(path)[1][1:]

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
        print '\nFare thee well.'
        sys.exit()



class NoseRunner(EasyRunner):
    def __init__(self):
        self.set_title('Nose Runny')
        self.set_command('nosetests')


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
        self.fail_re = re.compile(r'(execution failed)|(Exception has been thrown)|((\d+) (failed|undefined))', re.I)

        self.add_required_regex(r'.*feature$')

    def get_state(self):
        return {
            'tags': self.tags
        }

    def apply_state(self, state_obj):
        self.tags = state_obj.get('tags')
        self.add_tag_suffix()

    def _update_log(self, feature_file, output):
        outcome = self.outcome_re.findall(output)
        if len(outcome) > 0:
            self.test_log['files'][feature_file] = outcome

        failed = self.fail_re.search(output)
        if failed is not None:
            self.log_failure(feature_file)
        else:
            self.log_pass()

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
            print self._bad('Bad config file: ' + path)
            self._quit()

        self.add_prefix('-c ' + self.config_file)
        self.config_parts.insert(0, self.config_file)


    def _finish(self):
       pass

if __name__ == '__main__':
    if '--behat' in sys.argv:
        runner = BehatRunner()
        runner.set_cli_args(sys.argv)
        runner.run()

    if '--nose' in sys.argv:
        runner = NoseRunner()
        runner.set_cli_args(sys.argv)
        runner.run()
