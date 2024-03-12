export const MAP_SIZE = 500;
export const MAX_WAYPOINTS = 16;
export const MAX_POSITION_HISTORY = 100;
export const LH2_DISTANCE_THRESHOLD = 0.01;
export const GPS_DISTANCE_THRESHOLD = 5;  // 5 meters
export const INACTIVE_ADDRESS = "0000000000000000";

// Environment variables
if (typeof import.meta.env.VITE_DOTBOTS_BASE_URL !== 'string'){
  throw new Error('VITE_DOTBOTS_BASE_URL environment variable is not set');
}
if (typeof import.meta.env.VITE_DOTBOTS_WS_URL !== 'string'){
  throw new Error('VITE_DOTBOTS_BASE_URL environment variable is not set');
}
export const API_BASE_URL = import.meta.env.VITE_DOTBOTS_BASE_URL
export const WEBSOCKET_URL = `${import.meta.env.VITE_DOTBOTS_WS_URL}/controller/ws/status`;
