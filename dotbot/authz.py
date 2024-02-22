import requests

from dotbot.logger import LOGGER

logger = LOGGER.bind(context=__name__)
LOC_W_CRED_REQUEST = "http://localhost:18000/.well-known/lake-authz/cred-request/"


def fetch_credential(id_cred_i):
    if len(id_cred_i) > 1:
        return id_cred_i
    elif len(id_cred_i) == 1:
        cred = fetch_credential_remotely(id_cred_i[0])
        if cred:
            return cred
        else:
            raise Exception("Error fetching credential at {LOC_W_CRED_REQUEST}")
    else:
        logger.error("No valid credential found")
        return


def fetch_credential_remotely(kid: int) -> bytes:
    id_cred_i = bytes.fromhex(f"a10441{format(kid, '02x')}")
    res = requests.post(LOC_W_CRED_REQUEST, data=id_cred_i)
    if res.status_code == 200:
        return res.content
    else:
        logger.error("Error fetching credential", status_code=res.status_code)
