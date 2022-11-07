import React from "react";
import { useCallback, useEffect, useState } from "react";
import { RgbColorPicker } from "react-colorful";
import useWebSocket from 'react-use-websocket';

import { Joystick } from "./Joystick";
import {
  apiUpdateActiveDotbotAddress, apiFetchActiveDotbotAddress,
  apiFetchDotbots, apiUpdateRgbLed
} from "./rest";


const websocketUrl = `${process.env.REACT_APP_DOTBOTS_WS_URL}/controller/ws/status`;
const inactiveAddress = "0000000000000000";


const DotBotRow = (props) => {

  return (
    <tr>
      <td>{`${props.dotbot.address}`}</td>
      <td>
      {
        props.dotbot.address === props.activeDotbot ? (
          <button className="badge text-bg-success text-light border-0" onClick={() => props.controlsClicked(props.dotbot.address)}>active</button>
        ) : (
          <button className="badge text-bg-primary text-light border-0" onClick={() => props.controlsClicked(props.dotbot.address)}>activate</button>
        )
      }
      </td>
    </tr>
  )
}

const DotBots = () => {
  const [ dotbots, setDotbots ] = useState();
  const [ activeDotbot, setActiveDotbot ] = useState(inactiveAddress);
  const [ color, setColor ] = useState({ r: 0, g: 0, b: 0 });

  const updateColor = useCallback((data, address) => {
    const dotbot = data.filter(db => db.address === address)[0];
    if (dotbot && dotbot.rgb_led) {
      setColor({r: dotbot.rgb_led.red, g: dotbot.rgb_led.green, b: dotbot.rgb_led.blue,});
    } else {
      setColor({r: 0, g: 0, b: 0,});
    }
  }, [setColor]
  );

  const updateActive = useCallback(async (address) => {
    await apiUpdateActiveDotbotAddress(address).catch((error) => console.error(error));
    setActiveDotbot(address);
    if (dotbots && address !== inactiveAddress) {
      updateColor(dotbots, address);
    }
  }, [dotbots, setActiveDotbot, updateColor]
  );

  const switchActive = async (address) => {
    let newAddress = address;
    if (address === activeDotbot) {
      newAddress = inactiveAddress
    }
    await updateActive(newAddress);
  };

  const fetchDotBots = useCallback(async () => {
    const data = await apiFetchDotbots().catch(error => console.log(error));
    setDotbots(data);
    const active = await apiFetchActiveDotbotAddress().catch(error => console.log(error));
    setActiveDotbot(active);
    if (data && active !== inactiveAddress) {
      updateColor(data, active);
    }
  }, [setDotbots, updateColor]
  );

  const onWsOpen = () => {
    console.log('websocket opened');
    fetchDotBots();
  };

  const onWsMessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.cmd === "reload") {
      fetchDotBots();
    }
  };

  useWebSocket(websocketUrl, {
    onOpen: () => onWsOpen(),
    onClose: () => console.log("websocket closed"),
    onMessage: (event) => onWsMessage(event),
    shouldReconnect: (event) => true,
  });

  const applyColor = async () => {
    await apiUpdateRgbLed(activeDotbot, color.r, color.g, color.b);
    await fetchDotBots();
  }

  useEffect(() => {
    if (!dotbots) {
      fetchDotBots();
    }
  }, [dotbots, fetchDotBots]);

  const controlsVisible = activeDotbot !== inactiveAddress && dotbots && dotbots.filter(dotbot => dotbot.address === activeDotbot).length > 0;

  return (
    <>
    <nav className="navbar navbar-expand-lg bg-dark">
      <div className="container-fluid">
        <a className="navbar-brand text-light" href="http://www.dotbots.org">DotBots</a>
      </div>
    </nav>
    <div className="container">
      <div className="card m-1">
        <div className="card-header">Available DotBots</div>
        <div className="card-body p-0">
          <table id="table" className="table table-striped align-middle">
            <thead>
              <tr>
                <th>Address</th>
                <th>Controls</th>
              </tr>
            </thead>
            <tbody>
            {dotbots && dotbots.map(dotbot => <DotBotRow key={dotbot.address} dotbot={dotbot} activeDotbot={activeDotbot} controlsClicked={switchActive}/>)}
            </tbody>
          </table>
        </div>
      </div>
      <div className={`card m-1 ${controlsVisible ? "visible" : "invisible"}`}>
        <div className="card-body">
          <div className="row">
            <div className="col d-flex justify-content-center">
              <Joystick address={activeDotbot} />
            </div>
            <div className="col m-2">
              <div className="row">
                <div className="col">
                  <div className="d-flex justify-content-center">
                    <RgbColorPicker color={color} onChange={setColor} />
                  </div>
                </div>
              </div>
              <div className="col m-2">
                <div className="d-flex justify-content-center">
                  <button className="btn btn-primary m-1" onClick={applyColor}>Apply color</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}

export default DotBots;
