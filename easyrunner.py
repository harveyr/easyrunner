import os
import sys
import datetime
import subprocess as sub
import re
import urllib2

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
    start_time = None

    cli_args = None
    cli_handlers = []

    verbose = False

    fail_re = None
    success_re = None

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
        self._process_cli_args()

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

    def prompt_user(self):
        try:
            c = raw_input(self._status('\nContinue? [Y/n] '))
        except:
            self._quit()
        if c.lower()[:1] == 'n':
            self._quit()

        return True

    def run(self):
        self.print_title()
        self._validate()
        self._find_target_files()

        if len(self.target_files) == 0:
            print self._bad('No matches found.')
            self._quit()
        
        if self.command_path:
            os.chdir(self.command_path)
        
        self.print_prompt_msg()
        
        if self.prompt_user():
            self._run_tests()
            self._finish()

    def print_title(self):
        print self._header('\n----- ' + self.title + ' -----\n')

    def print_prompt_msg(self):
        print self._status('Target Files:')
        for f in self.target_files:
            parts = self._get_relative_search_path(f).split('/')
            print '\t' + '/'.join(parts[:-1]) + '/' + self._warn(parts[-1])

    def _run_tests(self):
        self.start_time = datetime.datetime.now()
        for t in self.target_files:
            self._run_command(t)

    def _run_command(self, target_file):
        cmd = self._build_command(target_file)

        print self._status('\n' + cmd)

        try:
            p = sub.Popen(cmd, stdout=sub.PIPE, stderr=sub.PIPE, shell=True)
            output, errors = p.communicate()
            if self.verbose is True:
                print output
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
        # Override me
        pass

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

    def _find_target_files(self):
        self._print_search_parameters()
        print self._status('Searching...')
        total_file_count = 0
        for path in self.search_paths:
            for root, subFolders, files in os.walk(path):
                count = 0
                for f in files:
                    skip = False
                    total_file_count += 1
                    # print root + '    ' + f
                    f_path = os.path.join(root,f)
                    # Check if it fails any of the required patterns
                    for r in self.file_required_res:
                        if not r.search(f_path):
                            # print f_path + ' failed ' + r.pattern
                            skip = True
                    if skip:
                        continue
                    
                    # Make sure it matches at least one optional pattern.
                    # (And handle the case when only required patterns are
                    # provided.)
                    if len(self.file_optional_res) > 0:
                        skip = True
                    for r in self.file_optional_res:
                        if r.search(f_path) is not None:
                            skip = False
                            break

                    if skip is not True:
                        self.target_files.append(f_path)
                        count += 1
                s = '\t' + root
                if count == 0:
                    print s
                else:
                    print self._status(s + ' [{0}]'.format(count))

        print '... finished searching {0} files.\n'.format(
            total_file_count)

    def _validate(self):
        # if not self.command_path:
        #     print self._bad("I don't have a command path!")
        #     self._quit()

        paths = self.search_paths.copy()
        paths.add(self.command_path)
        # paths.add(self.command_path)
        for p in paths:
            if not os.path.isdir(p):
                self._bad('Bad path: ' + p)
                self._quit()

    def _process_cli_args(self):
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
        elif arg == '-v':
            self.set_verbose(True)

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
    test_log = {
        'features': {},
        'passes': 0,
        'failures': 0,
        'failed_features': []
    }

    features = []
    config_file = None

    outcome_re = None
    pass_count_re = None
    fail_count_re = None

    tags = set()

    def __init__(self):
        super(BehatRunner, self).__init__()
        self.set_title('Behat Runner')
        self.set_command('bin/behat')
        self.add_suffix('--ansi')
        self.outcome_re = re.compile(r'\d+\Wscenarios?\W\(.+\)')
        self.pass_count_re = re.compile(r'(\d+) passed', re.I)
        self.fail_count_re = re.compile(r'(\d+) failed', re.I)
        
        self.add_required_regex(r'.*feature$')

    def print_prompt_msg(self):
        print self._status('The following feature files will be run:')
        for f in self.target_files:
            parts = self._get_relative_search_path(f).split('/')
            print '\t' + '/'.join(parts[:-1]) + '/' + self._warn(parts[-1])

        config_line = '[ ' + self._good(self.config_file)

        if len(self.tags) > 0:
            config_line += ' | '
            for t in self.tags:
                config_line += self._good('@{0} '.format(t))

        if self.verbose is True:
            config_line += ' | ' + self._good('verbose')

        config_line += ' ]'
        print config_line


    def _handle_output(self, feature_file, output):
        # if re.search(r'Error:', output) is not None:
        if 'Error:' in output:
            print self._bad(output.strip())
        else:
            self._update_log(feature_file, output)

        self.print_tally()

    def _update_log(self, feature_file, output):
        outcome = self.outcome_re.findall(output)

        if len(outcome) > 0:
            self.test_log['features'][feature_file] = outcome
            pass_count = self.pass_count_re.findall(outcome[0])
            if (len(pass_count) > 0):
                self.test_log['passes'] += int(pass_count[0])

            fail_count = self.fail_count_re.findall(outcome[0])
            if (len(fail_count) > 0):
                self.test_log['failures'] += int(fail_count[0])
                f_name = feature_file.split('/')[-1]
                self.test_log['failed_features'].append(f_name)
                print output

    def _process_cli_args(self):
        super(BehatRunner, self)._process_cli_args()
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

        if len(self.tags) > 0:
            self.add_suffix('--tags ' + ','.join(self.tags))
        
    def _extract_config_file(self):
        if '-c' in self.cli_args:
            idx = self.cli_args.index('-c')
            self.config_file = self.cli_args[idx + 1]
        else:
            self.config_file = 'behat.yml'

        path = os.path.join(self.command_path, self.config_file)
        if not os.path.isfile(path):
            print self._bad('Bad config file: ' + path)

    def _finish(self):
        self.print_log()

    def print_tally(self):
        pass_str = self._good('{0} passes'.format(self.test_log['passes']))
        fail_str = self._bad('{0} failures'.format(self.test_log['failures']))

        f_count_str = self._status('{0}/{1} features'.format(
            len(self.test_log['features']),
            len(self.target_files)))

        print '------'
        print '{0}: {1} | {2}  [{3}] [{4}]'.format(
            self._header('Test Suite Tally'),
            pass_str,
            fail_str,
            self._status(self.time_passed()),
            f_count_str)

        if len(self.test_log['failed_features']) > 0:
            print self._warn('Failures: {0}'.format(
                ', '.join(self.test_log['failed_features'])))
        print '------'

    def print_log(self):
        if len(self.test_log) == 0:
            print self._warn('\nNO RESULTS')
            return

        print self._header('\nRESULTS')
        for feature in self.target_files:
            if not feature in self.test_log['features']:
                continue

            print self._status(feature)
            print ' - ' + ' | '.join(self.test_log['features'][feature])
            # for r in l['results']:
            #     print ' - ' + r
if __name__ == '__main__':
    if '--behat' in sys.argv:
        runner = BehatRunner()
        runner.set_cli_args(sys.argv)
        runner.run()
    
    if '--nose' in sys.argv:
        runner = NoseRunner()
        runner.set_cli_args(sys.argv)
        runner.run()
