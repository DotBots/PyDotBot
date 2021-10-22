import pkg_resources
from dotbot.datastructures import Singleton
from dotbot.datastructures.config import BaseConfig

class DemoConfig(BaseConfig, metaclass=Singleton):
    def __init__(self):
        super().__init__(pkg_resources.resource_filename(__name__, "default_config.toml"))
