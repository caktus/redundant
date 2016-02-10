import redundant

def process_file_line(filepath, filerec, line):
    if redundant.RE_MODULE_FUNC.match(line):
        funcname = redundant.RE_MODULE_FUNC.match(line).groups()[0]
        redundant.record_function(funcname, filepath)
