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
  apiUpdateWaypoints, inactiveAddress,
} from "./rest";
import { ApplicationType, ControlModeType, gps_distance_threshold, lh2_distance_threshold, maxWaypoints } from "./constants";
import { gps_distance, lh2_distance } from "./helpers";


const websocketUrl = `${process.env.REACT_APP_DOTBOTS_WS_URL}/controller/ws/status`;
const dotbotStatuses = ["alive", "lost", "dead"];
const dotbotBadgeStatuses = ["success", "secondary", "danger"];


const DotBotAccordionItem = (props) => {

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

  const autoModeClicked = async (event) => {
    await props.updateAutoMode(props.dotbot.address, props.dotbot.application, event.target.checked);
  }

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
          {props.dotbot.lh2_position &&
            <div className="d-flex mx-auto">
              <div className="form-check">
                <input className="form-check-input" type="checkbox" id="flexCheckModeAuto" defaultChecked={props.dotbot.mode} onChange={autoModeClicked} />
                <label className="form-check-label" htmlFor="flexCheckModeAuto">Autonomous mode</label>
              </div>
            </div>
          }
          {props.dotbot.waypoints && props.dotbot.waypoints.length > 0 &&
            <div className="d-flex mx-auto">
              <button className="btn btn-primary btn-sm m-1" onClick={async () => props.applyWaypoints(props.dotbot.address, props.dotbot.application)}>Apply waypoints</button>
              <button className="btn btn-primary btn-sm m-1" onClick={async () => props.clearWaypoints(props.dotbot.address, props.dotbot.application)}>Clear waypoints</button>
            </div>
          }
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

  const autoModeClicked = async (event) => {
    await props.updateAutoMode(props.dotbot.address, props.dotbot.application, event.target.checked);
  }

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
          {props.dotbot.gps_position &&
            <div className="d-flex mx-auto">
              <div className="form-check">
                <input className="form-check-input" type="checkbox" id="flexCheckModeAuto" defaultChecked={props.dotbot.mode} onChange={autoModeClicked} />
                <label className="form-check-label" htmlFor="flexCheckModeAuto">Autonomous mode</label>
              </div>
            </div>
          }
          {props.dotbot.waypoints && props.dotbot.waypoints.length > 0 &&
            <div className="d-flex mx-auto">
              <button className="btn btn-primary btn-sm m-1" onClick={async () => props.applyWaypoints(props.dotbot.address, ApplicationType.SailBot)}>Apply waypoints</button>
              <button className="btn btn-primary btn-sm m-1" onClick={async () => props.clearWaypoints(props.dotbot.address, ApplicationType.SailBot)}>Clear waypoints</button>
            </div>
          }
        </div>
      </div>
    </div>
  );
}

