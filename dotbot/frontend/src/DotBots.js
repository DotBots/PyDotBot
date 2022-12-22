import React from "react";
import { useCallback, useEffect, useState } from "react";
import { RgbColorPicker } from "react-colorful";
import useWebSocket from 'react-use-websocket';
import useInterval from "use-interval";

import { Joystick } from "./Joystick";
import { DotBotsMap } from "./DotBotsMap";
import { SailBotsMap } from "./SailBotsMap";
import {
  apiUpdateActiveDotbotAddress, apiFetchActiveDotbotAddress,
  apiFetchDotbots, apiUpdateRgbLed, apiUpdateMoveRaw, apiUpdateControlMode,
  inactiveAddress,
} from "./rest";

const ApplicationType = {
  DotBot: 0,
  SailBot: 1,
};

const websocketUrl = `${process.env.REACT_APP_DOTBOTS_WS_URL}/controller/ws/status`;
const dotbotStatuses = ["alive", "lost", "dead"];
const dotbotBadgeStatuses = ["success", "secondary", "danger"];

const DotBotAccordionItem = (props) => {

  const [ modeAuto, setModeAuto ] = useState(false);
  const [ expanded, setExpanded ] = useState(false);
  const [ color, setColor ] = useState({ r: 0, g: 0, b: 0 });

  const applyColor = async () => {
    await apiUpdateRgbLed(props.dotbot.address, props.dotbot.application, color.r, color.g, color.b);
    await props.refresh();
  }

  let rgbColor = "rgb(0, 0, 0)"
  if (props.dotbot.rgb_led) {
    rgbColor = `rgb(${props.dotbot.rgb_led.red}, ${props.dotbot.rgb_led.green}, ${props.dotbot.rgb_led.blue})`
  }

  const updateModeAuto = async (event) => {
    setModeAuto(event.target.checked);
    await apiUpdateControlMode(props.dotbot.address, props.dotbot.application, event.target.checked);
  };

  useEffect(() => {
    if (props.dotbot.rgb_led) {
      setColor({ r: props.dotbot.rgb_led.red, g: props.dotbot.rgb_led.green, b: props.dotbot.rgb_led.blue })
    } else {
      setColor({ r: 0, g: 0, b: 0 })
    }

    // Add collapse/expand event listener to avoid weird effects with the joystick
    let collapsibleElement = document.getElementById(`collapse-${props.dotbot.address}`)
    collapsibleElement.addEventListener('hide.bs.collapse', () => {
      setExpanded(false);
    })
    collapsibleElement.addEventListener('shown.bs.collapse', () => {
      setExpanded(true);
    })
  }, [props.dotbot.address, props.dotbot.rgb_led, setColor, setExpanded]);

  return (
    <div className="accordion-item">
      <h2 className="accordion-header" id={`heading-${props.dotbot.address}`}>
        <button className="accordion-button collapsed" onClick={() => props.updateActive(props.dotbot.address)} type="button" data-bs-toggle="collapse" data-bs-target={`#collapse-${props.dotbot.address}`} aria-controls={`collapse-${props.dotbot.address}`}>
          <div className="d-flex" style={{ width: '100%' }}>
            <div className="me-2">
              <svg style={{ height: '12px', width: '12px'}}>
                <circle cx={5} cy={5} r={5} fill={rgbColor} opacity={`${props.dotbot.status === 0 ? "100%" : "30%"}`} />
              </svg>
            </div>
            <div className="me-auto">{props.dotbot.address}</div>
            <div className="me-2">
              <div className={`badge text-bg-${dotbotBadgeStatuses[props.dotbot.status]} text-light border-0`}>
                {dotbotStatuses[props.dotbot.status]}
              </div>
            </div>
            <div className="me-2">
              <div className={`badge text-bg-${props.dotbot.address === props.active ? "success" : "primary"} text-light border-0`}>
                {`${props.dotbot.address === props.active ? "active": "activate"}`}
              </div>
            </div>
          </div>
        </button>
      </h2>
      <div id={`collapse-${props.dotbot.address}`} className="accordion-collapse collapse" aria-labelledby={`heading-${props.dotbot.address}`} data-bs-parent="#accordion-dotbots">
        <div className="accordion-body">
          <div className="d-flex">
            <div className={`mx-auto justify-content-center ${!expanded && "invisible"}`}>
              <Joystick address={props.dotbot.address} application={props.dotbot.application} />
            </div>
            <div className="mx-auto justify-content-center">
              <div className="d-flex justify-content-center">
                <RgbColorPicker color={color} onChange={setColor} />
              </div>
              <div className="d-flex justify-content-center">
                <button className="btn btn-primary m-1" onClick={applyColor}>Apply color</button>
              </div>
            </div>
          </div>
          <div className="d-flex">
            <div className="form-check">
                <input className="form-check-input" type="checkbox" id="flexCheckModeAuto" defaultChecked={modeAuto} onChange={updateModeAuto} />
                <label className="form-check-label" htmlFor="flexCheckModeAuto">Autonomous mode</label>
              </div>
            </div>
        </div>
      </div>
    </div>
  )
}

