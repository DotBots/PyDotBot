import toml

class BaseConfig(dict):
    """BaseConfig access to dictionary attributes"""
    def __init__(self, data):
        if isinstance(data, str):
            _dict = toml.load(data)
        elif isinstance(data, dict):
            _dict = data
        else:
            raise ValueError("Bad data type.")
        super().__init__(_dict)

    def __getattr__(self, *args):
        val = dict.get(self, *args)
        return BaseConfig(val) if type(val) is dict else val

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__