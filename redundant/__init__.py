import sys, os, re
from contextlib import contextmanager
import difflib
import optparse
import configparser
import fnmatch
import importlib
from bisect import insort_left, bisect_left
from collections import namedtuple

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
                do_print(header, indent=(i * INDENT_SIZE))
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

line_sorted = []
line_files = {}
longest_line_length = 0
def readfile(filepath):
    global longest_line_length
    lines = []
    for bline in open(filepath, 'rb'):
        tline = bline.decode('utf8', 'ignore')
        tline_stripped = tline.strip()
        longest_line_length = max(longest_line_length, len(tline_stripped))
        tline_i = bisect_left(line_sorted, (len(tline_stripped), tline_stripped))
        try:
            if line_sorted[tline_i][1] != tline_stripped:
                line_sorted.insert(tline_i, (len(tline_stripped), tline_stripped))
        except IndexError:
            line_sorted.insert(tline_i, (len(tline_stripped), tline_stripped))
        line_files.setdefault(tline_stripped, set()).add(filepath)
        lines.append(tline)
    return lines

def lines_in_length_range(min_length, max_length):
    assert min_length <= max_length
    if max_length == 0:
        return iter([""])
    i_start = 0
    i_end = len(line_sorted) - 1
    l_start = line_sorted[i_start][0]
    l_end = line_sorted[i_end][0]
    f_start = False
    f_end = False

    while l_start < min_length and not f_start:
        i_start += 1024
        l_start = line_sorted[i_start][0]
        while l_start >= min_length and not f_start:
            i_start -= 1
            l_start = line_sorted[i_start][0]
            if l_start < min_length:
                f_start = True

    while l_end > max_length and not f_end:
        i_end -= 1024
        try:
            l_end = line_sorted[i_end][0]
        except IndexError:
            i_end = i_start + 1
            l_end = line_sorted[i_end][0]
        while l_end <= min_length and not f_end:
            i_end += 1
            l_end = line_sorted[i_end][0]
            if l_end > max_length:
                f_end = True

    for i in range(i_start, i_end + 1):
        yield line_sorted[i][1]

def line_diff(line1, line2):
    """Constructs a representation of the difference between two lines and a score.

    Given the two lines:
        for i in range(i_start, i_end + 1):
        for i in range(start, end):

    line_diff() will produce a sequence of substrings that are the same and differ between
    the two lines, like this:

        [
            "for i in range(",
            ("i_start", "start"),
            ", ",
            ("i_end + 1", "end"),
            "):",
        ]
    """
    line1 = list(line1)
    cur1 = 0
    line2 = list(line2)
    cur2 = 0

    def next1():
        nonlocal cur1
        c = line1[cur1]
        cur1 += 1
        return c

    def next2():
        nonlocal cur2
        c = line2[cur2]
        cur2 += 1
        return c

    def findnext(line, cur, char):
        # track other chars to find the closest the strings reconverge
        others = {}
        # do not advance cursor yet, just locate
        for i in range(cur, len(line) - 1):
            if char == line[i]:
                return i, others
            else:
                others.setdefault(line[i], i - cur)
        # found the end of the line
        return (None, others)

    buf_same = []
    buf_line1 = []
    buf_line2 = []

    results = []

    while cur1 < len(line1) and cur2 < len(line2):
        char1 = next1()
        char2 = next2()

        # If the lines continue to be similar, add to the Same Buffer
        if char1 == char2:
            buf_same.append(char1)
            continue
        elif buf_same:
            results.append(''.join(buf_same))
            buf_same[:] = []

        # If they differ here, we want to read into Line 1 Buffer OR Line 2 Buffer
        # whichever has the shortest distance to the other line's next character
        nextchar1, otherchars1 = findnext(line1, cur1, char2)
        nextchar2, otherchars2 = findnext(line2, cur2, char1)
        # Did we find the end of either line?

        next_char_max_dists = {}
        same_chars = set(otherchars1) & set(otherchars2)
        if same_chars:
            for c in same_chars:
                next_char_max_dists[c] = max(otherchars1[c], otherchars2[c])
            next_char_max_dists_sorted = list(sorted((d, c) for (c, d) in next_char_max_dists.items()))
            closest_next_char_dist, closest_next_char = next_char_max_dists_sorted[0]
            # Now we only want to advance this far

            if nextchar1 is None:
                nextchar1 = closest_next_char_dist
            else:
                nextchar1 = min(closest_next_char_dist, nextchar1)
            if nextchar2 is None:
                nextchar2 = closest_next_char_dist
            else:
                nextchar2 = min(closest_next_char_dist, nextchar2)

        # Neither gap is very small, so we'll treat this as a divergent segment
        # this means we read both into their own buffers up to the new cursor positions
        buf_line1.append(char1)
        buf_line2.append(char2)
        while cur1 < len(line1) and (nextchar1 is None or cur1 <= nextchar1):
            buf_line1.append(next1())
        while cur2 < len(line2) and (nextchar2 is None or cur2 <= nextchar2):
            buf_line2.append(next2())
        # We assume the cursors now point to the same character
        results.append((''.join(buf_line1), ''.join(buf_line2)))
        buf_line1[:] = []
        buf_line2[:] = []

    if buf_same:
        results.append(''.join(buf_same))
    return results

def score_line_diff(diff):
    same_chars = 0.0
    diff_chars = 0.0
    for entry in diff:
        if isinstance(entry, tuple):
            left, right = entry
            diff_chars += (len(left) + len(right)) / 2
        else:
            same_chars = len(entry)
    return same_chars / (same_chars + diff_chars)

def levenshtein(s1, s2):
    if len(s1) < len(s2):
        return levenshtein(s2, s1)

    # len(s1) >= len(s2)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1 # j+1 instead of j since previous_row and current_row are one character longer
            deletions = current_row[j] + 1       # than s2
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

def find_similar_lines(line, orig_filepath):
    max_levenshtein = int(len(line) * 0.1)
    search_min_length = int(len(line) - max_levenshtein)
    search_max_length = int(len(line) + max_levenshtein)

    with indent(next(iter(line_files[line])) + ": " + line):
        for i, possible_line in enumerate(lines_in_length_range(search_min_length, search_max_length)):
            if i % 4096 == 0:
                dot()
            if possible_line != line:
                possible_lev = score_line_diff(line_diff(line, possible_line))
                if possible_lev <= max_levenshtein and possible_lev > 0.5:
                    with indent("%s (%0.2f)" % (possible_lev, possible_line)):
                        for filepath in line_files[possible_line]:
                            if filepath != orig_filepath:
                                print(filepath)

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

    if options.similar_lines:
        for line in lines_in_length_range(30, longest_line_length):
            find_similar_lines(line, next(iter(line_files)))

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
            # print("duplicates for", afilepath)
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
                    # elif not found_duplicates:
                    #     dot()
                if not found_duplicates:
                    # print("none. adding to skip list.")
                    add_dup_skip(afilepath)
