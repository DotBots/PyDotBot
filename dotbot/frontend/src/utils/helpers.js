import geodist from "geodist";

import { gps_distance_threshold, lh2_distance_threshold } from "./constants";

export const lh2_distance = (lh21, lh22) => {
  return Math.sqrt(((lh21.x - lh22.x) ** 2) + ((lh21.y - lh22.y) ** 2));
};

export const gps_distance = (gps1, gps2) => {
  const _gps1 = {lat: gps1.lat, lon: gps1.longitude}
  const _gps2 = {lat: gps2.lat, lon: gps2.longitude}
  return geodist(_gps1, _gps2, {exact: true, unit: 'meters'});
};

export const handleDotBotUpdate = (prevList, message) => {
  let changed = false;
  let nextList = prevList.map(bot => {
    if (bot.address !== message.data.address) { return bot; }

     let botChanged = false;
    let updated = bot;

     // direction
    if (message.data.direction != null && bot.direction !== message.data.direction) {
      updated = { ...updated, direction: message.data.direction };
      botChanged = true;
    }

     // rgb_led
    if (message.data.rgb_led != null) {
      const newLed = message.data.rgb_led;
      const oldLed = bot.rgb_led ?? { red: 0, green: 0, blue: 0 };

       if (
        oldLed.red !== newLed.red ||
        oldLed.green !== newLed.green ||
        oldLed.blue !== newLed.blue
      ) {
        updated = { ...updated, rgb_led: newLed };
        botChanged = true;
      }
    }

     // wind_angle
    if (message.data.wind_angle != null && bot.wind_angle !== message.data.wind_angle) {
      updated = { ...updated, wind_angle: message.data.wind_angle };
      botChanged = true;
    }

     // rudder_angle
    if (message.data.rudder_angle != null && bot.rudder_angle !== message.data.rudder_angle) {
      updated = { ...updated, rudder_angle: message.data.rudder_angle };
      botChanged = true;
    }

     // sail_angle
    if (message.data.sail_angle != null && bot.sail_angle !== message.data.sail_angle) {
      updated = { ...updated, sail_angle: message.data.sail_angle };
      botChanged = true;
    }

     // lh2_position + position_history
    if (message.data.lh2_position != null && lh2_distance(bot.lh2_position, message.data.lh2_position) > lh2_distance_threshold) {
      let newHistory = [...bot.position_history, message.data.lh2_position];
      updated = { ...updated, lh2_position: message.data.lh2_position, position_history: newHistory };
      botChanged = true;
    }

     // lh2_waypoints
    if (message.data.lh2_waypoints != null) {
      updated = { ...updated, lh2_waypoints: message.data.lh2_waypoints };
      botChanged = true;
    }

     // gps_position + position_history
    if (message.data.gps_position != null && gps_distance(bot.gps_position, message.data.gps_position) > gps_distance_threshold) {
      let newHistory = [...bot.position_history, message.data.gps_position];
      updated = { ...updated, gps_position: message.data.gps_position, position_history: newHistory };
      botChanged = true;
    }

     // gps_waypoints
    if (message.data.gps_waypoints != null) {
      updated = { ...updated, gps_waypoints: message.data.gps_waypoints };
      botChanged = true;
    }

     // battery
    if (message.data.battery != null && Math.abs(bot.battery - message.data.battery) > 0.1) {
      updated = { ...updated, battery: message.data.battery };
      botChanged = true;
    }

     if (botChanged) {changed = true;}
    return botChanged ? updated : bot;
  });
  return changed ? nextList : prevList;
};
