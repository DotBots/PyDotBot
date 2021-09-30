import toml
import threading

class BaseConfig(dict):
    """BaseConfig access to dictionary attributes"""
    lock = threading.Lock()

    def __init__(self, data):
        if isinstance(data, str):
            _dict = toml.load(data)
        elif isinstance(data, dict):
            _dict = data
        else:
            raise ValueError("Bad data type.")
        super().__init__(_dict)

    def __getattr__(self, *args):
        with self.lock:
            val = dict.get(self, *args)
            return BaseConfig(val) if type(val) is dict else val

    def __setattr__(self, *args, **kwargs):
        with self.lock:
            dict.__setitem__(*args, **kwargs)

    def __delattr__(self, *args, **kwargs):
        with self.lock:
            dict.__delitem__(*args, **kwargs)