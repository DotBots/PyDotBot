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
  const wind_angle = props.sailbot.wind_angle;

  const rudder_angle = props.sailbot.rudder_angle
  const sail_angle = props.sailbot.sail_angle

  console.log("wind: " + wind_angle + ", heading: " + rotation, "(r,s): (" + rudder_angle + ',' + sail_angle + ')')

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
        <g transform="scale(0.7) rotate(${rotation + 180} 20 25)">
          <path d="M 10 10 C 10 20 10 40 20 50 C 30 40 30 20 30 10 C 30 0 10 0 10 10" stroke="${boatStroke}" strokeWidth="1" opacity="80%" fill="${rgbColor}" />
          <g transform=" translate(20,-7) rotate(${rudder_angle} 0 10)" >
            <line x1="0" y1="10" x2="0" y2="0" stroke="red" stroke-width="2" opacity="80% "/>
          </g>
          <g transform=" translate(20,8) rotate(${sail_angle} 0 15)">
            <line x1="0" y1="15" x2="0" y2="0" stroke="red" stroke-width="2.4" opacity="80%"/>
          </g>
          <g transform=" translate(20,3) rotate(${wind_angle + 180} 0 20)">
            <line x1="0" y1="20" x2="0" y2="0" stroke="rgb(255, 255, 0)" stroke-width="2.4" opacity="100% "/>
            <line x1="-0.5" y1="0" x2="4" y2="5" stroke="rgb(255, 255, 0)" stroke-width="2.2" opacity="100%"/>
            <line x1="0.5" y1="0" x2="-4" y2="5" stroke="rgb(255, 255, 0)" stroke-width="2.2" opacity="100%"/>
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
