import traceback

def format_buf(buf):
    """
    Format a bytelist into an easy-to-read string. For example:

    ``[0xab,0xcd,0xef,0x00] -> '(4B) ab-cd-ef-00'``
    """
    return '({0:>2}B) {1}'.format(len(buf), '-'.join(["%02x" % b for b in buf]))

def format_string_buf(buf):
    return '({0:>2}B) {1}'.format(len(buf), '-'.join(["%02x" % ord(b) for b in buf]))

def format_critical_message(error):
    return_val = []
    return_val += ['Error:']
    return_val += [str(error)]
    return_val += ['\ncall stack:\n']
    return_val += [traceback.format_exc()]
    return_val += ['\n']
    return_val = '\n'.join(return_val)
    return return_val

def format_crash_message(thread_name, error):
    return_val = []
    return_val += ['\n']
    return_val += ['======= crash in {0} ======='.format(thread_name)]
    return_val += [format_critical_message(error)]
    return_val = '\n'.join(return_val)
    return return_val