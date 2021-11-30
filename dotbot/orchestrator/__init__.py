import threading
import pkg_resources
from dotbot.datastructures import Singleton
from dotbot.datastructures.config import BaseConfig

class OrchestratorConfig(BaseConfig, metaclass=Singleton):
    '''
    Class to manage the configuration of Orchestrator. 
    Configuration is contained in a file that is located in this same folder. 
    '''
    def __init__(self):
        super().__init__(pkg_resources.resource_filename(__name__, "default_config.toml"))