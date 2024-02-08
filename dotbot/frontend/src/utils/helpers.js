import geodist from "geodist";
import logger from './logger';

const log = logger.child({module: 'helpers'});

export const lh2_distance = (lh21, lh22) => {
  return Math.sqrt(((lh21.x - lh22.x) ** 2) + ((lh21.y - lh22.y) ** 2));
};

export const gps_distance = (gps1, gps2) => {
  const _gps1 = {lat: gps1.lat, lon: gps1.longitude}
  const _gps2 = {lat: gps2.lat, lon: gps2.longitude}
  return geodist(_gps1, _gps2, {exact: true, unit: 'meters'});
};

export const loadLocalPin = () => {
  const pin = parseInt(localStorage.getItem("pin"));
  const date = parseInt(localStorage.getItem("date"));

  if (isNaN(pin) || isNaN(date)) {
    log.debug("No pin found in local storage");
    return null;
  }

  if (Date.now() - date > 1000 * 60 * 20) {
    log.debug("Pin found in local storage, but it's too old");
    return null;
  }

  log.debug(`Pin ${pin} found in local storage`);

  return pin;
};

export const saveLocalPin = (pin) => {
  log.debug(`Saving pin ${pin} to local storage`);
  localStorage.setItem("pin", pin);
  localStorage.setItem("date", Date.now());
};
