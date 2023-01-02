import axios from 'axios';

export const inactiveAddress = "0000000000000000";

export const apiUpdateActiveDotbotAddress = async (address) => {
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbot_address`,
    { address: address },
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiFetchDotbots = async () => {
  return await axios.get(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots`,
  ).then(res => res.data);
}

export const apiFetchDotbot = async (address) => {
    return await axios.get(
      `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}`,
    ).then(res => res.data);
  }

export const apiFetchActiveDotbotAddress = async () => {
  return await axios.get(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbot_address`,
  ).then(res => res.data.address);
}

export const apiUpdateMoveRaw = async (address, application, left_x, left_y, right_x, right_y) => {
  const command = { left_x: left_x, left_y: left_y, right_x: right_x, right_y: right_y };
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}/${application}/move_raw`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiUpdateRgbLed = async (address, application, red, green, blue) => {
  const command = { red: red, green: green, blue: blue };
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}/${application}/rgb_led`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiUpdateControlMode = async (address, application, mode) => {
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}/${application}/mode`,
    { mode: mode ? 1 : 0 },
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiUpdateWaypoints = async (address, application, waypoints) => {
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}/${application}/waypoints`,
    waypoints,
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiFetchLH2CalibrationState = async () => {
  return await axios.get(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/lh2/calibration`,
  ).then(res => res.data);
}

export const apiApplyLH2Calibration = async () => {
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/lh2/calibration`,
  );
}

export const apiAddLH2CalibrationPoint = async (index) => {
  return await axios.post(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/lh2/calibration/${index}`,
  );
}
