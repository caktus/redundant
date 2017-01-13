import sys
import os
import re
import time
from contextlib import contextmanager
import difflib
import optparse
import configparser
import fnmatch
import importlib
from bisect import insort_left, bisect_left
from collections import namedtuple

from .lines import line_diff, score_line_diff, lines_in_length_range, record_line
from . import chunks

config = configparser.ConfigParser()
config.read(".redundantrc")
config.setdefault('report', {})
config.setdefault('files', {})

INDENT_SIZE = int(config['report'].get('indent', 4))
_CUR_INDENT = 0
RE_MODULE_FUNC = re.compile(r'^def (\w+)\(')
DIFF_DELTA_MAX = float(config['report'].get('diff-delta-max', 0.5))
DIFF_LENGTH_MIN = float(config['report'].get('diff-line-min', 0.5))
EXTENSIONS = [line.strip() for line in config['files'].get('extensions', '').split('\n') if line]
EXCLUDE_GLOBS = [line.strip() for line in config['files'].get('exclude-path', '').split('\n') if line]
DUP_IGNORE_LINE_RE = [re.compile(line.strip()) for line in config['files'].get('dup-ignore-line-re', '').split('\n') if line]

dupskipfile = open('.redundantdupskip', 'a')
def add_dup_skip(filepath):
    _print(filepath, file=dupskipfile)
    dupskipfile.flush()
DUP_SKIP = [f.strip() for f in open('.redundantdupskip') if f]

SEEN_FUNCTIONS = {}

parser = optparse.OptionParser()
parser.add_option('-e', '--extension', dest="extension", action="append")
parser.add_option('-o', '--output', dest="output")
parser.add_option('', '--similar-lines', dest="similar_lines", action="store_true")
parser.add_option('', '--similar-chunks', dest="similar_chunks", action="store_true")
parser.add_option('', '--similar-files', dest="similar_files", action="store_true")
(options, args) = parser.parse_args()
if options.extension:
    EXTENSIONS = options.extension
PRINT_OUTPUT = [None]
if options.output:
    PRINT_OUTPUT.append(open(options.output, 'w'))

_INDENT_HEADER = []
@contextmanager
def indent(header=None):
    global _CUR_INDENT
    global _INDENT_HEADER
    _CUR_INDENT += INDENT_SIZE
    _INDENT_HEADER.append(header)
    yield
    _INDENT_HEADER.pop()
    _CUR_INDENT -= INDENT_SIZE
_print = print
def print(*args, **kwargs):
    global dotting
    global _INDENT_HEADER
    if dotting:
        dotting = False
        _print("", end="\n")
    def do_print(*args, indent=None, **kwargs):
        kwargs = dict(kwargs)
        if indent is None:
            indent = _CUR_INDENT
        for out in PRINT_OUTPUT:
            kwargs['file'] = out
            _print((" "*indent) + str(args[0]), *args[1:], **kwargs)
    if _INDENT_HEADER:
        for i, header in enumerate(_INDENT_HEADER):
            if header:
                for header_line in header.split('\n'):
                    do_print(header_line, indent=(i * INDENT_SIZE))
                _INDENT_HEADER[i] = None
    do_print(*args, **kwargs)
dotting = False
def dot():
    global dotting
    dotting = True
    _print(".", end="")
    sys.stdout.flush()

def record_function(funcname, filepath):
    # print("function:", funcname)
    seen_at = SEEN_FUNCTIONS.setdefault(funcname, [])
    with indent("function: %s (from %s)"  % (funcname, filepath)):
        dup_count = 0
        for other_filepath in seen_at:
            print("duplicate name in:", other_filepath)
            dup_count += 1
        if dup_count:
            print("duplicate total:", dup_count)
    seen_at.append(filepath)

_default_filetype = namedtuple("filetype", "ext")
def get_filetype(filepath):
    ext = os.path.splitext(filepath)[1]
    try:
        mod = importlib.import_module('redundant.filetype_%s' % ext[1:])
        mod.ext = ext
    except ImportError:
        mod = _default_filetype(ext=ext)
    return mod

seen_files = {}
def record_file(filepath):
    filerec = seen_files.setdefault(filepath, {
        "linecount": 0,
        "lines": readfile(filepath),
    })
    # print("file:", filepath)
    filetype = get_filetype(filepath)
    with indent("file: " + filepath):
        try:
            for line in readfile(filepath):
                filerec['linecount'] += 1
                try:
                    line_proc = filetype.process_file_line
                except AttributeError:
                    break
                else:
                    line_proc(filepath, filerec, line)
        except UnicodeDecodeError:
            print("[!] Unicode Decode Error")
        # print(filerec['linecount'], "lines")

def check_file_ext(filename):
    for ext in EXTENSIONS:
        if filename.endswith(ext):
            return True
    return False

