import geodist from "geodist";

export const lh2_distance = (lh21, lh22) => {
  return Math.sqrt(((lh21.x - lh22.x) ** 2) + ((lh21.y - lh22.y) ** 2));
};

export const gps_distance = (gps1, gps2) => {
  const _gps1 = {lat: gps1.lat, lon: gps1.longitude}
  const _gps2 = {lat: gps2.lat, lon: gps2.longitude}
  return geodist(_gps1, _gps2, {exact: true, unit: 'meters'});
};
