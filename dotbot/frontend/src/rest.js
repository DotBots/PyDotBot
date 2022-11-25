import axios from 'axios';

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

export const apiUpdateMoveRaw = async (address, left, right) => {
  const command = { left_x: 0, left_y: left, right_x: 0, right_y: right };
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}/move_raw`,
    command,
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiUpdateRgbLed = async (address, red, green, blue) => {
  const command = { red: red, green: green, blue: blue };
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}/rgb_led`,
    command,
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
