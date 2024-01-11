import hkdf from "futoin-hkdf";
import * as jose from 'jose'

import { ProtocolVersion } from "./constants";

import logger from './logger';
const log = logger.child({module: 'crypto'});

export const deriveKey = (pin) => {
  const length = 32;
  const salt = '';
  const info = `secret_key_${ProtocolVersion}`;
  const hash = 'SHA-256';

  return hkdf(`${pin}`, length, {salt, info, hash});
};

export const deriveTopic = (pin) => {
  const length = 16;
  const salt = '';
  const info = `secret_topic_${ProtocolVersion}`;
  const hash = 'SHA-256';

  // Topic is encoded in url safe base64
  return Buffer.from(hkdf(`${pin}`, length, {salt, info, hash})).toString("base64").replace(/\+/g,'-').replace(/\//g,'_');
};

export const encrypt = async (message, key) => {
  const jwe = await new jose.CompactEncrypt(
    new TextEncoder().encode(message),
  )
    .setProtectedHeader({ alg: 'dir', enc: 'A256GCM' })
    .encrypt(key)
  return jwe;
};

export const decrypt = async (message, key) => {
  try {
    const decrypted = await jose.compactDecrypt(message, key)
    return new TextDecoder().decode(decrypted.plaintext);
  } catch (error) {
    log.debug(`${error.name}: ${error.message}`);
    return;
  }
};