line_files = {}
longest_line_length = 0
def readfile(filepath):
    global longest_line_length
    if filepath in seen_files:
        return seen_files[filepath]['lines']
    lines = []
    for linenum, bline in enumerate(open(filepath, 'rb'), 1):
        tline = bline.decode('utf8', 'ignore')
        tline_stripped = tline.strip()
        longest_line_length = max(longest_line_length, len(tline_stripped))
        record_line(filepath, linenum, tline)
        line_files.setdefault(tline_stripped, {}).setdefault('files', {})[filepath] = linenum
        lines.append(tline)
    return lines

def report_similar_lines(line, orig_filepath):
    max_levenshtein = int(len(line) * 0.1)
    search_min_length = int(len(line) - max_levenshtein)
    search_max_length = int(len(line) + max_levenshtein)

    one_file = next(iter(line_files[line]['files']))

    with indent(one_file + ": " + line.stripped):
        for i, line_rec in enumerate(lines_in_length_range(search_min_length, search_max_length)):
            if i % 4096 == 0:
                dot()
            possible_line = line_rec.stripped
            if possible_line != line.stripped:
                possible_lev = score_line_diff(line_diff(line.stripped, possible_line))
                if possible_lev > 0.5:
                    with indent("%s (orig)\n%s (%0.2f)" % (line.stripped, possible_line, possible_lev)):
                        for filepath, linenum in line_files[possible_line]['files'].items():
                            if filepath != orig_filepath:
                                print("%s: %s" % (filepath, linenum))


def spinning_cursor():
    while True:
        for cursor in '|/-\\':
            yield cursor


spinner = spinning_cursor()
_current_status = ""


def spin_cursor(status):
    global _current_status
    _current_status = "%s %s" % (next(spinner), status)
    sys.stdout.write(_current_status)
    sys.stdout.flush()
    # time.sleep(0.1)
    sys.stdout.write('\b' * len(_current_status))


def main():
    print("Analyzing files...")
    count = 0
    for root, dirs, filenames in os.walk(".", topdown=True):
        if 'migrations' in dirs:
            dirs.remove('migrations')
        for i, filename in enumerate(filenames):
            if check_file_ext(filename):
                count += 1
                spin_cursor(str(count))
                filepath = os.path.join(root, filename)
                is_excluded = False
                for excpattern in EXCLUDE_GLOBS:
                    if fnmatch.fnmatch(filepath, excpattern):
                        is_excluded = True
                        break
                if not is_excluded:
                    record_file(filepath)

    line_total = 0
    for filerec in seen_files.values():
        line_total += len(filerec['lines'])

    if options.similar_lines:
        for line in lines_in_length_range(30, longest_line_length):
            report_similar_lines(line, next(iter(line_files)))

    if options.similar_chunks:
        chunks.find_similar_chunks(seen_files, line_files, 30, longest_line_length)

    if options.similar_files:
        print("Read %d lines of %d files." % (line_total, len(seen_files)))
        print("Analyzing files for diverged duplicates...")
        if DUP_SKIP:
            with indent():
                print("(skipping %d files from .redundantdupskip)" % (len(DUP_SKIP),))
        for afilepath in sorted(seen_files):
            if afilepath in DUP_SKIP:
                continue
            if seen_files[afilepath].get('exact_dup'):
                continue
            print("duplicates for", afilepath)
            found_duplicates = False
            with indent("duplicates for " + afilepath):
                for bfilepath in sorted(seen_files):
                    if afilepath == bfilepath:
                        continue
                    elif os.path.splitext(afilepath)[1] != os.path.splitext(bfilepath)[1]:
                        continue
                    elif bfilepath in seen_files[afilepath].get('near_files', []):
                        continue
                    alength = seen_files[afilepath]['linecount']
                    blength = seen_files[bfilepath]['linecount']
                    try:
                        lengthdelta = min(alength, blength) / max(alength, blength)
                    except ZeroDivisionError:
                        continue
                    else:
                        if lengthdelta < DIFF_LENGTH_MIN:
                            continue
                    try:
                        diff = []
                        for line in difflib.unified_diff(readfile(afilepath), readfile(bfilepath)):
                            # Don't count lines shared
                            if line.startswith(' '):
                                continue
                            # Don't count empty lines
                            if not line.strip():
                                continue
                            # Don't count ignored lines
                            for r in DUP_IGNORE_LINE_RE:
                                if r.match(line):
                                    continue
                            diff.append(line)
                    except UnicodeDecodeError:
                        if not found_duplicates:
                            dot()
                        continue
                    delta = len(diff)
                    match = delta / (seen_files[afilepath]['linecount'] + seen_files[bfilepath]['linecount'])
                    if delta == 0:
                        print("exact:", bfilepath)
                        seen_files[bfilepath].setdefault('exact_dup', afilepath)
                        found_duplicates = True
                    elif match <= DIFF_DELTA_MAX:
                        print("near:", bfilepath, "(%0.2f)" % (match,))
                        seen_files[bfilepath].setdefault('near_files', []).append(afilepath)
                        found_duplicates = True
                    elif not found_duplicates:
                        dot()
                if not found_duplicates:
                    print("none. adding to skip list.")
                    add_dup_skip(afilepath)
