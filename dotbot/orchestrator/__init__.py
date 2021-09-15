import pkg_resources
from dotbot.datastructures.config import BaseConfig

class OrchestratorConfig(BaseConfig):
    pass

class DefaultConfig(OrchestratorConfig):
    def __init__(self):
       super().__init__(pkg_resources.resource_filename(__name__, "default_config.toml"))