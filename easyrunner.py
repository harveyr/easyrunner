# TODO
# - Paging through failures


import os
import sys
import datetime
import Queue
import subprocess as sub
import threading
from threading import Timer
import re
import urllib2
import pickle
import time
import signal
import tempfile
import math
import textwrap
import curses
from curses import ascii, panel
import logging
from logging import FileHandler
from collections import defaultdict

logger = logging.getLogger(__name__)

TEST_SCOPE_VIEW_MODE = 0
TEST_STATUS_VIEW_MODE = 1

FILENAME_SEARCH_MODE = 0
TESTNAME_SEARCH_MODE = 1

def is_int(s):
    try:
        _ = int(s)
        return True
    except ValueError, e:
        return False

def ellipsify(s, max_chars):
    len_s = len(s)
    if len_s > max_chars:
        start_idx = abs(len_s - max_chars + 4)
        return '...' + s[start_idx:]
    return s

class CursesHelper(object):
    window_h = None
    window_w = None
    cur_y = 0
    cur_x = 0
    panels = {}

    def __init__(self):

        def init_curses(window=None):
            # self.window = window
            self.window = curses.initscr()
            self.window.keypad(True)
            curses.start_color()
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(2, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
            curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)
            curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)
            curses.init_pair(9, curses.COLOR_BLACK, curses.COLOR_WHITE)

            self.padcols = 1
            self.pad = ' '.join('' for i in range(self.padcols + 1))

            self.default_cpair = curses.color_pair(1)
            self.heading_cpair = curses.color_pair(2)
            self.highlight_cpair = curses.color_pair(3)
            self.green_cpair = curses.color_pair(4)
            self.red_cpair = curses.color_pair(5)
            self.yellow_cpair = curses.color_pair(6)
            self.warn_cpair = curses.color_pair(6)
            self.bg_highlight_cpair = curses.color_pair(9)

        # curses.wrapper(init_curses)
        init_curses()

    def addstr(self, y, x, s, pair=None, win=None):
        if win is None:
            win = self.window
        if pair is None:
            pair = self.default_cpair
        try:
            win.addstr(y, x, s, pair)
        except curses.error, e:
            pass

    def addnstr(self, y, x, s, n, pair=None):
        if pair is None:
            pair = self.default_cpair
        try:
            self.window.addnstr(y, x, s, n, pair)
        except curses.error, e:
            pass

    def get_window(self):
        return self.window

    def get_size(self, panel_key=None):
        if panel_key is None:
            return self.window.getmaxyx()
        else:
            return self.panels[panel_key].window().getmaxyx()

    def get_panel(self, panel_key, nlines=None, ncols=None, begin_y=None, begin_x=None):
        if not hasattr(self.panels, panel_key):
            win_h, win_w = self.get_size()
            if nlines is None:
                nlines = int(win_h / 1.3)
            if ncols is None:
                ncols = int(win_w / 1.3)
            if begin_y is None:
                begin_y = int((win_h - nlines) / 2)
            if begin_x is None:
                begin_x =  int((win_w - ncols) / 2)

            win = self.window.subwin(nlines, ncols, begin_y, begin_x)
            p = panel.new_panel(win)
            p.window().border(0)
            p.show()
            p.top()
            self.panels[panel_key] = p
        return self.panels[panel_key]

class TestThread(threading.Thread):
    def __init__(self, command_path, target_file, test_name, command, callback):
        threading.Thread.__init__(self)
        self.command_path = command_path
        self.target_file = target_file
        self.test_name = test_name
        self.command = command
        self.callback = callback

    def run(self):
        self.p = sub.Popen(
            self.command,
            cwd=self.command_path,
            stdout=sub.PIPE,
            stderr=sub.PIPE,
            shell=True)

        output, errors = self.p.communicate()
        self.callback(self, self.target_file, self.test_name, output, errors)

    def stop(self):
        self.p.terminate()

    def get_target_file(self):
        return self.target_file

