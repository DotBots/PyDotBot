import axios from 'axios';
import logger from './logger';

import { DotBot, AreaSize, BackgroundMap, MoveRawData, RgbLedData, LH2Position, GpsPosition } from '../types';

const log = logger.child({ module: 'Rest' });

export const API_URL = "http://localhost:8000";

export const apiFetchDotbots = async (): Promise<DotBot[]> => {
  log.info("Fetching dotbots from API");
  return await axios.get<DotBot[]>(
    `${API_URL}/controller/dotbots`,
  ).then(res => res.data);
};

export const apiFetchMapSize = async (): Promise<AreaSize> => {
  log.info("Fetching map size from API");
  return await axios.get<AreaSize>(
    `${API_URL}/controller/map_size`,
  ).then(res => res.data);
};

export const apiFetchBackgroundMap = async (): Promise<BackgroundMap> => {
  log.info("Fetching background map from API");
  return await axios.get<BackgroundMap>(
    `${API_URL}/controller/background_map`,
  ).then(res => {
    log.info(`Received background map data from API (${res.data.data.length} chars)`);
    return res.data;
  });
}

export const apiUpdateMoveRaw = async (
  address: string,
  application: number,
  left_x: number,
  left_y: number,
  right_x: number,
  right_y: number
): Promise<void> => {
  log.info(`Setting move raw for dotbot ${address} with values (${left_x}, ${left_y}, ${right_x}, ${right_y})`);
  const command: MoveRawData = {
    left_x: parseInt(String(left_x)),
    left_y: parseInt(String(left_y)),
    right_x: parseInt(String(right_x)),
    right_y: parseInt(String(right_y)),
  };
  await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/move_raw`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
};

export const apiUpdateRgbLed = async (
  address: string,
  application: number,
  red: number,
  green: number,
  blue: number
): Promise<void> => {
  log.info(`Setting RGB LED for dotbot ${address} with values (${red}, ${green}, ${blue})`);
  const command: RgbLedData = { red, green, blue };
  await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/rgb_led`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
};

export const apiUpdateWaypoints = async (
  address: string,
  application: number,
  waypoints: (LH2Position | GpsPosition)[],
  threshold: number
): Promise<void> => {
  log.info(`Setting waypoints for dotbot ${address} with command (${JSON.stringify(waypoints)}, ${threshold})`);
  await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/waypoints`,
    { threshold, waypoints },
    { headers: { 'Content-Type': 'application/json' } }
  );
};

export const apiClearPositionsHistory = async (address: string): Promise<void> => {
  log.info(`Clearing positions history for dotbot ${address}`);
  await axios.delete(
    `${API_URL}/controller/dotbots/${address}/positions`,
    { headers: { 'Content-Type': 'application/json' } }
  );
};
