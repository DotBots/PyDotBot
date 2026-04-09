import React, { useCallback } from "react";
import { Circle, MapContainer, TileLayer, Marker, Popup, Polyline, useMapEvent } from "react-leaflet";
import L, { LatLngExpression } from "leaflet";
import { DotBot } from "./types";

const defaultPosition: LatLngExpression = [
  48.832313766146896, 2.4126897594949184
];

interface SailBotMarkerProps {
  sailbot: DotBot;
  active: string;
}

export const SailBotMarker: React.FC<SailBotMarkerProps> = (props) => {
  let rgbColor = "rgb(0, 0, 0)";
  if (props.sailbot.rgb_led) {
    rgbColor = `rgb(${props.sailbot.rgb_led.red}, ${props.sailbot.rgb_led.green}, ${props.sailbot.rgb_led.blue})`;
  }

  let boatStroke = "none";
  if (props.sailbot.address === props.active) {
    boatStroke = "black";
  }

  const waypointsLineOptions = {
    color: rgbColor,
    opacity: props.sailbot.status === 0 ? 0.5 : 0.2,
    weight: 2,
    dashArray: "8",
  };

  const waypointsOptions = {
    color: rgbColor,
    opacity: props.sailbot.status === 0 ? 0.8 : 0.3,
    weight: 6,
  };

  const waypointsRadiusOptions = {
    color: rgbColor,
    opacity: props.sailbot.status === 0 ? 0.2 : 0.1,
    weight: 0,
  };

  const positionsOptions = {
    color: rgbColor,
    weight: 2,
    opacity: props.sailbot.status === 0 ? 1.0 : 0.4,
  };

  const mainsheet2sail_angle = (sail_in_length_deg: number, app_wind_angle_deg: number): number => {
    let sail_out_deg: number;
    const sail_in_length_rad = sail_in_length_deg * (Math.PI / 180);
    const app_wind_angle_rad = app_wind_angle_deg * (Math.PI / 180);

    if (Math.cos(app_wind_angle_rad) + Math.cos(sail_in_length_rad) > 0) {
      const sign = Math.sign(Math.sin(app_wind_angle_rad));
      sail_out_deg = sail_in_length_deg * sign;
    } else {
      sail_out_deg = 180 - app_wind_angle_deg;
    }

    return sail_out_deg;
  };

  const rotation = parseInt(String(props.sailbot.direction ?? 0));
  const wind_angle = parseInt(String(props.sailbot.wind_angle ?? 0));
  const rudder_angle = parseInt(String(props.sailbot.rudder_angle ?? 0));
  const sail_angle = mainsheet2sail_angle(props.sailbot.sail_angle ?? 0, wind_angle);

  const svgIcon = L.divIcon({
    html: `
      <svg
        width="200"
        height="200"
        viewBox="0 0 200 200"
        version="1.1"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
      <g>
        <g transform="translate(8,6) scale(1.2)">
          <g transform="scale(0.7) rotate(${rotation + 180} 20 25)">
            <path d="M 10 10 C 10 20 10 40 20 50 C 30 40 30 20 30 10 C 30 0 10 0 10 10" stroke="${boatStroke}" strokeWidth="1" opacity="80%" fill="${rgbColor}" />
            <g transform=" translate(20,-7) rotate(${-rudder_angle} 0 10)" >
              <line x1="0" y1="10" x2="0" y2="0" stroke="red" stroke-width="2" opacity="80% "/>
            </g>
            <g transform=" translate(20,8) rotate(${-sail_angle} 0 15)">
              <line x1="0" y1="15" x2="0" y2="0" stroke="red" stroke-width="2.4" opacity="80%"/>
            </g>
            <g transform=" translate(20,3) rotate(${wind_angle + 180} 0 20)">
              <line x1="0" y1="20" x2="0" y2="0" stroke="rgb(255, 255, 0)" stroke-width="2.4" opacity="100% "/>
              <line x1="-0.5" y1="0" x2="4" y2="5" stroke="rgb(255, 255, 0)" stroke-width="2.2" opacity="100%"/>
              <line x1="0.5" y1="0" x2="-4" y2="5" stroke="rgb(255, 255, 0)" stroke-width="2.2" opacity="100%"/>
            </g>
          </g>
        </g>
      </g>
      </svg>`,
    className: "",
    iconSize: [30, 50],
    iconAnchor: [25, 25],
  });

  const gpsPos = props.sailbot.gps_position!;

  return (
    <>
      {props.sailbot.waypoints
        .slice(1)
        .map((waypoint, i) => (
          <Circle
            key={i}
            center={Object.values(waypoint) as LatLngExpression}
            pathOptions={waypointsRadiusOptions}
            radius={props.sailbot.waypoints_threshold}
          />
        ))
      }
      {props.sailbot.waypoints.length > 0 && (
        <Polyline
          pathOptions={waypointsLineOptions}
          positions={props.sailbot.waypoints.map(waypoint => Object.values(waypoint) as LatLngExpression)}
        />
      )}
      {props.sailbot.waypoints.map((waypoint, i) => (
        <Circle
          key={i}
          center={Object.values(waypoint) as LatLngExpression}
          pathOptions={waypointsOptions}
          radius={1}
        />
      ))}
      {props.sailbot.position_history.length > 0 && (
        <Polyline
          pathOptions={positionsOptions}
          positions={props.sailbot.position_history.map(position => Object.values(position) as LatLngExpression)}
        />
      )}
      <Marker
        key={props.sailbot.address}
        icon={svgIcon}
        position={[gpsPos.latitude, gpsPos.longitude]}
        opacity={props.sailbot.status === 0 ? 1 : 0.4}
      >
        <Popup>
          {`SailBot@${props.sailbot.address}`}
        </Popup>
      </Marker>
    </>
  );
};

interface SailbotItemsProps {
  sailbots: DotBot[];
  active: string;
  mapClicked: (lat: number, lng: number) => void;
}

const SailbotItems: React.FC<SailbotItemsProps> = (props) => {
  const onClick = useCallback(
    (event: { latlng: { lat: number; lng: number } }) => {
      props.mapClicked(event.latlng.lat, event.latlng.lng);
    },
    [props],
  );

  useMapEvent('click', onClick);

  return (
    <>
      {props.sailbots
        .filter(sailbot => sailbot.gps_position)
        .filter(sailbot => sailbot.status !== 2)
        .map(sailbot => (
          <SailBotMarker key={sailbot.address} sailbot={sailbot} active={props.active} />
        ))
      }
    </>
  );
};

interface SailBotsMapProps {
  sailbots: DotBot[];
  active: string;
  showHistory: boolean;
  updateShowHistory: (show: boolean, application: number) => void;
  mapClicked: (lat: number, lng: number) => void;
  mapSize: number;
}

export const SailBotsMap: React.FC<SailBotsMapProps> = (props) => {
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
            <SailbotItems sailbots={props.sailbots} mapClicked={props.mapClicked} active={props.active} />
          </MapContainer>
        </div>
      </div>
    </div>
  );
};
