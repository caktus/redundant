#!/usr/bin/env python3
import sys, os, re
from contextlib import contextmanager
import difflib
import optparse
import configparser
import fnmatch

config = configparser.ConfigParser()
config.read(".debtcollectorrc")

INDENT_SIZE = int(config['report'].get('indent', 4))
_CUR_INDENT = 0
RE_MODULE_FUNC = re.compile(r'^def (\w+)\(')
DIFF_DELTA_MAX = float(config['report'].get('diff-delta-max', 0.5))
DIFF_LENGTH_MIN = float(config['report'].get('diff-line-min', 0.5))
EXTENSIONS = [line.strip() for line in config['files']['extensions'].split('\n') if line]
EXCLUDE_GLOBS = [line.strip() for line in config['files']['exclude-path'].split('\n') if line]

dupskipfile = open('.debtcollectordupskip', 'w')
def add_dup_skip(filepath):
    print(filepath, file=dupskipfile)
    dupskipfile.flush()
DUP_SKIP = [f.strip() for f in open('.debtcollectordupskip') if f]

SEEN_FUNCTIONS = {}

@contextmanager
def indent():
    global _CUR_INDENT
    _CUR_INDENT += INDENT_SIZE
    yield
    _CUR_INDENT -= INDENT_SIZE
_print = print
def print(*args, **kwargs):
    global dotting
    if dotting:
        dotting = False
        _print("", end="\n")
    _print((" "*_CUR_INDENT) + str(args[0]), *args[1:], **kwargs)
dotting = False
def dot():
    global dotting
    dotting = True
    _print(".", end="")
    sys.stdout.flush()

def record_function(funcname, filepath):
    print("function:", funcname)
    seen_at = SEEN_FUNCTIONS.setdefault(funcname, [])
    with indent():
        dup_count = 0
        for other_filepath in seen_at:
            print("duplicate name in:", other_filepath)
            dup_count += 1
        if dup_count:
            print("duplicate total:", dup_count)
    seen_at.append(filepath)

seen_files = {}
def record_file(filepath):
    filerec = seen_files.setdefault(filepath, {
        "linecount": 0,
    })
    print("file:", filepath)
    ext = os.path.splitext(filepath)[1]
    with indent():
        try:
            for line in open(filepath):
                filerec['linecount'] += 1
                try:
                    line_proc = globals()['process_file_line_' + ext]
                except KeyError:
                    continue
                else:
                    line_proc(filepath, filerec, line)
        except UnicodeDecodeError:
            print("[!] Unicode Decode Error")
        # print(filerec['linecount'], "lines")

def process_file_line_py(filepath, filerec, line):
    if RE_MODULE_FUNC.match(line):
        funcname = RE_MODULE_FUNC.match(line).groups()[0]
        record_function(funcname, filepath)

def check_file_ext(filename):
    for ext in EXTENSIONS:
        if filename.endswith(ext):
            return True
    return False

def main(argv):
    parser = optparse.OptionParser()
    parser.add_option('-e', '--extension', dest="extension", action="append")
    (options, args) = parser.parse_args()
    if options.extension:
        EXTENSIONS[:] = options.extension

    for root, dirs, filenames in os.walk(".", topdown=True):
        if 'migrations' in dirs:
            dirs.remove('migrations')
        for filename in filenames:
            if check_file_ext(filename):
                filepath = os.path.join(root, filename)
                is_excluded = False
                for excpattern in EXCLUDE_GLOBS:
                    if fnmatch.fnmatch(filepath, excpattern):
                        is_excluded = True
                        break
                if not is_excluded:
                    record_file(filepath)

    print("Analyzing files for diverged duplicates...")
    for afilepath in seen_files:
        if afilepath in DUP_SKIP:
            continue
        if seen_files[afilepath].get('exact_dup'):
            continue
        print("duplicates for", afilepath)
        found_duplicates = False
        with indent():
            for bfilepath in seen_files:
                if afilepath == bfilepath:
                    continue
                elif os.path.splitext(afilepath)[1] != os.path.splitext(bfilepath)[1]:
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
                    diff = [
                        line for line in
                        difflib.ndiff(list(open(afilepath)), list(open(bfilepath)))
                        if not line.startswith(' ')
                    ]
                except UnicodeDecodeError:
                    continue
                delta = len(diff)
                match = delta / (seen_files[afilepath]['linecount'] + seen_files[bfilepath]['linecount'])
                if delta == 0:
                    print("exact:", bfilepath)
                    seen_files[bfilepath].setdefault('exact_dup', afilepath)
                    found_duplicates = True
                elif match <= DIFF_DELTA_MAX:
                    print("near:", bfilepath, "(%0.2f)" % (match,))
                    found_duplicates = True
            if not found_duplicates:
                print("none. adding to skip list.")
                add_dup_skip(afilepath)
        # dot()

if __name__ == '__main__':
    main(sys.argv)
