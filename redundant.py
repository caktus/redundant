import sys, os, re
from contextlib import contextmanager
import difflib
import optparse
import configparser
import fnmatch

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
(options, args) = parser.parse_args()
if options.extension:
    EXTENSIONS = options.extension
PRINT_OUTPUT = [None]
if options.output:
    PRINT_OUTPUT.append(open(options.output, 'w'))

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
    kwargs = dict(kwargs)
    for out in PRINT_OUTPUT:
        kwargs['file'] = out
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
        "lines": readfile(filepath),
    })
    print("file:", filepath)
    ext = os.path.splitext(filepath)[1]
    with indent():
        try:
            for line in readfile(filepath):
                filerec['linecount'] += 1
                try:
                    line_proc = globals()['process_file_line_' + ext.strip('.')]
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

def readfile(filepath):
    lines = []
    for line in open(filepath, 'rb'):
        lines.append(line.decode('utf8', 'ignore'))
    return lines

def main():
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

    line_total = 0
    for filerec in seen_files.values():
        line_total += len(filerec['lines'])
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
        with indent():
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
                # elif not found_duplicates:
                #     dot()
            if not found_duplicates:
                print("none. adding to skip list.")
                add_dup_skip(afilepath)

if __name__ == '__main__':
    main()
