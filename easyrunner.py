import os
import sys
import datetime
import subprocess as sub
import re
import urllib2

class EasyRunner(object):
    title = None
    command = None
    command_preps = set()
    command_path = None
    command_prefixes = set()
    command_suffixes = set()
    search_paths = set()
    file_res = set()
    target_files = []
    start_time = None

    cli_args = None
    cli_handlers = []
    output_handlers = set()

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
        pass

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
            print self._problem("Bad command path: " + str(path))

    def add_search_path(self, path):
        if path[0] == '~':
            path = os.path.expanduser(path)
        if os.path.exists(path):
            self.search_paths.add(path)
            print 'adding search path ' + path

    def add_file_regex(self, regex):
        self.file_res.add(regex)

    def add_prefix(self, prefix):
        self.command_prefixes.add(prefix)

    def add_suffix(self, suffix):
        self.command_suffixes.add(suffix)

    def add_cli_handler(self, func):
        self.cli_handlers.append(func)

    def add_output_handler(self, func):
        self.output_handlers.add(func)

    def set_verbose(self, verbose):
        self.verbose = bool(verbose)

    def time_passed(self):
        diff = datetime.datetime.now() - start_time
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
        self._validate()
        self._find_target_files()
        os.chdir(self.command_path)
        print_prompt_msg()
        if prompt_user():
            self._run_tests()

    def print_prompt_msg():
        pass

    def _run_tests(self):
        self.start_time = datetime.datetime.now()
        for t in self.target_files:
            self._run_command(t)

    def _run_command(self, target_file):

        cmd = self._build_command(target_file)

        print self._status('\n' + cmd)

        print 'still just testing...'
        return
        

        try:
            p = sub.Popen(cmd.split(' '), stdout=sub.PIPE, stderr=sub.PIPE)
            output, errors = p.communicate()
            if self.verbose is True:
                print output
            if errors:
                print errors

            for func in self.output_handlers:
                func(test_file, output)

        except KeyboardInterrupt:
            if p:
                print self._warn('\nABORTING...')
                print 'Terminating current process...'
                p.terminate()
                print '... done.'

        except Exception as e:
            print self._problem('Exception: ') + str(e)

    def _build_command(self, target_file):
        prefixes = ' '.join(self.command_prefixes)
        suffixes = ' '.join(self.command_suffixes)
        return self.command + ' '.join([prefixes, target_file, suffixes])

    def _find_target_files(self):
        print self._status('Searching ...')
        for path in self.search_paths:
            # print '\tpath: ' + path
            count = 0
            for root, subFolders, files in os.walk(path):
                for f in files:
                    # print '\t file: ' + f
                    f_path = os.path.join(root,f)
                    for r in self.file_res:
                        # print '\tregex: ' + r
                        if re.search(r, f_path, re.I) is not None:
                            self.target_files.append(f_path)
                            count += 1
                            break

            print path + self._status(' [{0}]'.format(count))

    def _validate(self):
        if not self.command_path:
            print self._problem("I don't have a command path!")
            self._quit()

        paths = self.search_paths
        paths.add(self.command_path)
        for p in paths:
            if not os.path.isdir(p):
                self._problem('Bad path: ' + p)

    def _process_cli_args(self):
        self.add_file_regex(r'{0}'.format(self.cli_args[1]))

        for a in self.cli_args[2:]:
            self._process_cli_arg(a)

    def _process_cli_arg(self, arg):
        idx = self.cli_args.index(arg)
        if arg == '--sp':
            for i in range(idx + 1, len(self.cli_args)):
                n_arg = self.cli_args[i]
                self.add_search_path(n_arg)
        if arg == '--cp':
            path = self.cli_args[idx + 1]
            self.set_command_path(path)

    def _status(self, text):
        return self.clr.get('BLUE') + text + self.clr.get('ENDC')

    def _problem(self, text):
        return self.clr.get('FAIL') + text + self.clr.get('ENDC')

    def _warn(self, text):
        return self.clr.get('WARN') + text + self.clr.get('ENDC')

    def _quit(self):
        sys.exit()


class BehatRunner(EasyRunner):
    test_log = {
        'features': [],
        'passes': 0,
        'failures': 0,
        'failed_features': []
    }

    features = []
    outcome_re = None
    pass_count_re = None
    fail_count_re = None

    tags = set()

    def __init__(self):
        super(BehatRunner, self).__init__()

        self.set_command('bin/behat')
        self.add_suffix('--ansi')
        self.outcome_re = re.compile(r'\d+\Wscenarios?\W\(.+\)')
        self.pass_count = re.compile(r'(\d+) passed')
        self.fail_count_re = re.compile(r'(\d+) failed')
        self.add_output_handler(self._update_log)

    def _update_log(self, feature, output):
        outcome = self.outcome_re.findall(output)

        test_log['features'][feature] = outcome

        if len(outcome) > 0:
            pass_count = self.pass_count_re.findall(results_lines[0])
            if (len(pass_count) > 0):
                test_log['passes'] += int(pass_count[0])

            fail_count = self.fail_count_re.findall(outcome[0])
            if (len(fail_count) > 0):
                test_log['failures'] += int(fail_count[0])
                f_name = feature.split('/')[-1]
                test_log['failed_features'].append(f_name)
                print output

    def _process_cli_args(self):
        super(BehatRunner, self)._process_cli_args()
        self._extract_tags()

    def _extract_tags(self):
        args = self.cli_args
        if '--tags' in args:
            for t in args[args.index('--tags')].split(','):
                self.tags.add(t)
        for a in args:
            if a[:1] == '@':
                self.tags.add(a[1:])
        print 'tags: ' + str(self.tags)

        self.add_suffix('--tags ' + ','.join(self.tags))
        
        # print_log()
        # print_tally()


if __name__ == '__main__':
    if '--behat' in sys.argv:
        runner = BehatRunner()
        runner.set_cli_args(sys.argv)
        runner.run()
