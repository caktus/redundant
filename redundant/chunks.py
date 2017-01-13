from . import lines
from .config import config

class Chunk(object):

    def __init__(self, filepath, startline, endline=None):
        self.filepath = filepath
        self.startline = startline
        self.endline = endline or startline

    def __len__(self):
        return self.endline + 1 - self.startline

    def similar_to(self, other):
        self_line = self.startline
        other_line = other.startline


class ChunkPair(object):

    def __init__(self, left, right):
        self.left = left
        self.right = right


def extend_chunks(start1, start2, start_score, min_score, min_lines):
    from redundant import indent
    length = 2

    if start1.filepath == start2.filepath:
        return

    try:
        next1 = lines.lines_by_filepath[start1.filepath][start1.linenum + 1]
        next2 = lines.lines_by_filepath[start2.filepath][start2.linenum + 1]
    except IndexError:
        return
    scores = [start_score]
    scores.append(lines.score_line_diff(lines.line_diff(next1.stripped, next2.stripped)))

    def cur_score():
        return sum(scores) / len(scores)

    while cur_score() >= min_score:
        try:
            next1 = lines.lines_by_filepath[next1.filepath][next1.linenum + 1]
            next2 = lines.lines_by_filepath[next2.filepath][next2.linenum + 1]
        except IndexError:
            return
        scores.append(lines.score_line_diff(lines.line_diff(next1.stripped, next2.stripped)))

        length += 1

    if length >= min_lines:
        print(
            cur_score(),
            start1.filepath, start1.linenum,
            start2.filepath, start2.linenum,
            "(%s lines)" % (length,)
        )
        for i in range(length):
            print("    ",
                lines.lines_by_filepath[start1.filepath][start1.linenum + i].line,
            end="")
        print("-----")
        for i in range(length):
            print("    ",
                lines.lines_by_filepath[start2.filepath][start2.linenum + i].line,
            end="")

    # with indent():
    #     print(start1.stripped)
    #     print(next1.stripped)
    #     print("")
    #     print(start2.stripped)
    #     print(next2.stripped)


def find_similar_chunks(file_data, line_files, min_line, max_line):
    from redundant import indent, print, spin_cursor

    MIN_SIM_LINE = float(config['chunks'].get('min-sim-line', 0.5))
    starting_lines = {}
    count = 0

    print("Analyzing for similar chunks within files...")
    for line in lines.lines_in_length_range(min_line, max_line):
        count += 1
        spin_cursor(count)

        if line.stripped not in starting_lines:
            for i, simline in enumerate(lines.find_similar_lines(line_files, line, MIN_SIM_LINE)):
                starting_lines.setdefault(line, []).append(simline)
                spin_cursor(len(starting_lines))
            # if line.stripped in starting_lines:
                # print("%03d %s:%d %s" % (len(starting_lines[line.stripped]), line.filepath, line.linenum, line.stripped))

    print("Found %d similar lines to start chunks..." % (len(starting_lines),))

    # Now try to extend these into chunks...
    # somehow...
    MIN_LENGTH = int(config['chunks'].get('min-length', 10))
    for line, simlines in starting_lines.items():
        for (simline, score) in simlines:
            extend_chunks(line, simline, score, score - 0.2, MIN_LENGTH)
    return
    for line, simlines in starting_lines.items():
        for (simline, score) in simlines:
            if line.filepath == simline.filepath and line.linenum == simline.linenum:
                continue
            try:
                ln_line = file_data[line.filepath]['lines'][line.linenum - 1]
            except IndexError:
                print("[ERROR]", line.filepath, line.linenum)
                raise
            try:
                rn_line = file_data[simline.filepath]['lines'][simline.linenum - 1]
            except IndexError:
                print("[ERROR]", simline.filepath, simline.linenum)
                raise
            rn_score = lines.score_line_diff(lines.line_diff(line.stripped, simline.stripped))

            print("[%s:%d]" % (line.filepath, line.linenum))
            print(line.line.strip('\n'))
            #print(ln_line.strip('\n'))
            print("[%s:%d] (%0.2f)" % (simline.filepath, simline.linenum, rn_score))
            print(simline.line.strip('\n'))
            #print(rn_line.strip('\n'))
            print("")