const DotBots = () => {
  const [ dotbots, setDotbots ] = useState();
  const [ activeDotbot, setActiveDotbot ] = useState(inactiveAddress);
  const [ showDotBotHistory, setShowDotBotHistory ] = useState(true);
  const [ showSailBotHistory, setShowSailBotHistory ] = useState(true);

  const updateActive = useCallback(async (address) => {
    await apiUpdateActiveDotbotAddress(address).catch((error) => console.error(error));
    setActiveDotbot(address);
  }, [setActiveDotbot]
  );

  const updateAutoMode = async (address, application, mode) => {
    const newMode = mode ? ControlModeType.Auto : ControlModeType.Manual;
    await apiUpdateControlMode(address, application, newMode);
    let dotbotsTmp = dotbots.slice();
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        dotbotsTmp[idx].mode = newMode;
        setDotbots(dotbotsTmp);
      }
    }
  };

  const updateShowHistory = (show, application) => {
    if (application === ApplicationType.SailBot) {
      setShowSailBotHistory(show);
    } else {
      setShowDotBotHistory(show);
    }
  };

  const fetchDotBots = useCallback(async () => {
    const data = await apiFetchDotbots().catch(error => console.log(error));
    setDotbots(data);
    const active = await apiFetchActiveDotbotAddress().catch(error => console.log(error));
    setActiveDotbot(active);
  }, [setDotbots, setActiveDotbot]
  );

  const mapClicked = useCallback((x, y) => {
    if (!dotbots || dotbots.length === 0) {
      return;
    }

    const activeDotbots = dotbots.filter(dotbot => activeDotbot === dotbot.address);
    // Do nothing if no active dotbot
    if (activeDotbots.length === 0) {
      return;
    }

    const dotbot = activeDotbots[0];
    if (dotbot.mode !== ControlModeType.Auto) {
      // Do nothing if dotbot is in manual mode
      return;
    }

    // Limit number of waypoints to maxWaypoints
    if (dotbot.waypoints.length >= maxWaypoints) {
      return;
    }

    if (dotbot.application === ApplicationType.SailBot) {
      let dotbotsTmp = dotbots.slice();
      for (let idx = 0; idx < dotbots.length; idx++) {
        if (dotbots[idx].address === dotbot.address) {
          if (dotbotsTmp[idx].waypoints.length === 0) {
            dotbotsTmp[idx].waypoints.push({
              latitude: dotbotsTmp[idx].gps_position.latitude,
              longitude: dotbotsTmp[idx].gps_position.longitude,
            });
          }
          dotbotsTmp[idx].waypoints.push({latitude: x, longitude: y});
          setDotbots(dotbotsTmp);
        }
      }
    }
    if (dotbot.application === ApplicationType.DotBot) {
      let dotbotsTmp = dotbots.slice();
      for (let idx = 0; idx < dotbots.length; idx++) {
        if (dotbots[idx].address === dotbot.address) {
          if (dotbotsTmp[idx].waypoints.length === 0) {
            dotbotsTmp[idx].waypoints.push({
              x: dotbotsTmp[idx].lh2_position.x,
              y: dotbotsTmp[idx].lh2_position.y,
              z: 0
            });
          }
          dotbotsTmp[idx].waypoints.push({x: x, y: y, z: 0});
          setDotbots(dotbotsTmp);
        }
      }
    }
  }, [activeDotbot, dotbots, setDotbots]
  );

  const applyWaypoints = async (address, application) => {
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        await apiUpdateWaypoints(address, application, dotbots[idx].waypoints);
        return;
      }
    }
  };

  const clearWaypoints = async (address, application) => {
    let dotbotsTmp = dotbots.slice();
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        dotbotsTmp[idx].waypoints = [];
        await apiUpdateWaypoints(address, application, []);
        setDotbots(dotbotsTmp);
        return;
      }
    }
  };

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
          const newPosition = {x: message.x, y: message.y};
          if (dotbotsTmp[idx].lh2_position && (dotbotsTmp[idx].position_history.length === 0 || lh2_distance(dotbotsTmp[idx].lh2_position, newPosition) > lh2_distance_threshold)) {
            dotbotsTmp[idx].position_history.push(newPosition);
          }
          dotbotsTmp[idx].lh2_position = newPosition;
          setDotbots(dotbotsTmp);
        }
      }
    }
    if (message.cmd === "gps_position" && dotbots && dotbots.length > 0) {
      let dotbotsTmp = dotbots.slice();
      for (let idx = 0; idx < dotbots.length; idx++) {
        if (dotbots[idx].address === message.address) {
          const newPosition = {
            latitude: message.latitude,
            longitude: message.longitude,
          };
          if (dotbotsTmp[idx].position_history.length === 0 || gps_distance(dotbotsTmp[idx].gps_position, newPosition) > gps_distance_threshold) {
            dotbotsTmp[idx].position_history.push(newPosition);
          }
          dotbotsTmp[idx].gps_position = newPosition;
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
                  .map(dotbot =>
                    <DotBotAccordionItem
                      key={dotbot.address}
                      dotbot={dotbot}
                      active={activeDotbot}
                      updateActive={updateActive}
                      updateAutoMode={updateAutoMode}
                      applyWaypoints={applyWaypoints}
                      clearWaypoints={clearWaypoints}
                      refresh={fetchDotBots}
                    />
                  )
                }
              </div>
            </div>
          </div>
        </div>
        <div className="col col-xxl-6">
          <div className="d-block d-md-none m-1">
            <DotBotsMap dotbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot)} active={activeDotbot} updateActive={updateActive} showHistory={showDotBotHistory} updateShowHistory={updateShowHistory} mapClicked={mapClicked} mapSize={350} />
          </div>
          <div className="d-none d-md-block m-1">
            <DotBotsMap dotbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot)} active={activeDotbot} updateActive={updateActive} showHistory={showDotBotHistory} updateShowHistory={updateShowHistory} mapClicked={mapClicked} mapSize={650} />
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
                  .map(dotbot =>
                    <SailBotItem
                      key={dotbot.address}
                      dotbot={dotbot}
                      active={activeDotbot}
                      updateActive={updateActive}
                      updateAutoMode={updateAutoMode}
                      applyWaypoints={applyWaypoints}
                      clearWaypoints={clearWaypoints}
                      refresh={fetchDotBots}
                    />
                  )
                }
              </div>
            </div>
          </div>
        </div>
        <div className="col col-xxl-6">
          <div className="d-block d-md-none m-1">
            <SailBotsMap sailbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.SailBot)} active={activeDotbot} showHistory={showSailBotHistory} updateShowHistory={updateShowHistory} mapClicked={mapClicked} mapSize={350} />
          </div>
          <div className="d-none d-md-block m-1">
            <SailBotsMap sailbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.SailBot)} active={activeDotbot} showHistory={showSailBotHistory} updateShowHistory={updateShowHistory} mapClicked={mapClicked} mapSize={650} />
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
