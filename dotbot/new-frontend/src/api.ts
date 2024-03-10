import axios from "axios";
import { API_BASE_URL } from "./constants";
import * as models from "./models";

export async function updateActiveDotBotAddress(address: string) {
  return await axios.put(
    `${API_BASE_URL}/controller/dotbot_address`,
    { address: address },
    { headers: { "Content-Type": "application/json" } },
  );
}

export async function fetchDotBots() {
  const { data: dotbots } = await axios.get<models.DotBotModel[]>(
    `${API_BASE_URL}/controller/dotbots`,
  );
  return dotbots;
}

export async function fetchDotBot(address: string) {
  const { data: dotbot } = await axios.get<models.DotBotModel>(
    `${API_BASE_URL}/controller/dotbots/${address}`,
  );
  return dotbot;
}

export async function fetchActiveDotBotAddress() {
  const { data: address } = await axios.get<models.DotBotAddressModel>(
    `${API_BASE_URL}/controller/dotbot_address`,
  );
  return address;
}

export async function updateMoveRaw(
  address: string,
  application: string,
  command: models.DotBotMoveRawCommandModel,
) {
  return await axios.put(
    `${API_BASE_URL}/controller/dotbots/${address}/${application}/move_raw`,
    command,
    { headers: { "Content-Type": "application/json" } },
  );
}

export async function updateRgbLed(
  address: string,
  application: string,
  command: models.DotBotRgbLedCommandModel,
) {
  return await axios.put(
    `${API_BASE_URL}/controller/dotbots/${address}/${application}/rgb_led`,
    command,
    { headers: { "Content-Type": "application/json" } },
  );
}

export async function updateControlMode(
  address: string,
  application: string,
  command: models.DotBotControlModeModel,
) {
  return await axios.put(
    `${API_BASE_URL}/controller/dotbots/${address}/${application}/mode`,
    command,
    { headers: { "Content-Type": "application/json" } },
  );
}

export async function updateWaypoints(
  address: string,
  application: string,
  waypoints: models.DotBotWaypoints,
) {
  return await axios.put(
    `${API_BASE_URL}/controller/dotbots/${address}/${application}/waypoints`,
    waypoints,
    { headers: { "Content-Type": "application/json" } },
  );
}

export async function clearPositionsHistory(address: string) {
  return await axios.delete(
    `${API_BASE_URL}/controller/dotbots/${address}/positions`,
    { headers: { "Content-Type": "application/json" } },
  );
}

export async function fetchLH2CalibrationState() {
  const { data: calibrationState } =
    await axios.get<models.DotBotCalibrationStateModel>(
      `${API_BASE_URL}/controller/lh2/calibration`,
    );
  return calibrationState;
}

export async function applyLH2Calibration() {
  return await axios.put(
    `${API_BASE_URL}/controller/lh2/calibration`,
  );
}

export async function addLH2CalibrationPoint(index: number | string) {
  return await axios.post(
    `${API_BASE_URL}/controller/lh2/calibration/${index}`,
  );
}
