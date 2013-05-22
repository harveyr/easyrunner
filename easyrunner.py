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
from logging.handlers import RotatingFileHandler

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
LOGFORMATTER = logging.Formatter('[%(name)s:%(lineno)d] - %(levelname)s - %(message)s')

# LOGHANDLER = logging.StreamHandler()
# LOGHANDLER.setFormatter(LOGFORMATTER)
# LOGHANDLER.setLevel(logging.DEBUG)
# logger.addHandler(LOGHANDLER)

log_f = tempfile.mkstemp(suffix='.log', prefix='easyrunner-')[1]
FILEHANDLER = RotatingFileHandler(
    log_f,
    maxBytes=1000000,
    backupCount=3)
FILEHANDLER.setFormatter(LOGFORMATTER)
FILEHANDLER.setLevel(logging.DEBUG)
logger.addHandler(FILEHANDLER)

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
            curses.init_pair(9, curses.COLOR_BLACK, curses.COLOR_WHITE)

            self.padcols = 1
            self.pad = ' '.join('' for i in range(self.padcols + 1))

            self.default_cpair = curses.color_pair(1)
            self.heading_cpair = curses.color_pair(2)
            self.highlight_cpair = curses.color_pair(3)
            self.green_cpair = curses.color_pair(4)
            self.red_cpair = curses.color_pair(5)
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
            logger.debug('curses error ' + str(e))

    def addnstr(self, y, x, s, n, pair=None):
        if pair is None:
            pair = self.default_cpair
        try:
            self.window.addnstr(y, x, s, n, pair)
        except curses.error, e:
            logger.debug('curses error ' + str(e))

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
                nlines = int(win_h / 1.5)
            if ncols is None:
                ncols = int(win_w / 1.5)
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
    def __init__(self, command_path, target_file, command, callback):
        threading.Thread.__init__(self)
        self.command_path = command_path
        self.target_file = target_file
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
        # if errors:
        #     print 'errors'
        #     print errors

        self.callback(self, self.target_file, output, errors)

    def stop(self):
        self.p.terminate()

    def get_target_file(self):
        return self.target_file

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
    pending_test_files = []
    search_file_page = 0
    total_test_count = None
    use_all_files = False
    start_time = None
    input_buffer = ''

    all_output = ''
    output_log_f = 'easyrunner.log'

    test_setup_funcs = []

    can_parallel = False
    run_parallel = False
    max_parallel_count = 3
    test_threads = []

    cli_args = None
    cli_handlers = []
    config_parts = []

    verbose = False
    loop_mode = False
    loop_count = 0
    loop_tests_complete = 0

    pass_count_re = None
    fail_count_re = None
    test_log = {
        'files': {},
        'passes': 0,
        'failures': 0,
        'failed_tests': [],
        'failed_files': {}
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

        self.init_curses()

        self.output_log_f = os.path.join(self.command_path, self.output_log_f)
        with open(self.output_log_f, 'w') as f:
            pass

        win_h, win_w = self.curses_helper.get_size()
        self.PROMPT_Y = win_h - 2
        self.CONFIG_Y = win_h - 1
        self.CONTENT_Y = 4
        self.CONTENT_MAX_Y = win_h - 5

        self.commands = [
            {
                'command': ':a',
                'description': 'Queue all available test files.',
                'func': self.queue_all
            },
            {
                'command': ':l',
                'description': 'Toggle loop mode. If on, all failed tests will be run indefinity, with pass/fail tallies printed. This is helpful for finding flaky tests.',
                'func': self.toggle_loop_mode
            },
            {
                'command': ':p <#>',
                'description': 'Set parallel count (if available). For example: ":p 3".',
                'func': self.set_parallel_count
            },
            {
                'command': ':c',
                'description': 'Clear current settings (reset).',
                'func': self.reset
            },
            {
                'command': ':go',
                'description': 'Run the tests.',
                'func': self.run_tests
            },
            {
                'command': ':?',
                'description': 'Get help.',
                'func': self.print_help
            },
        ]

    def init_curses(self):
        self.curses_helper = CursesHelper()

    def is_running(self):
        return len(self.test_threads) > 0

    def has_run(self):
        return self.loop_count > 0

    def draw(self, clear=False):
        if not self.curses_helper:
            return

        ch = self.curses_helper
        win_h, win_w = ch.get_size()

        if clear is True:
            ch.window.clear()
        else:
            ch.window.erase()

        self.draw_window()
        if self.has_run():
            self.print_test_run_status()
        else:
            self.print_test_scope()
        self.draw_config()
        self.print_padding()
        self.print_feedback()
        self.print_prompt()
        self.curses_helper.window.refresh()

    def print_padding(self):
        ch = self.curses_helper
        for y in range(self.CONTENT_Y, self.CONTENT_MAX_Y):
            for x in range(0, ch.padcols):
                ch.addstr(y, x, ' ')

    def reset(self):
        self.find_all_files()
        self.filtered_files = []
        self.selected_filtered_test_indices = []
        self.pending_test_files = []
        self.total_test_count = None
        self.start_time = None
        self.loop_count = 0
        self.loop_tests_complete = 0
        self.feedback_str = ''
        self.draw()

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

    def add_cli_handler(self, func):
        self.cli_handlers.append(func)

    def set_verbose(self, verbose):
        self.verbose = bool(verbose)

    def toggle_verbosity(self):
        self.verbose = not self.verbose

    def toggle_parallel_mode(self):
        self.run_parallel = not self.run_parallel

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

    def log_failure(self, target_file, test_name=None):
        self.test_log['failures'] += 1

        if test_name is None:
            test_name = target_file

        if test_name not in self.test_log['failed_tests']:
            self.test_log['failed_tests'].append(test_name)

        if target_file in self.test_log['failed_files']:
            fail_dict = self.test_log['failed_files'][target_file]
        else:
            fail_dict = {
                'failed_tests': [],
                'fail_count': 0,
                'pass_count': 0
            }

        fail_dict['fail_count'] += 1
        if target_file not in self.test_log['failed_files']:
            self.test_log['failed_files'][target_file] = fail_dict

    def log_pass(self, target_file):
        self.test_log['passes'] += 1
        if target_file in self.test_log['failed_files']:
            self.test_log['failed_files'][target_file]['pass_count'] += 1

    def run(self):
        signal.signal(signal.SIGINT, self.sigint_handler)
        signal.signal(signal.SIGWINCH, self.resize_handler)

        self.reset()
        self.queue_all()

        self.draw()
        self.get_user_input()

    def in_command_mode(self):
        return len(self.input_buffer) > 0 and self.input_buffer[0] == ':'

    def print_prompt(self):
        ch = self.curses_helper
        win_h, win_w = ch.get_size()
        y = win_h - 2
        x = ch.padcols
        s = '> ' + self.input_buffer
        ch.window.addstr(y, x, s)
        curses.curs_set(2)
        ch.window.clrtoeol()

    def get_user_input(self):
        win = self.curses_helper.window
        win_h, win_w = self.curses_helper.get_size()

        self.print_prompt()
        curses.cbreak()
        try:
            inp = self.curses_helper.window.getkey()
        except curses.error, e:
            logger.debug('curses input error: ' + str(e))
            self.get_user_input()
            return

        logger.debug('inp: "{0}"'.format(inp))

        if inp == 'KEY_BACKSPACE':
            if len(self.input_buffer) > 0:
                self.input_buffer = self.input_buffer[:-1]
            self.draw()
            inp = ''

        if inp == ' ':
            pass
        elif inp == 'KEY_RESIZE':
            logger.debug('resize!')
            h, w = win.getmaxyx()
            curses.resize_term(h, w)
            self.draw()
        elif inp == 'KEY_UP':
            logger.debug('KEY_UP')
            if self.search_file_page > 0:
                self.search_file_page -= 1
            self.draw()
        elif inp == 'KEY_DOWN':
            self.search_file_page += 1
            self.draw()
        elif inp in ['KEY_LEFT', 'KEY_RIGHT', 'KEY_SF']:
            pass
        elif inp == ':':
            self.input_buffer = ':'
            self.feedback_str = '[Command Mode (:? for a list)] '
            self.draw()
        elif len(self.input_buffer) > 0 and self.input_buffer[0] == ':':
            if inp == '\n':
                self.command_feedback(execute=True)
            else:
                self.input_buffer += inp
                self.command_feedback(execute=False)
        elif inp == '\n':
            if self.input_buffer == '':
                self.run_tests()
            else:
                self.input_buffer = ''
        else:
            self.input_buffer += inp
            logger.debug('len(self.input_buffer): ' + str(len(self.input_buffer)))
            if len(self.input_buffer) > 0:
                self.feedback_str = 'Filter string: ' + self.input_buffer
            else:
                self.feedback_str = '<Enter> to run targeted files, type some letters to search, or :? for help'
            self.filter_files(self.input_buffer)
            self.draw()

        self.last_input = inp
        self.get_user_input()

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

    def print_feedback(self):
        if not self.feedback_str:
            return

        ch = self.curses_helper
        win = ch.window
        win_h, win_w = ch.get_size()
        y = win_h - 3
        x = ch.padcols
        win.addnstr(y, x, self.feedback_str, win_w - x - 5, ch.green_cpair)
        ch.window.clrtoeol()

    def print_debug(self, debug_str):
        s = 'Debug: {0} ({1})'.format(debug_str, datetime.datetime.now())
        y = 3
        x = self.curses_helper.padcols
        self.curses_helper.addstr(y, x, s)

    def print_title(self):
        print self._header('\n----- ' + self.title + ' -----\n')

    def print_test_scope(self):
        """Print the target files and related parameters (verbosity, etc.)"""
        ch = self.curses_helper
        win = ch.window
        win_h, win_w = ch.get_size()
        y = self.CONTENT_Y
        x = ch.padcols
        col1_w = col2_w = int(win_w / 2) - 10
        col2_start = win_w - col2_w - 4

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

    def draw_config(self):
        ch = self.curses_helper
        win = ch.window
        win_h, win_w = ch.get_size()
        y = self.CONFIG_Y

        try:
            win.addstr(y, ch.padcols, 'Config: ')
            win.addstr('[parallel ')
            if self.run_parallel is True:
                win.addstr(str(self.max_parallel_count), ch.highlight_cpair)
            else:
                win.addstr('off')
            win.addstr('] ')

            win.addstr('[loop ')
            if self.loop_mode is True:
                win.addstr('on', ch.green_cpair)
            else:
                win.addstr('off')
            win.addstr(']')

            logs1 = '[Debug: {0}] '.format(ellipsify(str(log_f), 30))
            logs2 = '[Output: {0}]'.format(ellipsify(self.output_log_f, 30))
            # x = win_w - 4 - max(len(logs1), len(logs2))
            x = win_w - len(logs1) - len(logs2) - 2
            win.addstr(y, x, logs1)
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

    def command_feedback(self, execute=False):
        if not self.in_command_mode():
            return

        s = self.input_buffer
        logger.debug('command_feedback(): s == ' + s)
        if len(s) > 1 and is_int(s[1]):
            try:
                nums = [i - 1 for i in self.parse_number_input()]
                self.feedback_str = '[Enter] Queue test files: ' + str(nums)
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
                if s[:2] == cmd['command'][:2]:
                    self.feedback_str = '[Enter] ' + cmd['description']
                    self.draw()
                    if execute is True:
                        func = cmd['func']
                        func()
        if execute is True:
            self.input_buffer = ''
            self.feedback_str = ''
            self.draw()

    def print_help(self):

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

        ch = self.curses_helper
        panel_key = 'help_panel'
        help_panel = ch.get_panel(panel_key)
        win = help_panel.window()
        win_h, win_w = win.getmaxyx()
        padcols = 2

        win.clear()

        s = 'Usage'
        y = 1
        x = int(win_w / 2 - len(s) / 2)
        win.addstr(y, x, s, ch.heading_cpair)
        y += 1

        for part in intro:
            win.addstr(y, padcols, part['heading'], ch.highlight_cpair)
            y += 1
            y = add_wrapped(y, padcols, part['body'], win_w - padcols * 2)
            y += 1

        s = 'Commands'
        x = int(win_w / 2 - len(s) / 2)
        win.addstr(y, x, s, ch.heading_cpair)
        y += 1

        for cmd in self.commands:
            x = padcols
            try:
                win.addstr(y, x, cmd['command'], ch.highlight_cpair)
            except curses.error, e:
                pass
            x = 12
            for line in textwrap.wrap(cmd['description'], win_w - 10):
                try:
                    win.addstr(y, x, line)
                except curses.error, e:
                    pass
                y += 1

        s = '<Hit any key to close>'
        x = int(win_w / 2 - len(s) / 2)
        win.addstr(win_h - 2, x, s, ch.highlight_cpair)

        win.border()
        win.refresh()
        help_panel.top()
        help_panel.show()

        curses.curs_set(0)
        inp = win.getkey()
        help_panel.hide()
        self.draw()
        curses.curs_set(2)

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
        if failure_state is False:
            save_path = self.get_state_save_path()
            files = self.target_files
        else:
            save_path = self.get_failure_save_path()
            files = self.test_log['failed_files']

        state = {
            'files': files,
            'verbose': self.verbose
        }

        child_state = self.get_state()
        for key in child_state:
            state[key] = child_state[key]

        f = file(save_path, "w")
        pickle.dump(state, f)

    def get_state(self):
        """Override me"""
        return {}

    def apply_state(self, state_obj):
        """Override me"""
        pass

    def print_test_run_status(self):
        ch = self.curses_helper
        win = ch.window
        win_h, win_w = ch.get_size()
        start_y = self.CONTENT_Y
        col1_w = int(win_w / 2)
        col2_w = int(win_w / 3)
        col2_start = win_w - col2_w - ch.padcols * 2

        y = start_y
        x = ch.padcols

        win.addstr(y, x, 'Active Tests', ch.highlight_cpair)
        y += 1
        if len(self.test_threads) > 0:
            for thread in self.test_threads:
                s = ellipsify(thread.get_target_file(), col1_w)
                ch.addnstr(y, x, s, col1_w)
                y += 1
        else:
            win.addstr(y, x, 'None')

        tests_run_count = len(self.test_log['files'])
        fail_count = self.test_log['failures']

        y = start_y
        x = col2_start
        s = '<-- {0} Queued Tests'.format(len(self.pending_test_files))
        ch.addstr(y, x, s, ch.highlight_cpair)

        y += 1
        if len(self.pending_test_files) > 0:
            for f in self.pending_test_files:
                s = ellipsify(f, col2_w)
                ch.addnstr(y, x, s, col2_w)
                y += 1
                if y == self.CONTENT_MAX_Y - 1:
                    ch.addstr(y, x, '[...]')
                    break
        else:
            ch.addstr(y, x, 'None')

        y = self.CONTENT_Y + self.max_parallel_count + 2
        x = ch.padcols
        logger.debug('x: ' + str(x))
        win.addstr(y, x, 'Test Results', ch.highlight_cpair)
        y += 1

        win.addstr(y, x, '[')
        cpair = ch.red_cpair
        if fail_count == 0:
            cpair = ch.green_cpair
        s = '{0} failures '.format(fail_count)
        win.addstr(s, cpair)
        win.addstr('/ {0} run '.format(self.loop_tests_complete))
        win.addstr('/ {0} total] '.format(self.total_test_count))
        win.addstr('[Elapsed: {0}] '.format(self.time_passed()))
        win.addstr('[Loop: {0}]'.format(self.loop_count))

        if self.loop_count == 1:
            # Progress meter
            y += 1
            x = ch.padcols
            progress_meter_length = col1_w - 6
            percent_complete = float(tests_run_count) / float(self.total_test_count)
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

        failures = self.test_log['failed_files']
        logger.debug('failures: ' + str(failures))
        y += 2

        if len(failures) > 0:
            ch.addstr(y, ch.padcols, 'Failures', ch.red_cpair)
            s = '[Passes/Fails]'
            ch.addstr(y, col1_w - len(s), s, ch.highlight_cpair)
            y += 1
            for f, data in failures.items():
                head, tail = os.path.split(f)
                head_s = '{0}/'.format(
                    ellipsify(head, col1_w - len(tail) - 10))

                pass_count = str(data['pass_count'])
                fail_count = str(data['fail_count'])

                x = ch.padcols
                ch.addstr(y, x, head_s)
                win.addstr(tail, ch.red_cpair)
                x = col1_w - len(pass_count) - len(fail_count) - 3
                win.addstr(y, x, '[')
                win.addstr(pass_count, ch.green_cpair)
                win.addstr('/')
                win.addstr(fail_count, ch.red_cpair)
                win.addstr(']')

                y += 1
                if y == self.CONTENT_MAX_Y - 1:
                    ch.addstr(y, x, '[...]')
                    break

    def poll_running_tests(self):
        # self.print_debug('polling ...')
        if self.can_parallel is True and self.run_parallel is True:
            max_threads = self.max_parallel_count
        else:
            max_threads = 1

        while (len(self.test_threads) < max_threads and
            len(self.pending_test_files) > 0):
                for func in self.test_setup_funcs:
                    func()
                target_file = self.pending_test_files.pop(0)
                thread = TestThread(
                    self.command_path,
                    target_file,
                    self.build_command(target_file),
                    self.test_callback)
                self.test_threads.append(thread)
                thread.start()

        if len(self.test_threads) > 0:
            self.test_poller = Timer(3, self.poll_running_tests)
            self.test_poller.start()
        else:
            if self.loop_mode is True:
                if len(self.test_log['failed_files']) > 0:
                    failed_indices = []
                    for f in self.test_log['failed_files']:
                        failed_indices.append(self.filtered_files.index(f))
                    self.selected_filtered_test_indices = failed_indices
                    self.run_tests()
        logger.debug('self.test_log[failed_files]: ' + str(self.test_log['failed_files']))
        self.draw(clear=True)

    def run_tests(self):
        self.loop_count += 1
        self.loop_tests_complete = 0
        if not self.start_time:
            self.start_time = datetime.datetime.now()

        sfti = self.selected_filtered_test_indices
        if len(sfti) > 0:
            self.pending_test_files = [self.filtered_files[i] for i in sfti]
        else:
            self.pending_test_files = list(self.filtered_files)
        self.total_test_count = len(self.pending_test_files)
        self.poll_running_tests()

    def test_callback(self, test_thread, target_file, output, errors):
        self.test_threads.remove(test_thread)
        self.loop_tests_complete += 1

        combined = output + errors
        with open(self.output_log_f, 'a+') as f:
            f.write(combined)
        self.handle_output(target_file, combined)
        self.draw(clear=True)

    def build_command(self, target_file):
        prefixes = ' '.join(self.command_prefixes)
        suffixes = ' '.join(self.command_suffixes)
        return '{0} {1}'.format(
            self.command,
            ' '.join([prefixes, target_file, suffixes]))

    def handle_output(self, target_file, output):
        self.test_log['files'][target_file] = output
        self.update_log(target_file, output)

    def update_log(self, target_file, output):
        # Override me
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
        self.filtered_files = []
        filter_str = filter_str.lower()
        for f in self.all_files:
            if filter_str in f.lower():
                self.filtered_files.append(f)
        self.draw()

    def validate(self):
        """Make sure necessary paths exist."""
        paths = self.search_paths.copy()
        paths.add(self.command_path)
        for p in paths:
            if not os.path.isdir(p):
                self._bad('Bad path: ' + p)
                self.quit()

    def process_cli_args(self):
        for a in self.cli_args[1:]:
            self._process_cli_arg(a)

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
        self.end_curses()
        self.init_curses()
        self.draw()

    def end_curses(self):
        curses.nocbreak()
        self.curses_helper.window.keypad(0)
        curses.echo()
        curses.endwin()
        self.curses_helper = None

    def quit(self, exception=None):
        self.end_curses()
        try:
            self.test_poller.cancel()
        except AttributeError, e:
            pass

        for thread in self.test_threads:
            thread.stop()

        # with open(log_f, 'r') as f:
        #     print(f.read())

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

    def update_log(self, feature_file, output):
        if len(output) == 0:
            return

        outcome = self.outcome_re.findall(output)
        if len(outcome) > 0:
            self.test_log['files'][feature_file] = outcome

        failed = self.fail_re.search(output)
        if failed is not None:
            self.log_failure(feature_file)
        else:
            self.log_pass(feature_file)

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
            self.quit()

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
        runner = NoseRunner()
        runner.set_cli_args(sys.argv)
        runner.run()