class EasyRunnerTestLog(object):
    loop = None
    log = None

    def __init__(self):
        self.reset()

    def reset(self):
        self.log = {
            'loops': {},
            'cumulative': {
                'files': {},
            }
        }
        self.loop = 0

    def new_loop(self):
        self.loop += 1
        self.log['loops'][self.loop] = {
            'files': {},
            'pass_count': 0,
            'fail_count': 0
        }

    def get_loop(self):
        return self.loop

    def get_loop_log(self, loop):
        return self.log['loops'][loop]

    def get_current_loop_log(self):
        return self.log['loops'][self.get_loop()]

    def init_log(self, filename, test_name=None):
        loop_log = self.get_current_loop_log()
        if not filename in loop_log['files']:
            loop_log['files'][filename] = {
                'pass_count': 0,
                'fail_count': 0,
                'tests': {}
            }
        if test_name is not None:
            if not test_name in loop_log['files'][filename]['tests']:
                loop_log['files'][filename]['tests'][test_name] = {
                'pass_count': 0,
                'fail_count': 0
            }

        if not filename in self.log['cumulative']['files']:
            self.log['cumulative']['files'][filename] = {
                'pass_count': 0,
                'fail_count': 0,
                'tests': {}
            }
        f_cuml_log = self.log['cumulative']['files'][filename]
        if not test_name in f_cuml_log['tests']:
            f_cuml_log['tests'][test_name] = {
                'pass_count': 0,
                'fail_count': 0
            }

    def get_cumulative_log(self, filename, test_name=None):
        self.init_log(filename, test_name)
        if test_name is None:
            return self.log['cumulative']['files'][filename]
        else:
            return self.log['cumulative']['files'][filename]['tests'][test_name]

    def get_loop_log_for_test(self, filename, test_name=None):
        self.init_log(filename, test_name)
        file_log = self.get_current_loop_log()['files'][filename]
        if test_name is None:
            return file_log
        else:
            return file_log['tests'][test_name]

    def get_loop_pass_count(self, filename, test_name=None):
        return self.get_loop_log_for_test(
            filename,
            test_name)['pass_count']

    def get_loop_fail_count(self, filename, test_name=None):
        return self.get_loop_log_for_test(
            filename,
            test_name)['fail_count']

    def get_cumulative_pass_count(self, filename, test_name=None):
        return self.get_cumulative_log(filename, test_name)['pass_count']

    def get_cumulative_fail_count(self, filename, test_name=None):
        return self.get_cumulative_log(filename, test_name)['fail_count']

    def log_pass(self, filename, test_name=None):
        self.get_current_loop_log()['pass_count'] += 1
        self.get_loop_log_for_test(
            filename,
            test_name)['pass_count'] += 1
        self.get_cumulative_log(filename, test_name)['pass_count'] += 1

    def log_failure(self, filename, test_name=None):
        self.get_current_loop_log()['fail_count'] += 1
        self.get_loop_log_for_test(
            filename,
            test_name)['fail_count'] += 1
        self.get_cumulative_log(filename, test_name)['fail_count'] += 1

    def get_all_loop_tests(self, loop=None, test_names=False):
        if loop is None:
            loop = self.get_loop()

        log = self.get_loop_log(loop=loop)

        all_ = []
        failed = []
        passed = []

        for filename in log['files']:
            if test_names is False:
                all_.append(filename)
                if self.get_loop_pass_count(filename) > 0:
                    passed.append(filename)
                if self.get_loop_fail_count(filename) > 0:
                    failed.append(filename)
            else:
                tests_log = log['files'][filename]['tests']
                for test_name in tests_log:
                    all_.append(test_name)
                    if self.get_loop_pass_count(filename, test_name) > 0:
                        passed.append(test_name)
                    if self.get_loop_fail_count(filename) > 0:
                        passed.append(test_name)
        all_.sort()
        passed.sort()
        failed.sort()
        return (all_, passed, failed)

    def get_all_failed_tests(self):
        failed_tests = defaultdict()
        cfl = self.log['cumulative']['files']
        for filename in cfl:
            failed_in_file = []
            for test_name in cfl[filename]['tests']:
                if cfl[filename]['tests'][test_name]['fail_count'] > 0:
                    failed_in_file.append(test_name)
            if len(failed_in_file) > 0:
                failed_in_file.sort()
                failed_tests[filename] = failed_in_file
        return failed_tests

    def get_all_failed_files(self):
        """Get all failed files from all loops."""
        failed_files = set()
        for filename in self.log['cumulative']['files']:
            if self.log['cumulative']['files'][filename]['fail_count'] > 0:
                failed_files.add(filename)
        l = list(failed_files)
        l.sort()
        return l

