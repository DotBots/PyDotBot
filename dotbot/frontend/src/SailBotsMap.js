import React from "react";

import { useCallback } from "react";
import { Circle, MapContainer, TileLayer, Marker, Popup, Polyline, useMapEvent } from "react-leaflet";

import L from "leaflet";

const defaultPosition = [
  48.832313766146896, 2.4126897594949184
];

export const SailBotMarker = (props) => {

  let rgbColor = "rgb(0, 0, 0)"
  if (props.sailbot.rgb_led) {
    rgbColor = `rgb(${props.sailbot.rgb_led.red}, ${props.sailbot.rgb_led.green}, ${props.sailbot.rgb_led.blue})`
  }

  let boatStroke = "none";
  if (props.sailbot.address === props.active) {
    boatStroke = "black";
  }

  const waypointsLineOptions = {
    color: rgbColor,
    opacity: `${props.sailbot.status === 0 ? "50%" : "20%"}`,
    weight: "2",
    dashArray: "8"
  };

  const waypointsOptions = {
    color: rgbColor,
    opacity: `${props.sailbot.status === 0 ? "80%" : "30%"}`,
    weight: "6",
  };

  const waypointsRadiusOptions = {
    color: rgbColor,
    opacity: `${props.sailbot.status === 0 ? "20%" : "10%"}`,
    weight: "0",
  };

  const positionsOptions = {
    color: rgbColor,
    weight: "2",
    opacity: `${props.sailbot.status === 0 ? "100%" : "40%"}`,
  };

  // const rotation = (props.sailbot.direction) ? props.sailbot.direction - 180 : 180;
  const rotation = props.sailbot.direction
  // props.sailbot.wind_angle ranges from 0 to 359
  const wind_angle = -props.sailbot.wind_angle + 180-33;
  console.log("wind: " + wind_angle + ", heading: " + rotation)


  const svgIcon = L.divIcon({
    html: `
      <svg
        width="100"
        height="100"
        viewBox="-15 -15 75 75"
        version="1.1"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
      <g>
        <g transform="scale(1.5) rotate(${rotation+280} 11.8 11.8)">
          <path fill="${rgbColor}" d="M7.83,3.404l1.741-2.909C9.367,0.407,9.15,0.344,8.913,0.344c-0.954,0-1.728,0.774-1.728,1.728C7.185,2.613,7.441,3.087,7.83,3.404z"></path>
          <path fill="${rgbColor}" d="M19.645,12.002l-0.464-0.31c-0.09-1.505-0.628-2.972-1.575-4.187l-1.212,0.156l0.084-0.125c0.316-0.473,0.188-1.119-0.286-1.435L15.517,5.65c-0.473-0.316-1.119-0.187-1.435,0.286l-0.095,0.142l-0.538-3.219l-3.271-2.033l-1.754,2.93l0.86,0.481L3.04,3.445L2.136,4.798l3.766,2.516c-0.17,0.204-0.333,0.414-0.484,0.639C5.269,8.178,5.137,8.41,5.013,8.645L1.247,6.129L0.344,7.482l4.878,8.537l0.008-0.013c0.098,0.164,0.207,0.322,0.317,0.479l1.628-0.209l-0.302,0.452c-0.316,0.473-0.187,1.119,0.286,1.435l0.675,0.451c0.473,0.316,1.119,0.188,1.435-0.286l0.252-0.378l0.185,1.442c1.418,0.385,2.904,0.334,4.273-0.105l0.552,0.369c1.512-0.533,2.87-1.542,3.829-2.977C19.32,15.244,19.732,13.602,19.645,12.002z M14.09,16.055c-0.106,0.158-0.32,0.201-0.478,0.095c-0.158-0.106-0.201-0.32-0.095-0.478c0.106-0.158,0.32-0.201,0.478-0.095C14.153,15.682,14.196,15.896,14.09,16.055zM13.969,13.664c-0.513,0.769-1.371,1.227-2.296,1.227c-0.546,0-1.075-0.161-1.531-0.465c-1.265-0.845-1.606-2.561-0.762-3.826c0.513-0.768,1.372-1.227,2.297-1.227c0.545,0,1.074,0.161,1.53,0.465C14.472,10.683,14.814,12.4,13.969,13.664z M15.065,17.476c-0.106,0.158-0.32,0.201-0.478,0.095c-0.158-0.106-0.201-0.32-0.095-0.478c0.106-0.158,0.32-0.201,0.478-0.095C15.129,17.104,15.171,17.318,15.065,17.476z M15.334,14.768c-0.106,0.158-0.32,0.201-0.478,0.095c-0.158-0.106-0.201-0.32-0.095-0.478c0.106-0.158,0.32-0.201,0.478-0.095C15.397,14.396,15.44,14.61,15.334,14.768zM15.568,13.222c-0.158-0.106-0.201-0.32-0.095-0.478c0.106-0.158,0.32-0.201,0.478-0.095c0.158,0.106,0.201,0.32,0.095,0.478C15.94,13.285,15.726,13.327,15.568,13.222z M16.665,15.658c-0.106,0.158-0.32,0.201-0.478,0.095c-0.158-0.106-0.201-0.32-0.095-0.478c0.106-0.158,0.32-0.201,0.478-0.095S16.771,15.499,16.665,15.658z M17.733,13.483c-0.106,0.158-0.32,0.201-0.478,0.095c-0.158-0.106-0.201-0.32-0.095-0.478c0.106-0.158,0.32-0.201,0.478-0.095C17.796,13.111,17.839,13.325,17.733,13.483z"></path>
          <path fill="no${rgbColor}ne" d="M12.824,10.412c-0.341-0.228-0.738-0.349-1.146-0.349c-0.694,0-1.338,0.344-1.723,0.92c-0.634,0.949-0.377,2.236,0.571,2.869c0.342,0.228,0.739,0.35,1.147,0.35c0.694,0,1.337-0.344,1.722-0.92C14.029,12.332,13.773,11.045,12.824,10.412z"></path>
        </g>
        <g transform=" translate(-4.5,8) rotate(${rotation+280 - wind_angle+180} 22 10)">
          <path fill="rgb(255, 255, 0)" d="M18.271,9.212H3.615l4.184-4.184c0.306-0.306,0.306-0.801,0-1.107c-0.306-0.306-0.801-0.306-1.107,0 L1.21,9.403C1.194,9.417,1.174,9.421,1.158,9.437c-0.181,0.181-0.242,0.425-0.209,0.66c0.005,0.038,0.012,0.071,0.022,0.109 c0.028,0.098,0.075,0.188,0.142,0.271c0.021,0.026,0.021,0.061,0.045,0.085c0.015,0.016,0.034,0.02,0.05,0.033l5.484,5.483 c0.306,0.307,0.801,0.307,1.107,0c0.306-0.305,0.306-0.801,0-1.105l-4.184-4.185h14.656c0.436,0,0.788-0.353,0.788-0.788 S18.707,9.212,18.271,9.212z"></path>
        </g>
        </g>
      </g>
      
      </svg>`,
    className: "",
    iconSize: [30, 50],
    iconAnchor: [25, 25],
  });

  return (
    <>
    {
      props.sailbot.waypoints
        .slice(1) // Skip first waypoint which is the start position
        .map(waypoint => <Circle center={Object.values(waypoint)} pathOptions={waypointsRadiusOptions} radius={props.sailbot.waypoints_threshold} />)
    }
    {(props.sailbot.waypoints.length > 0) && (
      <Polyline pathOptions={waypointsLineOptions} positions={props.sailbot.waypoints.map(waypoint => Object.values(waypoint))} />
    )}
    {
      props.sailbot.waypoints
        .map(waypoint => <Circle center={Object.values(waypoint)} pathOptions={waypointsOptions} radius={1} />)
    }
    {(props.sailbot.position_history.length > 0) && (
      <Polyline pathOptions={positionsOptions} positions={props.sailbot.position_history.map(position => Object.values(position))} />
    )}
    <Marker key={props.sailbot.address} icon={svgIcon} position={[props.sailbot.gps_position.latitude, props.sailbot.gps_position.longitude]} opacity={`${props.sailbot.status === 0 ? "1" : "0.4"}`}>
      <Popup>
        {`SailBot@${props.sailbot.address}`}
      </Popup>
    </Marker>
    </>
  );
};

const SailbotItems = (props) => {
  const onClick = useCallback(
    (event) => {
      props.mapClicked(event.latlng.lat, event.latlng.lng)
    }, [ props ],
  );

  useMapEvent('click', onClick);

  return (
    <>
    {
      props.sailbots
        .filter(sailbot => sailbot.gps_position)
        .filter(sailbot => sailbot.status !== 2)
        .map(sailbot => <SailBotMarker key={sailbot.address} sailbot={sailbot} active={props.active} />)
      }
    </>
  )
};

export const SailBotsMap = (props) => {

  const style = { height: `${props.mapSize}px`, width: `${props.mapSize}px` };

  return (
    <div className={`${props.sailbots.length > 0 ? "visible" : "invisible"}`}>
      <div className="row justify-content-center">
        <div className="col d-flex justify-content-center">
          <MapContainer center={defaultPosition} zoom={17} scrollWheelZoom={true} style={style}>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <SailbotItems sailbots={props.sailbots} mapClicked={props.mapClicked} />
          </MapContainer>
        </div>
      </div>
    </div>
  )
};
