
import axios from 'axios';
import logger from './logger';
const log = logger.child({module: 'Rest'});

export const API_URL = "http://localhost:8000";

export const apiFetchDotbots = async () => {
  log.info("Fetching dotbots from API");;
  return await axios.get(
    `${API_URL}/controller/dotbots`,
  ).then(res => res.data);
}

export const apiFetchMapSize = async () => {
  log.info("Fetching map size from API");;
  return await axios.get(
    `${API_URL}/controller/map_size`,
  ).then(res => res.data);
}

export const apiUpdateMoveRaw = async (address, application, left_x, left_y, right_x, right_y) => {
  log.info(`Setting move raw for dotbot ${address} with values (${left_x}, ${left_y}, ${right_x}, ${right_y})`);
  const command = { left_x: parseInt(left_x), left_y: parseInt(left_y), right_x: parseInt(right_x), right_y: parseInt(right_y) };
  return await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/move_raw`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiUpdateRgbLed = async (address, application, red, green, blue) => {
  log.info(`Setting RGB LED for dotbot ${address} with values (${red}, ${green}, ${blue})`);
  const command = { red: red, green: green, blue: blue };
  return await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/rgb_led`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiUpdateWaypoints = async (address, application, waypoints, threshold) => {
  log.info(`Setting waypoints for dotbot ${address} with command (${JSON.stringify(waypoints)}, ${threshold})`);
  return await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/waypoints`,
    {threshold: threshold, waypoints: waypoints},
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiClearPositionsHistory = async (address) => {
  log.info(`Clearing positions history for dotbot ${address}`);
  return await axios.delete(
    `${API_URL}/controller/dotbots/${address}/positions`,
    { headers: { 'Content-Type': 'application/json' } }
  );
}