class EasyRunner(object):

    title = 'EasyRunner'
    command = None
    command_preps = set()
    command_path = None
    command_prefixes = set()
    command_suffixes = set()
    search_paths = set()
    file_extensions = set()
    file_optional_res = set()
    file_required_res = set()
    all_files = []
    filtered_files = []
    selected_filtered_test_indices = []
    temp_selection_indices = []
    pending_test_indices = []
    search_file_page = 0
    failure_list_page = 0
    total_test_count = None
    use_all_files = False
    start_time = None
    input_buffer = ''

    view_mode = TEST_SCOPE_VIEW_MODE
    search_mode = FILENAME_SEARCH_MODE

    output_log_f = 'easyrunner.log'

    test_setup_funcs = []

    test_poll_delay = 1

    can_search_in_files = False

    can_parallel = False
    run_parallel = False
    max_parallel_count = 3
    test_threads = []

    cli_args = None
    cli_handlers = []
    config_parts = []

    verbose = False
    loop_mode = False

    pass_count_re = None
    fail_count_re = None

    clr = {
        'HEADER': '\033[95m',
        'BLUE': '\033[94m',
        'GREEN': '\033[92m',
        'WARN': '\033[93m',
        'FAIL': '\033[91m',
        'ENDC': '\033[0m'
    }

    def __init__(self):
        self.init_output_logs()

        self.init_curses()
        win_h, win_w = self.curses_helper.get_size()
        self.PROMPT_Y = win_h - 3
        self.CONFIG_Y = self.PROMPT_Y + 1
        self.CONTENT_Y = 4
        self.CONTENT_MAX_Y = win_h - 6

        self.log = EasyRunnerTestLog()

        self.commands = [
            {
                'command': ':a',
                'description': 'Queue all available test files.',
                'func': self.queue_all
            },
            {
                'command': ':c',
                'description': 'Clear current settings (reset).',
                'func': self.reset
            },
            {
                'command': ':cmd <filename>',
                'description': 'Print the command for the',
                'func': self.reset
            },
            {
                'command': ':go',
                'description': 'Run the tests.',
                'func': self.run_tests
            },
            {
                'command': ':l',
                'description': 'Toggle loop mode. If on, all failed tests will be run indefinity, with pass/fail tallies printed. This is helpful for finding flaky tests.',
                'func': self.toggle_loop_mode
            },
            {
                'command': ':out',
                'description': 'View the raw output of tests that have run.',
                'func': self.view_raw_output
            },
            {
                'command': ':par <#>',
                'description': 'Set parallel count (if available). For example: ":p 3".',
                'func': self.set_parallel_count
            },
            {
                'command': ':poll <#>',
                'description': 'Set poll delay in seconds. This affects how often the display is updated and test threads are spawned. If your tests execute very quickly, set this number lower. (Usage) :poll 1.5',
                'func': self.set_poll_delay
            },
            {
                'command': ':tn',
                'description': 'Test name mode. Search for test names, rather than just filenames. (If allowed.)',
                'func': self.set_search_mode_test_names
            },
            {
                'command': ':fn',
                'description': 'Filename mode. Search only for filenames (not within files for test names).',
                'func': self.set_search_mode_filename
            },
            {
                'command': ':?',
                'description': 'Get help.',
                'func': self.print_help
            },
            {
                'command': ':q',
                'description': 'Quit.',
                'func': self.quit
            },
        ]

    def init_output_logs(self):
        data_dir = os.path.expanduser('~/.easyrunner')
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        self.debug_log_path = os.path.join(data_dir, 'debug.log')
        with open(self.debug_log_path, 'w') as f:
            pass

        logger.setLevel(logging.DEBUG)
        LOGFORMATTER = logging.Formatter('[%(name)s:%(lineno)d] - %(levelname)s - %(message)s')
        FILEHANDLER = FileHandler(self.debug_log_path)
        FILEHANDLER.setFormatter(LOGFORMATTER)
        FILEHANDLER.setLevel(logging.DEBUG)
        logger.addHandler(FILEHANDLER)

        self.output_log_f = os.path.join(data_dir, 'tests.log')
        with open(self.output_log_f, 'w') as f:
            pass

    def reset(self):
        self.find_all_files()
        self.find_all_tests()
        self.filtered_files = list(self.all_files)
        self.selected_filtered_test_indices = []
        self.log = EasyRunnerTestLog()
        self.pending_test_indices = []
        self.total_test_count = None
        self.start_time = None
        self.set_default_feedback()
        self.failure_list_page = 0
        self.search_file_page = 0
        self.view_mode = TEST_SCOPE_VIEW_MODE
        self.draw()

    def strip_ansi(self, text):
        return re.sub(r'\033\[[0-9;]+m', '', text)

    def init_curses(self):
        self.curses_helper = CursesHelper()

    def is_running(self):
        return len(self.test_threads) > 0 or len(self.pending_test_indices) > 0

    def in_filename_search_mode(self):
        return self.search_mode == FILENAME_SEARCH_MODE

    def in_testname_search_mode(self):
        return self.search_mode == TESTNAME_SEARCH_MODE

    def should_print_test_status(self):
        return self.is_running() or self.view_mode == TEST_STATUS_VIEW_MODE

    def draw(self, clear=False):
        if not self.curses_helper:
            return

        ch = self.curses_helper
        win_h, win_w = ch.get_size()

        ch.window.erase()

        self.draw_window()
        if self.should_print_test_status():
            self.print_test_run_status()
        else:
            self.print_test_scope()
        self.print_config()
        self.print_padding()
        self.print_feedback()
        self.print_prompt()
        ch.window.redrawwin()
        ch.window.refresh()

    def print_padding(self):
        ch = self.curses_helper
        for y in range(self.CONTENT_Y, self.CONTENT_MAX_Y):
            for x in range(0, ch.padcols):
                ch.addstr(y, x, ' ')

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
            raise("Bad command path provided: " + str(path))

    def add_search_path(self, path):
        if path[0] == '~':
            path = os.path.expanduser(path)
        if os.path.exists(path):
            self.search_paths.add(path)

    def add_file_extension(self, extension):
        self.file_extensions.add(extension)

    def add_optional_regex(self, regex):
        self.file_optional_res.add(re.compile(regex, re.I))

    def add_required_regex(self, regex):
        self.file_required_res.add(re.compile(regex, re.I))

    def reset_required_res(self):
        self.file_required_res = set()

    def add_prefix(self, prefix):
        self.command_prefixes.add(prefix)

    def add_test_setup_func(self, func):
        self.test_setup_funcs.append(func)

    def add_suffix(self, suffix):
        self.command_suffixes.add(suffix)

    def set_search_mode_filename(self):
        self.search_mode = FILENAME_SEARCH_MODE
        self.search_file_page = 0

    def set_search_mode_test_names(self):
        if self.can_search_in_files:
            self.search_mode = TESTNAME_SEARCH_MODE
            self.search_file_page = 0
        else:
            self.feedback_str = '[Test name searching not enabled for this test suite]'

    def toggle_parallel_mode(self):
        self.run_parallel = not self.run_parallel

    def set_poll_delay(self):
        failed = False
        try:
            delay = float(self.input_buffer.split(' ')[1])
            self.test_poll_delay = round(delay, 2)
        except ValueError, e:
            failed = True
        except IndexError, e:
            failed = True

        if failed is True:
            self.feedback_str = "{0} {1}".format(
                "That didn't work.",
                "This command should look like :poll 1.5")

    def set_parallel_count(self):
        try:
            s = self.input_buffer
            count = int([p.strip() for p in s.split(':p') if p != ''][0])
            self.max_parallel_count = count
            self.run_parallel = True
            self.draw_window()
        except IndexError:
            self.max_parallel_count = 1
            self.run_parallel = False
        self.draw()

    def toggle_loop_mode(self):
        self.loop_mode = not self.loop_mode
        self.draw()

    def time_passed(self):
        diff = datetime.datetime.now() - self.start_time
        return str(diff).split('.')[0]

    def check_window_size(self):
        min_w = 112
        min_h = 20
        win_h, win_w = self.curses_helper.window.getmaxyx()
        if win_h < min_h or win_w < min_w:
            msg = ('This script needs some breathing room. ' +
                'Please resize your terminal to at least 112 x 20.\n' +
                '(You are currently at {0} x {1}.)'.format(win_w, win_h))
            self.quit(error_msg=msg)

    def run(self):
        self.check_window_size()
        signal.signal(signal.SIGINT, self.sigint_handler)
        signal.signal(signal.SIGWINCH, self.resize_handler)
        self.reset()
        self.queue_all()
        self.draw()
        while True:
            try:
                self.get_user_input()
            except Exception, e:
                logger.error('Exception: ' + str(e))
                self.quit()

    def in_command_mode(self):
        return len(self.input_buffer) > 0 and self.input_buffer[0] == ':'

    def print_prompt(self):
        ch = self.curses_helper
        win_h, win_w = ch.get_size()
        y = self.PROMPT_Y
        x = ch.padcols
        s = '> ' + self.input_buffer
        ch.window.addstr(y, x, s)
        curses.curs_set(2)
        ch.window.clrtoeol()

    def get_user_input(self):
        logger.debug('get_user_input')
        if not self.curses_helper:
            logger.debug('no curses helper; returning')
            return

        win = self.curses_helper.window
        win_h, win_w = self.curses_helper.get_size()

        self.print_prompt()
        curses.cbreak()
        try:
            # if self.is_running():
            #     logger.debug('trying getch...')
            #     inp = win.getch()
            #     logger.debug('inp: ' + str(inp))
            #     return

            logger.debug('threading.current_thread(): ' + str(threading.current_thread()))
            logger.debug('waiting for input...')
            inp = win.getkey()
            logger.debug('input: ' + str(inp))
        except curses.error, e:
            logger.debug('curses input error')
            return

        if inp == 'KEY_BACKSPACE':
            if len(self.input_buffer) > 0:
                self.input_buffer = self.input_buffer[:-1]
            inp = ''
            self.draw()

        if inp == ' ' and not self.in_command_mode():
            pass
        elif inp == 'KEY_RESIZE':
            self.check_window_size()
            h, w = win.getmaxyx()
            curses.resize_term(h, w)
            self.draw()
        elif inp == 'KEY_UP':
            self.key_up()
        elif inp == 'KEY_DOWN':
            self.key_down()
        elif inp in ['KEY_LEFT', 'KEY_RIGHT', 'KEY_SF']:
            pass
        elif inp == ':':
            self.input_buffer = ':'
            self.feedback_str = '[Command Mode (:? for a list)] '
            self.draw()
        elif len(self.input_buffer) > 0 and self.input_buffer[0] == ':':
            if inp == '\n':
                self.eval_command(execute=True)
            else:
                self.input_buffer += inp
                self.eval_command(execute=False)
        elif inp == '\n':
            if not self.is_running():
                if self.input_buffer == '':
                    logger.debug('calling run_tests()')
                    self.run_tests()
                    logger.debug('returned from run_tests()')
                else:
                    self.input_buffer = ''
            self.draw()
        else:
            self.input_buffer += inp

            if not self.is_running():
                self.view_mode = TEST_SCOPE_VIEW_MODE
                if len(self.input_buffer) > 0:
                    self.feedback_str = 'Filter string: ' + self.input_buffer
                else:
                    self.set_default_feedback()
                self.filter_files(self.input_buffer)
                self.draw()

        self.last_input = inp

    def key_up(self):
        if self.view_mode == TEST_SCOPE_VIEW_MODE:
            if self.search_file_page > 0:
                self.search_file_page -= 1
        elif self.view_mode == TEST_STATUS_VIEW_MODE:
            if self.failure_list_page > 0:
                self.failure_list_page -= 1
        self.draw()

    def key_down(self):
        if self.view_mode == TEST_SCOPE_VIEW_MODE:
            self.search_file_page += 1
        elif self.view_mode == TEST_STATUS_VIEW_MODE:
            self.failure_list_page += 1
        self.draw()

    def draw_window(self):
        ch = self.curses_helper
        win = ch.window
        win_h, win_w = self.curses_helper.get_size()
        content_top = 4

        win.hline(0, 0, curses.ACS_HLINE, win_w)
        ch.window.addstr(1, 0, '>')
        ch.window.addstr(1, win_w - 1, '<')
        ch.window.addstr(1, win_w / 2 - len(self.title) / 2, self.title,
            curses.color_pair(2))
        win.hline(2, 0, curses.ACS_HLINE, win_w)

    def set_default_feedback(self):
        self.feedback_str = '<Enter> to run targeted files, type some letters to search, or :? for help'

    def print_feedback(self):
        if not self.feedback_str:
            return

        ch = self.curses_helper
        win = ch.window
        win_h, win_w = ch.get_size()

        lines = textwrap.wrap(self.feedback_str, win_w - ch.padcols * 3)

        y = self.PROMPT_Y - len(lines)
        x = ch.padcols

        for line in lines:
            win.addstr(y, x, line, ch.green_cpair)
            ch.window.clrtoeol()
            y += 1

    def print_title(self):
        print self._header('\n----- ' + self.title + ' -----\n')

    def print_test_scope(self):
        win = self.curses_helper.window
        win_h, win_w = win.getmaxyx()
        y = self.CONTENT_Y
        x = self.curses_helper.padcols
        col1_w = col2_w = int(win_w / 2) - 10
        col2_start = win_w - col2_w - 4

        if self.search_mode == FILENAME_SEARCH_MODE:
            self.print_filename_search_mode_test_scope(col1_w, col2_start,
                col2_w)
        elif self.search_mode == TESTNAME_SEARCH_MODE:
            self.print_testname_search_mode_test_scope(col1_w, col2_start,
                col2_w)

    def print_testname_search_mode_test_scope(self, col1_w, col2_start, col2_w):
        ch = self.curses_helper
        win = self.curses_helper.window
        y = self.CONTENT_Y
        x = ch.padcols

        available_lines = self.CONTENT_MAX_Y - y - 2
        total_lines = 0
        test_indices_by_name = {}
        tests_by_index = {}
        test_count = 0
        for filename in self.filtered_tests:
            total_lines += 1
            test_indices_by_name[filename] = {}
            for test_name in self.filtered_tests[filename]:
                test_indices_by_name[filename][test_name] = test_count
                tests_by_index[test_count] = {
                    'filename': filename,
                    'test_name': test_name
                }
                test_count += 1
        self.tests_by_index = tests_by_index

        if total_lines < available_lines:
            start_idx = 0
            self.search_file_page = 0
        else:
            lines_per_page = int(available_lines * .8)
            page_count = int(total_lines / lines_per_page) + 1
            if self.search_file_page > page_count:
                self.search_file_page = page_count
            start_idx = self.search_file_page * lines_per_page

        y += 1
        line_count = 0
        break_ = False
        for filename in self.filtered_tests:
            line_count += 1
            if line_count + len(self.filtered_tests[filename]) < start_idx:
                continue
            head, tail = os.path.split(filename)
            head_s = ellipsify(head, col1_w - len(tail) - 3) + '/'
            ch.addstr(y, x, head_s, ch.highlight_cpair)
            ch.addstr(y, x + len(head_s), tail, curses.A_BOLD)
            y += 1
            for test_name in self.filtered_tests[filename]:
                line_count += 1
                idx = test_indices_by_name[filename][test_name]
                if idx in self.temp_selection_indices:
                    cpair = ch.bg_highlight_cpair
                else:
                    cpair = None
                s = ('  - [{0}] {1}'.format(
                        test_indices_by_name[filename][test_name] + 1,
                        ellipsify(test_name, col1_w - 10)))
                ch.addstr(y, x, s, cpair)
                y += 1
                if y == self.CONTENT_MAX_Y - 1:
                    break_ = True
                    break
            if break_ is True:
                break

        s = 'Search Results: {0} tests in {1} files'.format(test_count,
            len(self.filtered_tests))
        ch.addstr(self.CONTENT_Y, ch.padcols, s, ch.highlight_cpair)

        y = self.CONTENT_Y
        x = col2_start
        win.addstr(y, x, 'Targeted Files', ch.heading_cpair)
        win.addstr(' (these will be run)')
        y += 1
        selected_count = len(self.selected_filtered_test_indices)
        if selected_count > 0:
            target_count = selected_count
            for i in self.selected_filtered_test_indices:
                test_name = tests_by_index[i]['test_name']
                s = '[{0}] {1}'.format(i + 1,
                    ellipsify(test_name, col2_w - 2))
                ch.addstr(y, x, s, ch.highlight_cpair)
                y += 1
        else:
            target_count = len(self.filtered_files)
            ch.addstr(y, x, '<-- All search results will be run',
                ch.highlight_cpair)

    def print_filename_search_mode_test_scope(self, col1_w, col2_start, col2_w):
        ch = self.curses_helper
        win = ch.window
        win_h, win_w = ch.get_size()
        y = self.CONTENT_Y
        x = ch.padcols

        max_lines = self.CONTENT_MAX_Y - self.CONTENT_Y
        max_y = y + max_lines

        s = 'Search Results: {0} of {1} files with extension(s) {2}'.format(
            len(self.filtered_files),
            len(self.all_files),
            ','.join(self.file_extensions))

        ch.addstr(y, x, s, ch.heading_cpair)
        y += 1

        display_files = []
        for i in range(len(self.filtered_files)):
            if i in self.selected_filtered_test_indices:
                continue
            display_files.append(self.filtered_files[i])

        if len(display_files) == 0:
            win.addstr(y, x, 'No files matching search')
            return

        lines_per_page = int(max_lines * .8)
        page_count = int(math.ceil(len(display_files) / lines_per_page)) + 1
        if page_count * lines_per_page >= len(display_files):
            page_count -= 1

        self.search_file_page = min(page_count, self.search_file_page)
        start_idx = 0 + self.search_file_page * lines_per_page
        max_chars = col1_w - 4

        for i in range(start_idx, len(display_files)):
            f = display_files[i]
            f_idx = self.filtered_files.index(f)
            head, tail = os.path.split(f)
            head_s = ' [{0}] {1}/'.format(f_idx + 1,
                ellipsify(head, col1_w - len(tail) - len(str(f_idx + 1)) - 2))

            head_cpair = None
            tail_cpair = curses.A_BOLD

            if f_idx in self.temp_selection_indices:
                head_cpair = ch.bg_highlight_cpair
                tail_cpair = ch.bg_highlight_cpair

            x = ch.padcols
            ch.addstr(y, x, head_s, head_cpair)
            ch.addstr(y, x + len(head_s), tail, tail_cpair)
            y += 1
            if y >= self.CONTENT_MAX_Y - 1:
                break

        s = '<Use arrows to page up and down>'
        x = int(col1_w / 2 - len(s) / 2)
        if page_count > 1:
            win.addstr(y, x, s, ch.highlight_cpair)

        y = self.CONTENT_Y
        x = col2_start
        win.addstr(y, x, 'Targeted Files', ch.heading_cpair)
        win.addstr(' (these will be run)')
        y += 1
        selected_count = len(self.selected_filtered_test_indices)
        if selected_count > 0:
            target_count = selected_count
            for i in self.selected_filtered_test_indices:
                f = self.all_files[i]
                f_idx = self.filtered_files.index(f)
                head, tail = os.path.split(f)
                max_head_len = col2_w - len(tail) - len(str(i)) - 3
                head_s = '[{0}] {1}'.format(f_idx + 1,
                    ellipsify(head + '/', max_head_len))
                ch.addstr(y, x, head_s, ch.highlight_cpair)
                ch.addstr(y, x + len(head_s), tail, curses.A_BOLD)
                y += 1
        else:
            target_count = len(self.filtered_files)
            ch.addstr(y, x, '<-- All search results will be run',
                ch.highlight_cpair)

    def print_config(self):
        ch = self.curses_helper
        win = ch.window
        win_h, win_w = ch.get_size()
        y = self.CONFIG_Y

        try:
            win.addstr(y, ch.padcols, 'Config: ', curses.A_BOLD)

            win.addstr('[search ')
            if self.search_mode == FILENAME_SEARCH_MODE:
                win.addstr('filenames', ch.highlight_cpair)
            elif self.search_mode == TESTNAME_SEARCH_MODE:
                win.addstr('test names', ch.highlight_cpair)
            win.addstr('] ')

            win.addstr('[poll delay ')
            win.addstr(str(self.test_poll_delay), ch.highlight_cpair)
            win.addstr('] ')

            win.addstr('[parallel ')
            if self.run_parallel is True:
                win.addstr(str(self.max_parallel_count), ch.highlight_cpair)
            else:
                win.addstr('off')
            win.addstr('] ')

            win.addstr('[loop ')
            if self.loop_mode is True:
                win.addstr('on', ch.highlight_cpair)
            else:
                win.addstr('off')
            win.addstr('] ')

            y += 1
            x = ch.padcols
            s = 'Logs:   '
            w = int(win_w / 2 - 6 - len(s) / 2)

            win.addstr(y, x, s, curses.A_BOLD)
            logs1 = '[Output: {0}]'.format(ellipsify(self.output_log_f, w))
            logs2 = '[Debug: {0}] '.format(
                ellipsify(str(self.debug_log_path), w))

            win.addstr(logs1)
            win.addstr(' ')
            win.addstr(logs2)
        except curses.error, e:
            pass

    def parse_number_input(self):
        numbers = []
        s = self.input_buffer[1:]
        parts = [part.strip() for part in s.split(',')]
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
                if num not in numbers:
                    numbers.append(num)
            except Exception as e:
                pass
        return numbers

    def eval_command(self, execute=False):
        if not self.in_command_mode():
            return

        s = self.input_buffer
        if len(s) > 1 and is_int(s[1]):
            try:
                nums = [i - 1 for i in self.parse_number_input()]
                self.feedback_str = '<Enter> Queue test files: ' + str(nums)
                self.temp_selection_indices = nums
                self.draw()
                if execute is True:
                    for n in nums:
                        if n in self.selected_filtered_test_indices:
                            self.selected_filtered_test_indices.remove(n)
                        else:
                            self.selected_filtered_test_indices.append(n)
                        self.selected_filtered_test_indices.sort()
                    self.temp_selection_indices = []
                    self.draw()
            except ValueError, e:
                self.draw()
        else:
            for cmd in self.commands:
                if s[:3] == cmd['command'][:3]:
                    self.feedback_str = '<Enter> ' + cmd['description']
                    self.draw()
                    if execute is True:
                        func = cmd['func']
                        logger.debug('executing ' + cmd['description'])
                        func()
        if execute is True:
            self.input_buffer = ''
            self.draw()

    def print_help(self):

        logger.debug('print_help')

        def add_wrapped(y, x, text, width):
            for line in textwrap.wrap(text, width):
                win.addstr(y, x, line)
                y += 1
            return y

        intro = [
            {
                'heading': 'First: Search For Some Test Files',
                'body': 'Begin typing in some letters to search for files. Hit enter when you are satisfied with the list of files found.'
            },
            {
                'heading': 'Second (Optional): Select From Among Those Files',
                'body': "Currently, the best way to do this is by typing ':' to enter command mode, and then entering some numbers corresponding to the listed files. Hit enter to commit those files to the test queue. For example, ':1-5,11,15' would choose tests 1 through 5, 11, and 15."
            },
            {
                'heading': 'Third: Run the Tests',
                'body': "Either hit enter with a blank prompt, or run the ':go' command."
            },
        ]

        self.end_curses()

        print 'USAGE\n'

        for part in intro:
            print part['heading']
            print part['body']
            print

        print ''

        print('COMMANDS')

        for cmd in self.commands:
            logger.debug('command: ' + str(cmd))
            print(cmd['command'])
            print(cmd['description'])
            print

        print("NOTE!")
        print("If the script exist unexpectedly, your terminal may get messed up. Enter 'reset' to fix it. Trying to fix this.")

        print
        i = raw_input('<Hit enter to return>')
        self.init_curses()
        self.draw()

    def prompt_resume_state(self):
        try:
            print
            c = raw_input(
                self._status("Hit anything but 'q' to re-run last batch: "))
        except:
            self.quit()
        c = c.lower()
        if c == 'q' or c == 'n':
            self.quit()
        self.run_tests()

    def get_state_save_path(self):
        filename = '.{0}_state'.format(
            ('_'.join(self.title.split(' '))).lower())
        script_path = '/'.join(os.path.realpath(__file__).split('/')[:-1])
        return os.path.join(script_path, filename)

    def get_failure_save_path(self):
        return '{0}_failures'.format(self.get_state_save_path())

    def load_state(self, failure_state=False):
        if failure_state is False:
            path = self.get_state_save_path()
        else:
            path = self.get_failure_save_path()
        try:
            with open(path) as f:
                return pickle.load(f)
        except IOError as e:
            return False

    def save_state(self, failure_state=False):
        # if failure_state is False:
        #     save_path = self.get_state_save_path()
        #     files = self.target_files
        # else:
        #     save_path = self.get_failure_save_path()
        #     files = self.test_log['failed_files']

        # state = {
        #     'files': files,
        #     'verbose': self.verbose
        # }

        # child_state = self.get_state()
        # for key in child_state:
        #     state[key] = child_state[key]

        # f = file(save_path, "w")
        # pickle.dump(state, f)
        pass

    def get_state(self):
        """Override me"""
        return {}

    def apply_state(self, state_obj):
        """Override me"""
        pass

    def print_test_run_status(self):
        # TODO: Break me up
        ch = self.curses_helper
        win = ch.window
        win_h, win_w = ch.get_size()
        start_y = self.CONTENT_Y
        col1_w = int(win_w / 2)
        col2_w = int(win_w / 3)
        col2_start = win_w - col2_w - ch.padcols * 2

        y = start_y
        x = ch.padcols

        thread_count = len(self.test_threads)
        s = 'Active Tests ({0})'.format(thread_count)
        if thread_count > 0:
            cpair = ch.yellow_cpair
        else:
            cpair = ch.highlight_cpair

        win.addstr(y, x, s, cpair)
        y += 1
        if len(self.test_threads) > 0:
            for thread in self.test_threads:
                s = ellipsify(thread.get_target_file(), col1_w)
                ch.addnstr(y, x, s, col1_w)
                y += 1
        else:
            win.addstr(y, x, 'None')

        self.print_queued_tests(
            start_y=start_y,
            max_y=self.CONTENT_MAX_Y - 1,
            start_x=col2_start,
            max_x=col2_start + col2_w)

        y = self.CONTENT_Y + self.max_parallel_count + 2
        x = ch.padcols
        s = 'Test Results '
        if self.in_filename_search_mode():
            s += '(Test Files)'
        elif self.in_testname_search_mode():
            s += '(Individual Tests)'
        win.addstr(y, x, s, ch.highlight_cpair)
        y += 1

        run, passed, failed = self.log.get_all_loop_tests(
            test_names=self.in_testname_search_mode())
        fail_count = len(failed)
        pass_count = len(passed)
        run_count = len(run)

        win.addstr(y, x, '[Loop {0}] '.format(self.log.get_loop()))
        win.addstr('[')
        win.addstr('{0} passes'.format(pass_count), ch.green_cpair)
        win.addstr(' / ')

        fail_cpair = ch.red_cpair
        if fail_count == 0:
            fail_cpair = ch.green_cpair
        win.addstr('{0} failures '.format(fail_count), fail_cpair)

        win.addstr('] ')
        win.addstr('[Elapsed: {0}] '.format(self.time_passed()))

        # Progress meter
        y += 1
        x = ch.padcols
        progress_meter_length = col1_w - 6
        percent_complete = float(run_count) / float(self.total_test_count)
        progress = int(percent_complete * progress_meter_length)
        if progress == progress_meter_length:
            progress -= 1
        progress_str = '['
        for i in range(progress_meter_length):
            if i < progress:
                char = '-'
            elif i == progress:
                char = '>'
            else:
                char = ' '
            progress_str += char
        progress_str += '] '
        progress_str += '{0}%'.format((int(percent_complete * 100)))
        ch.addstr(y, x, progress_str)

        # Failures
        y += 2
        self.print_failed_tests(
            start_y=y,
            start_x=ch.padcols,
            max_x=ch.padcols + col1_w)

    def print_queued_tests(self, start_y, max_y, start_x, max_x):
        ch = self.curses_helper
        win = ch.window
        y = start_y
        x = start_x
        col_w = max_x - start_x

        s = '<-- Queued Tests ({0})'.format(len(self.pending_test_indices))
        ch.addstr(y, x, s, ch.highlight_cpair)
        y += 1

        if len(self.pending_test_indices) > 0:
            for idx in self.pending_test_indices:
                if self.in_filename_search_mode():
                    name = self.filtered_files[idx]
                elif self.in_testname_search_mode():
                    test_data = self.tests_by_index[idx]
                    name = test_data['test_name']
                s = ellipsify('- ' + name, col_w - 1)
                ch.addstr(y, x, s)
                y += 1
                if y == max_y:
                    ch.addstr(y, x, '[...]')
                    break
        else:
            ch.addstr(y, x, 'None')

    def print_failed_tests(self, start_y, start_x, max_x):
        ch = self.curses_helper
        win = ch.window
        y = start_y
        x = start_x
        col_w = max_x - start_x

        if self.in_filename_search_mode():
            all_failed = self.log.get_all_failed_files()
            all_failed_count = len(all_failed)
            heading = 'Failed Files'
        elif self.in_testname_search_mode():
            all_failed = self.log.get_all_failed_tests()
            all_failed_count = 0
            for filename in all_failed:
                all_failed_count += len(all_failed[filename])
            heading = 'Failed Tests'

        if all_failed_count > 0:
            ch.addstr(y, x, heading, ch.red_cpair)
            win.addstr(' (cumulative)')
            s = '[Passes/Fails]'
            ch.addstr(y, col_w - len(s), s, ch.highlight_cpair)

            start_idx, page_count = self.determine_pages(
                total_line_count=all_failed_count,
                available_lines=self.CONTENT_MAX_Y - 1 - start_y,
                current_page=self.failure_list_page)

            y += 1
            i = 0
            for failure in all_failed:
                i += 1
                x = ch.padcols

                if self.in_filename_search_mode():
                    if i < start_idx:
                        continue

                    head, tail = os.path.split(failure)
                    head_s = '{0}/'.format(ellipsify(
                        head,
                        col_w - len(tail) - 8))

                    ch.addstr(y, x, head_s)
                    win.addstr(tail, ch.red_cpair)

                    filename = failure
                    test_name = None

                elif self.in_testname_search_mode():
                    failed_test_names = all_failed[failure]
                    if i + len(failed_test_names) < start_idx:
                        continue

                    filename = failure['filename']
                    test_name = failure['test_name']

                    file_s = ellipsify(filename, col2_w - 7)
                    test_name_s = '- ' + ellipsify(test_name, col2_w - 10)

                    ch.addstr(y, x, file_s)
                    y += 1
                    ch.addstr(y, x, test_name_s, ch.red_cpair)

                pass_count = str(self.log.get_cumulative_pass_count(
                    filename=filename,
                    test_name=test_name))

                fail_count = str(self.log.get_cumulative_fail_count(
                    filename=filename,
                    test_name=test_name))

                x = col_w - len(pass_count) - len(fail_count) - 3
                win.addstr(y, x, '[')
                win.addstr(pass_count, ch.green_cpair)
                win.addstr('/')
                win.addstr(fail_count, ch.red_cpair)
                win.addstr(']')

                y += 1
                if y == self.CONTENT_MAX_Y - 1:
                    break
            s = '<Page {0}/{1}>'.format(
                self.failure_list_page + 1,
                page_count)
            x = int(ch.padcols + col_w / 2 - len(s) / 2)
            win.addstr(y, x, s, ch.highlight_cpair)

    def determine_pages(self, total_line_count, available_lines, current_page):
        fails_per_page = int(available_lines * .8)
        page_count = int(total_line_count / fails_per_page) + 1
        start_idx = int(current_page * fails_per_page)
        return (start_idx, page_count)

    def poll_running_tests(self):
        if self.can_parallel is True and self.run_parallel is True:
            max_threads = self.max_parallel_count
        else:
            max_threads = 1

        while (len(self.test_threads) < max_threads and
            len(self.pending_test_indices) > 0):
                for func in self.test_setup_funcs:
                    func()

                idx = self.pending_test_indices.pop(0)
                if self.in_filename_search_mode():
                    target_file = self.filtered_files[idx]
                    test_name = None

                elif self.in_testname_search_mode():
                    test_data = self.tests_by_index[idx]
                    target_file = test_data['filename']
                    test_name = test_data['test_name']

                cmd = self.build_command(
                    target_file=target_file,
                    test_name=test_name)

                thread = TestThread(
                    self.command_path,
                    target_file,
                    test_name,
                    cmd,
                    self.test_callback)
                self.test_threads.append(thread)
                thread.start()

        if len(self.test_threads) > 0:
            self.test_poller = Timer(self.test_poll_delay,
                self.poll_running_tests)
            self.test_poller.start()
        elif self.loop_mode is True:
                all_failed = self.log.get_all_failed_files()
                if len(all_failed) > 0:
                    failed_indices = []
                    for f in all_failed:
                        failed_indices.append(self.filtered_files.index(f))
                    self.selected_filtered_test_indices = failed_indices
                    self.run_tests()
        self.draw(clear=True)

    def run_tests(self):
        self.view_mode = TEST_STATUS_VIEW_MODE
        self.log.new_loop()
        if not self.start_time:
            self.start_time = datetime.datetime.now()

        sfti = self.selected_filtered_test_indices
        if len(sfti) > 0:
            self.pending_test_indices = list(sfti)
        else:
            if self.in_filename_search_mode():
                self.pending_test_indices = range(len(self.filtered_files))
            elif self.in_testname_search_mode():
                self.pending_test_indices = range(len(self.tests_by_index))
        self.total_test_count = len(self.pending_test_indices)
        self.poll_running_tests()
        self.draw()

    def test_callback(
        self,
        test_thread,
        target_file,
        test_name,
        output,
        errors):
            self.test_threads.remove(test_thread)

            combined = output + errors
            with open(self.output_log_f, 'a+') as f:
                f.write(combined)
            self.handle_output(target_file, test_name, combined)
            self.draw(clear=True)

    def build_command(self, target_file, test_name=None):
        prefixes = ' '.join(self.command_prefixes)
        suffixes = ' '.join(self.command_suffixes)
        return '{0} {1}'.format(
            self.command,
            ' '.join([prefixes, target_file, suffixes]))

    def handle_output(self, target_file, test_name, output):
        self.update_log(target_file, self.strip_ansi(output),
            test_name=test_name)

    def update_log(self, target_file, output):
        # Override me
        pass

    def find_all_tests(self):
        if not self.can_search_in_files:
            return

        self.all_tests = {}
        for filepath in self.all_files:
            with open(filepath, 'r') as open_f:
                test_names = self.find_tests_in_file(open_f.read())
                self.all_tests[filepath] = test_names
        self.filtered_tests = self.all_tests

    def find_tests_in_file(self, file_content):
        pass

    def find_all_files(self):
        self.all_files = []
        total_file_count = 0
        count_all_files = False
        if not self.file_extensions or len(self.file_extensions) == 0:
            count_all_files = True

        for path in self.search_paths:
            for root, subFolders, files in os.walk(path):
                count = 0
                for f in files:
                    include = False
                    if count_all_files is True:
                        include = True
                    else:
                        for e in self.file_extensions:
                            e_len = -1 * len(e)
                            if f[e_len:] == e:
                                include = True
                                break
                    if include is True:
                        self.all_files.append(os.path.join(root, f))


    def queue_all(self):
        self.filtered_files = list(self.all_files)
        self.draw()

    def filter_files(self, filter_str):
        filter_str = filter_str.lower()
        self.temp_selection_indices = []

        if self.search_mode == FILENAME_SEARCH_MODE:
            self.filtered_files = []
            for f in self.all_files:
                if filter_str in f.lower():
                    self.filtered_files.append(f)
        elif self.search_mode == TESTNAME_SEARCH_MODE:
            self.filtered_tests = {}
            for filename in self.all_tests:
                matches = []
                for test_name in self.all_tests[filename]:
                    if filter_str in test_name.lower():
                        matches.append(test_name)
                if len(matches) > 0:
                    self.filtered_tests[filename] = matches
        self.draw()

    def view_raw_output(self):
        output = self.read_output_file()

        self.end_curses()
        print output
        if len(output) == 0:
            print('No output (yet).')
        print
        inp = raw_input('<Hit enter to return>')
        self.init_curses()
        self.draw()

    def read_output_file(self):
        with open(self.output_log_f, 'r') as f:
            return f.read()

    def validate(self):
        """Make sure necessary paths exist."""
        paths = self.search_paths.copy()
        paths.add(self.command_path)
        for p in paths:
            if not os.path.isdir(p):
                self._bad('Bad path: ' + p)
                self.quit()

    def resume_state(self, failure_state=False):
        state_obj = self.load_state(failure_state=failure_state)
        if not state_obj:
            return False
        self.target_files = state_obj.get('files')
        self.verbose = state_obj.get('verbose')
        if hasattr(self, 'apply_state'):
            self.apply_state(state_obj)
        return True

    def finish(self):
        pass

    def sigint_handler(self, signal, frame):
        self.quit()

    def resize_handler(self, signal, frame):
        self.check_window_size()
        self.end_curses()
        self.init_curses()
        self.draw()

    def end_curses(self):
        logger.debug('end_curses')
        curses.nocbreak()
        try:
            self.curses_helper.window.keypad(0)
        except AttributeError, e:
            pass

        curses.echo()
        curses.endwin()
        self.curses_helper = None

    def quit(self, exception=None, error_msg=None):
        try:
            self.test_poller.cancel()
        except AttributeError, e:
            pass

        tc = len(self.test_threads)
        if tc > 0:
            print(('NOTE: {0} test threads still active. ' +
                'They will terminate shortly.\n').format(tc))
        for thread in self.test_threads:
            thread.stop()

        with open(self.output_log_f, 'r') as f:
            print(f.read())

        if error_msg is not None:
            print
            print(error_msg)
        else:
            print('Test output log: ' + str(self.output_log_f))
            print('Adios.')
        sys.exit()