const SailBotItem = (props) => {

  const [ rudderValue, setRudderValue ] = useState(0);
  const [ sailValue, setSailValue ] = useState(0);
  const [ active, setActive ] = useState(true);
  const [ color, setColor ] = useState({ r: 0, g: 0, b: 0 });

  const applyColor = async () => {
    await apiUpdateRgbLed(props.dotbot.address, props.dotbot.application, color.r, color.g, color.b);
    await props.refresh();
  }

  const rudderUpdate = async (event) => {
    const newRudderValue = parseInt(event.target.value);
    setRudderValue(newRudderValue);
    setActive(newRudderValue !== 0);
  };

  const sailUpdate = async (event) => {
    const newSailValue = parseInt(event.target.value);
    setSailValue(newSailValue);
    setActive(newSailValue !== 0);
  };

  useInterval(async () => {
    if (rudderValue === 0 && sailValue === 0) {
      setActive(false);
    }
    await apiUpdateMoveRaw(props.dotbot.address, props.dotbot.application, rudderValue, 0, 0, sailValue).catch(error => console.log(error));
  }, active ? 100 : null);

  useEffect(() => {
    if (props.dotbot.rgb_led) {
      setColor({ r: props.dotbot.rgb_led.red, g: props.dotbot.rgb_led.green, b: props.dotbot.rgb_led.blue })
    } else {
      setColor({ r: 0, g: 0, b: 0 })
    }
  }, [props.dotbot.rgb_led, setColor]);

  return (
    <div className="accordion-item">
      <h2 className="accordion-header" id={`heading-${props.dotbot.address}`}>
        <button className="accordion-button collapsed" onClick={() => props.updateActive(props.dotbot.address)} type="button" data-bs-toggle="collapse" data-bs-target={`#collapse-${props.dotbot.address}`} aria-controls={`collapse-${props.dotbot.address}`}>
          <div className="d-flex" style={{ width: '100%' }}>
            <div className="me-auto">{props.dotbot.address}</div>
            <div className="me-2">
              <div className={`badge text-bg-${dotbotBadgeStatuses[props.dotbot.status]} text-light border-0`}>
                {dotbotStatuses[props.dotbot.status]}
              </div>
            </div>
            <div className="me-2">
              <div className={`badge text-bg-${props.dotbot.address === props.active ? "success" : "primary"} text-light border-0`}>
                {`${props.dotbot.address === props.active ? "active": "activate"}`}
              </div>
            </div>
          </div>
        </button>
      </h2>
      <div id={`collapse-${props.dotbot.address}`} className="accordion-collapse collapse" aria-labelledby={`heading-${props.dotbot.address}`} data-bs-parent="#accordion-sailbots">
        <div className="accordion-body">
          <div className="d-flex">
            <div className="mx-auto justify-content-center">
              <p>{`Rudder: ${rudderValue}`}</p>
              <input type="range" min="-128" max="127" defaultValue={rudderValue} onChange={rudderUpdate}/>
            </div>
            <div className="mx-auto justify-content-center">
              <p>{`Sail: ${sailValue}`}</p>
              <input type="range" min="-128" max="127" defaultValue={sailValue} onChange={sailUpdate}/>
            </div>
          </div>
          <div className="d-flex justify-content-center">
            <div className="mx-auto justify-content-center">
              <RgbColorPicker color={color} onChange={setColor} />
            </div>
          </div>
          <div className="d-flex justify-content-center">
            <div className="mx-auto justify-content-center">
              <button className="btn btn-primary m-1" onClick={applyColor}>Apply color</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const DotBots = () => {
  const [ dotbots, setDotbots ] = useState();
  const [ activeDotbot, setActiveDotbot ] = useState(inactiveAddress);

  const updateActive = useCallback(async (address) => {
    await apiUpdateActiveDotbotAddress(address).catch((error) => console.error(error));
    setActiveDotbot(address);
  }, [setActiveDotbot]
  );

  const fetchDotBots = useCallback(async () => {
    const data = await apiFetchDotbots().catch(error => console.log(error));
    setDotbots(data);
    const active = await apiFetchActiveDotbotAddress().catch(error => console.log(error));
    setActiveDotbot(active);
  }, [setDotbots]
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
    if (message.cmd === "lh2_position" && dotbots && dotbots.length > 0) {
      let dotbotsTmp = dotbots.slice();
      for (let idx = 0; idx < dotbots.length; idx++) {
        if (dotbots[idx].address === message.address) {
          dotbotsTmp[idx].lh2_position = {x: message.x, y: message.y};
          setDotbots(dotbotsTmp);
        }
      }
    }
    if (message.cmd === "gps_position" && dotbots && dotbots.length > 0) {
      let dotbotsTmp = dotbots.slice();
      for (let idx = 0; idx < dotbots.length; idx++) {
        if (dotbots[idx].address === message.address) {
          dotbotsTmp[idx].gps_position = {
            latitude: message.latitude,
            longitude: message.longitude,
          };
          setDotbots(dotbotsTmp);
        }
      }
    }
    if (message.cmd === "direction" && dotbots && dotbots.length > 0) {
      let dotbotsTmp = dotbots.slice();
      for (let idx = 0; idx < dotbots.length; idx++) {
        if (dotbots[idx].address === message.address) {
          dotbotsTmp[idx].direction = message.direction;
          setDotbots(dotbotsTmp);
        }
      }
    }
  };

  useWebSocket(websocketUrl, {
    onOpen: () => onWsOpen(),
    onClose: () => console.log("websocket closed"),
    onMessage: (event) => onWsMessage(event),
    shouldReconnect: (event) => true,
  });

  useEffect(() => {
    if (!dotbots) {
      fetchDotBots();
    }
  }, [dotbots, fetchDotBots]);

  return (
    <>
    <nav className="navbar navbar-dark navbar-expand-lg bg-dark">
      <div className="container-fluid">
        <a className="navbar-brand text-light" href="http://www.dotbots.org">The DotBots project</a>
        <button className="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
          <span className="navbar-toggler-icon"></span>
        </button>
        <div className="collapse navbar-collapse" id="navbarNav">
          <ul className="navbar-nav">
            <li className="nav-item">
              <a className="nav-link active" aria-current="page" href="http://localhost:8000/api" target="_blank" rel="noreferrer noopener">API</a>
            </li>
          </ul>
        </div>
      </div>
    </nav>
    <div className="container">
      {dotbots && dotbots.length > 0 && (
      <>
      {dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot).length > 0 &&
      <div className="row">
        <div className="col col-xxl-6">
          <div className="card m-1">
            <div className="card-header">Available DotBots</div>
            <div className="card-body p-1">
              <div className="accordion" id="accordion-dotbots">
                {dotbots
                  .filter(dotbot => dotbot.application === ApplicationType.DotBot)
                  .map(dotbot => <DotBotAccordionItem key={dotbot.address} dotbot={dotbot} active={activeDotbot} updateActive={updateActive} refresh={fetchDotBots} />)
                }
              </div>
            </div>
          </div>
        </div>
        <div className="col col-xxl-6">
          <div className="d-block d-md-none m-1">
            <DotBotsMap dotbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot)} active={activeDotbot} updateActive={updateActive} mapSize={350} />
          </div>
          <div className="d-none d-md-block m-1">
            <DotBotsMap dotbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot)} active={activeDotbot} updateActive={updateActive} mapSize={650} />
          </div>
        </div>
      </div>
      }
      {dotbots.filter(dotbot => dotbot.application === ApplicationType.SailBot).length > 0 &&
      <div className="row">
        <div className="col col-xxl-6">
          <div className="card m-1">
            <div className="card-header">Available SailBots</div>
            <div className="card-body p-1">
              <div className="accordion" id="accordion-sailbots">
                {dotbots
                  .filter(dotbot => dotbot.application === ApplicationType.SailBot)
                  .map(dotbot => <SailBotItem key={dotbot.address} dotbot={dotbot} active={activeDotbot} updateActive={updateActive} refresh={fetchDotBots} />)
                }
              </div>
            </div>
          </div>
        </div>
        <div className="col col-xxl-6">
          <div className="d-block d-md-none m-1">
            <SailBotsMap sailbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.SailBot)} active={activeDotbot} mapSize={350} />
          </div>
          <div className="d-none d-md-block m-1">
            <SailBotsMap sailbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.SailBot)} active={activeDotbot} mapSize={650} />
          </div>
        </div>
      </div>
      }
      </>
      )}
    </div>
    </>
  );
}

export default DotBots;
