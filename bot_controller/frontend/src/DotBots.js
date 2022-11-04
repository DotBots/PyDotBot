import React from "react";
import { useCallback, useEffect, useState } from "react";
import { RgbColorPicker } from "react-colorful";
import useInterval from "use-interval";

import { Joystick } from "./Joystick";
import {
  apiUpdateActiveDotbotAddress, apiFetchActiveDotbotAddress,
  apiFetchDotbots, apiUpdateRgbLed
} from "./rest";


const DotBotRow = (props) => {

  const updateActive = async () => {
    let newAddress = props.dotbot.address;
    if (props.dotbot.address === props.activeDotbot) {
      newAddress = "0000000000000000"
    }
    await apiUpdateActiveDotbotAddress(newAddress).catch((error) => console.error(error));
  }

  return (
    <tr>
      <td>{`${props.dotbot.address}`}</td>
      <td>{`${props.dotbot.application}`}</td>
      <td>{`${props.dotbot.swarm}`}</td>
      <td>
      {
        props.dotbot.address === props.activeDotbot ? (
          <button className="badge text-bg-success text-light border-0" onClick={updateActive}>active</button>
        ) : (
          <button className="badge text-bg-primary text-light border-0" onClick={updateActive}>activate</button>
        )
      }
      </td>
    </tr>
  )
}

const DotBots = () => {
  const [ dotbots, setDotbots ] = useState();
  const [ activeDotbot, setActiveDotbot ] = useState("0000000000000000");
  const [ color, setColor ] = useState({ r: 0, g: 0, b: 0 });

  const fetchDotBots = useCallback(async () => {
    const data = await apiFetchDotbots().catch(error => console.log(error));
    setDotbots(data);
    const active = await apiFetchActiveDotbotAddress().catch(error => console.log(error));
    setActiveDotbot(active);
  }, [setDotbots, setActiveDotbot]
  );

  useInterval(() => {
    fetchDotBots();
  }, 1000);

  const applyColor = async () => {
    await apiUpdateRgbLed(activeDotbot, color.r, color.g, color.b);
  }

  useEffect(() => {
    if (!dotbots) {
      fetchDotBots();
    }
  }, [dotbots, fetchDotBots]);

  const controlsVisible = activeDotbot !== "0000000000000000" && dotbots && dotbots.filter(dotbot => dotbot.address === activeDotbot).length > 0;

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
                <th>Application</th>
                <th>Swarm ID</th>
                <th>Controls</th>
              </tr>
            </thead>
            <tbody>
            {dotbots && dotbots.map(dotbot => <DotBotRow key={dotbot.address} dotbot={dotbot} activeDotbot={activeDotbot}/>)}
            </tbody>
          </table>
          <div className={`d-flex justify-content-center ${controlsVisible ? "visible" : "invisible"}`}>
            <div className="me-2">
            <RgbColorPicker color={color} onChange={setColor} />
            <button className="btn btn-primary m-1" onClick={applyColor}>Apply color</button>
            </div>
            <Joystick address={activeDotbot} />
          </div>
        </div>
      </div>
    </div>
    </>
  );
}

export default DotBots;
