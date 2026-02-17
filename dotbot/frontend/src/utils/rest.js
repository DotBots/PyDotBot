
import axios from 'axios';

export const API_URL = "http://localhost:8000";

export const apiFetchDotbots = async () => {
  return await axios.get(
    `${API_URL}/controller/dotbots`,
  ).then(res => res.data);
}

export const apiFetchMapSize = async () => {
  return await axios.get(
    `${API_URL}/controller/map_size`,
  ).then(res => res.data);
}

export const apiUpdateMoveRaw = async (address, application, left_x, left_y, right_x, right_y) => {
  const command = { left_x: parseInt(left_x), left_y: parseInt(left_y), right_x: parseInt(right_x), right_y: parseInt(right_y) };
  return await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/move_raw`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiUpdateRgbLed = async (address, application, red, green, blue) => {
  const command = { red: red, green: green, blue: blue };
  return await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/rgb_led`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiUpdateWaypoints = async (address, application, waypoints, threshold) => {
  return await axios.put(
    `${API_URL}/controller/dotbots/${address}/${application}/waypoints`,
    {threshold: threshold, waypoints: waypoints},
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiClearPositionsHistory = async (address) => {
  return await axios.delete(
    `${API_URL}/controller/dotbots/${address}/positions`,
    { headers: { 'Content-Type': 'application/json' } }
  );
}
