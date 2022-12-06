import React from "react";

import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";

const defaultPosition = [
  48.832313766146896, 2.4126897594949184
];

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
                .map(
                  sailbot => (
                  <Marker key={sailbot.address} position={[sailbot.gps_position.latitude, sailbot.gps_position.longitude]} opacity={`${sailbot.status === 0 ? "1" : "0.4"}`}>
                    <Popup>{`SailBot@${sailbot.address}`}</Popup>
                  </Marker>)
                )
            }
          </MapContainer>
        </div>
      </div>
    </div>
  )
};
