import React from "react";

import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";

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

  const rotation = 0;

  const svgIcon = L.divIcon({
    html: `
      <svg
        width="50"
        height="50"
        viewBox="-15 -15 75 75"
        version="1.1"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
      <g transform="rotate(${rotation} 25 25)">
        <path d="M 10 10 C 10 20 10 40 20 50 C 30 40 30 20 30 10 C 30 0 10 0 10 10" stroke="${boatStroke}" strokeWidth="1" opacity="80%" fill="${rgbColor}" />
        <path d="M 20 30 C 30 30 40 30 40 20" stroke="blue" strokeWidth="2" opacity="80%" fill="none" />
      </g>
      </svg>`,
    className: "",
    iconSize: [30, 50],
    iconAnchor: [25, 10],
  });

  return (
    <Marker key={props.sailbot.address} icon={svgIcon} position={[props.sailbot.gps_position.latitude, props.sailbot.gps_position.longitude]} opacity={`${props.sailbot.status === 0 ? "1" : "0.4"}`}>
      <Popup>{`SailBot@${props.sailbot.address}`}</Popup>
    </Marker>
  );
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
            {
              props.sailbots
                .filter(sailbot => sailbot.gps_position)
                .filter(sailbot => sailbot.status !== 2)
                .map(sailbot => <SailBotMarker key={sailbot.address} sailbot={sailbot} active={props.active} />)
            }
          </MapContainer>
        </div>
      </div>
    </div>
  )
};
