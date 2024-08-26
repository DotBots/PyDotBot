import requests
from lakers import EdhocResponder, AuthzAutenticator
from dataclasses import dataclass
from typing import Optional

from dotbot.logger import LOGGER
from dotbot.models import DotBotModel

logger = LOGGER.bind(context=__name__)
CRED_REQUEST_PATH = ".well-known/lake-authz/cred-request"


def fetch_credential_remotely(loc_w: str, id_cred_i: bytes) -> bytes:
    url = f"{loc_w}/{CRED_REQUEST_PATH}"
    res = requests.post(url, data=id_cred_i)
    if res.status_code == 200:
        return res.content
    else:
        raise Exception(f"Error fetching credential {kid} at {loc_w}")


@dataclass
class PendingEdhocSession:
    dotbot: DotBotModel
    responder: EdhocResponder
    authz_authenticator: AuthzAutenticator
    loc_w: Optional[str] = None
    c_r: Optional[int] = None
