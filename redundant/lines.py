from collections import namedtuple

from .utils import memoize

# Data structures

# Canonical Line
# Includes a full line and its source file and location
# Does not strip line contents
Line = namedtuple("Line", "filepath linenum line stripped")
lines_by_length = {}
lines_by_filepath = {}


def record_line(filepath, linenum, line):
    stripped = line.strip()
    line_rec = Line(filepath, linenum, line, stripped)
    lines_by_length.setdefault(len(stripped), []).append(line_rec)
    lines_by_filepath.setdefault(filepath, []).append(line_rec)


@memoize
def lines_in_length_range(min_length, max_length):
    """Finds all lines in a length range.

    Expects `lines` is already sorted by length.
    """
    assert min_length <= max_length
    if max_length == 0:
        return iter([])

    for length in range(min_length, max_length + 1):
        try:
            for line in lines_by_length[length]:
                yield line
        except KeyError:
            pass

@memoize
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


@memoize
def score_line_diff(diff):
    if not diff:
        return 0
    same_chars = 0.0
    diff_chars = 0.0
    for entry in diff:
        if isinstance(entry, tuple):
            left, right = entry
            diff_chars += (len(left) + len(right)) / 2
        else:
            same_chars = len(entry)
    return same_chars / (same_chars + diff_chars)


@memoize
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

def find_similar_lines(line_files, line_rec, min_score=0.25):
    line = line_rec.stripped
    search_min_length = int(len(line) - int(len(line) * 0.1))
    search_max_length = int(len(line) + int(len(line) * 0.1))

    for possible_line in lines_in_length_range(search_min_length, search_max_length):
        if possible_line != line:
            score = score_line_diff(line_diff(line, possible_line.stripped))
            if score >= min_score:

                for filepath, linenum in line_files[possible_line.stripped]['files'].items():
                    if filepath != line_rec.filepath:
                        # print("%s: %s" % (filepath, linenum))
                        yield (possible_line, score)