class NoseRunner(EasyRunner):
    def __init__(self):
        super(EasyRunner, self).__init__()
        self.add_file_extension('.py')
        self.can_search_in_files = True
        self.test_name_re = re.compile(r'def ([Tt]est\w+)\(')
        self.pass_re = re.compile(r'OK \(\d+ test(s?), \d+ assertion(s?)\)',
            re.MULTILINE)

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
        self.pass_re = re.compile(r'[1-9]+ passed\)')
        self.can_search_in_files = False

        self.add_file_extension('.feature')
        self.can_parallel = True
        self.run_parallel = True
        self.max_parallel_count = 3

    def get_state(self):
        return {
            'tags': self.tags
        }

    def apply_state(self, state_obj):
        self.tags = state_obj.get('tags')
        self.add_tag_suffix()

    def update_log(self, feature_file, output, test_name=None):
        if len(output) == 0:
            logger.debug('update_log: no output!')
            return
        passed = self.pass_re.search(output)
        if passed is not None:
            self.log.log_pass(feature_file)
        else:
            self.log.log_failure(feature_file)

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
            self.quit()

        self.add_prefix('-c ' + self.config_file)
        self.config_parts.insert(0, self.config_file)


    def finish(self):
       pass

if __name__ == '__main__':
    if '--nose' in sys.argv:
        runner = NoseRunner()
        runner.run()
