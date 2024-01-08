import axios from 'axios';

export const apiUpdateWaypoints = async (address, application, waypoints, threshold) => {
  return await axios.put(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}/${application}/waypoints`,
    {threshold: threshold, waypoints: waypoints},
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export const apiClearPositionsHistory = async (address) => {
  return await axios.delete(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots/${address}/positions`,
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
