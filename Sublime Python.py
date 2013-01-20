import os
import threading
import subprocess
from collections import defaultdict

import sublime
import sublime_plugin

"""
TODO

* class variables, globals and instance vars don't work
* add configuration: ignore directories, python location
* find better name for plugin

"""

PYTHON = '/usr/bin/python2.7'
APPDIR = os.path.abspath(os.path.split(__file__)[0])

def error(message):
    sublime.message_dialog("Sublime Python\n\n" + message)

class SymbolManager(object):
    THREAD_NAME = "c50d5e10-60de-11e2-bcfd-0800200c9a66"

    def __init__(self):
        self._symbols = []
        self._lock = threading.RLock()
        self._thread = None
        self._progress = None
        self.loaded = False

    def get_symbols(self):
        with self._lock:
            return self._symbols[:]

    def scan_all(self):
        options = []
        for directory in sublime.active_window().folders():
            options.append('-d')
            options.append(directory)
        def callback(symbols):
            self._symbols = symbols
            self.loaded = True
        self._scan(options, callback)

    def scan_file(self, filename):
        def callback(symbols):
            self._symbols = [sym for sym in self._symbols if sym[1] != filename]
            self._symbols.extend(symbols)
        self._scan(['-f', filename], callback)

    def _scan(self, options, callback):
        old_threads = [t for t in threading.enumerate() if t.name == self.THREAD_NAME]
        if old_threads:
            return
        self._progress = 0
        self._show_progress()
        self._thread = threading.Thread(
            target=lambda: self._scan_thread(options, callback), 
            name=self.THREAD_NAME
        )
        self._thread.daemon = True
        self._thread.start()

    def _scan_thread(self, options, callback):
        symbols = []
        def add_symbol(symbol, filename, line):
            symbols.append((symbol, filename, line))
        process = subprocess.Popen([PYTHON, '-u', '%s/symbols.py' % APPDIR] + options, 
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while True:
            line = process.stdout.readline()
            if not line:
                break
            eval(line, dict(
                progress=self._update_progress,
                symbol=add_symbol
            ))
        self._update_progress(None)
        with self._lock:
            callback(symbols)

    def _update_progress(self, percent):
        self._progress = percent

    def _show_progress(self):
        if self._progress is not None:
            sublime.status_message("scanning python symbols (%d%% done)..." % self._progress)
            sublime.set_timeout(self._show_progress, 200)
        else:
            sublime.status_message("")

class SublimePythonGotoDialogCommand(sublime_plugin.WindowCommand):
    def run(self):
        manager = MANAGERS[self.window.id()]
        if not manager.loaded:
            error("Loading symbols, please try in a few moments...")
            manager.scan_all()
            return
        symbols = sorted(manager.get_symbols())
        symbols = [[sym[0], '%s:%d' % (sym[1], sym[2])]  for sym in symbols]
        if not symbols:
            error("No symbols found.")
        def goto_symbol(index):
            if index == -1:
                return
            self.window.open_file(symbols[index][1]+':0', sublime.ENCODED_POSITION)
        self.window.show_quick_panel(symbols, goto_symbol)

class SublimePythonGotoWordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        manager = MANAGERS[self.view.window().id()]
        if not manager.loaded:
            error("Loading symbols, please try in a few moments...")
            manager.scan_all()
            return
        word = self.view.substr(self.view.word(self.view.sel()[0]))
        if not word:
            return
        symbols = manager.get_symbols()
        matches = [[sym[0], '%s:%d' % (sym[1], sym[2])] for sym in symbols if word == sym[0]]
        def goto_match(index):
            if index == -1:
                return
            self.view.window().open_file(matches[index][1]+':0', sublime.ENCODED_POSITION)
        if len(matches) > 1:
            self.view.window().show_quick_panel(matches, goto_match)
        elif matches:
            goto_match(0)
        else:
            error("Can't find definition for '%s'." % word)

class SublimePythonScanCommand(sublime_plugin.WindowCommand):
    def run(self):
        MANAGERS[sublime.active_window()].scan_all()

class SublimePythonEventListener(sublime_plugin.EventListener):
    def __init__(self):
        super(SublimePythonEventListener, self).__init__()
        self.prev_folders = defaultdict(list)

    def on_load(self, view):
        window_id = view.window().id()
        manager = MANAGERS[window_id]
        if not manager.loaded or self.prev_folders[window_id] != sublime.active_window().folders():
            self.prev_folders[window_id] = sublime.active_window().folders()
            manager.scan_all()
        else:
            manager.scan_file(view.file_name())

    def on_post_save(self, view):
        manager = MANAGERS[view.window().id()]
        manager.scan_file(view.file_name())

MANAGERS = defaultdict(SymbolManager)