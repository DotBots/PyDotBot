import React from "react";
import { useCallback, useEffect, useState } from "react";
import { RgbColorPicker } from "react-colorful";
import useWebSocket from 'react-use-websocket';

import { Joystick } from "./Joystick";
import {
  apiUpdateActiveDotbotAddress, apiFetchActiveDotbotAddress,
  apiFetchDotbots, apiUpdateRgbLed,
  apiFetchLH2CalibrationState, apiApplyLH2Calibration, apiAddLH2CalibrationPoint
} from "./rest";


const websocketUrl = `${process.env.REACT_APP_DOTBOTS_WS_URL}/controller/ws/status`;
const inactiveAddress = "0000000000000000";

const DotBotAccordionItem = (props) => {

  const [ expanded, setExpanded ] = useState(false);
  const [ color, setColor ] = useState({ r: 0, g: 0, b: 0 });

  const applyColor = async () => {
    await apiUpdateRgbLed(props.dotbot.address, color.r, color.g, color.b);
    await props.refresh();
  }

  let rgbColor = "rgb(0, 0, 0)"
  if (props.dotbot.rgb_led) {
    rgbColor = `rgb(${props.dotbot.rgb_led.red}, ${props.dotbot.rgb_led.green}, ${props.dotbot.rgb_led.blue})`
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
                <circle cx={5} cy={5} r={5} fill={rgbColor} />
              </svg>
            </div>
            <div className="me-auto">{props.dotbot.address}</div>
            <div className="me-2">
            {
              props.dotbot.address === props.active ? (
                <div className="badge text-bg-success text-light border-0" onClick={() => props.updateActive(props.dotbot.address)}>active</div>
              ) : (
                <div className="badge text-bg-primary text-light border-0" onClick={() => props.updateActive(props.dotbot.address)}>activate</div>
              )
            }
            </div>
          </div>
        </button>
      </h2>
      <div id={`collapse-${props.dotbot.address}`} className="accordion-collapse collapse" aria-labelledby={`heading-${props.dotbot.address}`} data-bs-parent="#accordion-dotbots">
        <div className="accordion-body">
          <div className="row">
            <div className={`col d-flex justify-content-center ${!expanded && "invisible"}`}>
              <Joystick address={props.dotbot.address} />
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
  )
}

const DotBotsMapPoint = (props) => {
  let rgbColor = "rgb(0, 0, 0)"
  if (props.dotbot.rgb_led) {
    rgbColor = `rgb(${props.dotbot.rgb_led.red}, ${props.dotbot.rgb_led.green}, ${props.dotbot.rgb_led.blue})`
  }

  return (
    <>
    { (props.dotbot.address === props.active) &&
      <circle cx={200 * (1 + parseFloat(props.dotbot.lh2_position.x))} cy={200 * (1 + parseFloat(props.dotbot.lh2_position.y))} r="8" stroke="black" strokeWidth="2" fill="none" />
    }
    <circle cx={200 * (1 + parseFloat(props.dotbot.lh2_position.x))} cy={200 * (1 + parseFloat(props.dotbot.lh2_position.y))} r={props.dotbot.address === props.active ? 8: 5} opacity="80%" fill={rgbColor} />
    </>
  )
}

const DotBotsMap = (props) => {

  const [ calibrationFetched, setCalibrationFetched ] = useState(false);
  const [ calibrationState, setCalibrationState ] = useState("unknown");
  const [ pointsChecked, setPointsChecked ] = useState([false, false, false, false, false, false, false, false, false]);

  const fetchCalibrationState = useCallback(async () => {
    const state = await apiFetchLH2CalibrationState().catch((error) => console.error(error));
    setCalibrationState(state.state);
    setCalibrationFetched(true);
  }, [setCalibrationFetched, setCalibrationState]
  );

  const pointClicked = (index) => {
    let pointsCheckedTmp = pointsChecked.slice();
    pointsCheckedTmp[index] = true;
    setPointsChecked(pointsCheckedTmp);
    apiAddLH2CalibrationPoint(index);
  };

  const calibrateClicked = () => {
    if (["unknown", "done"].includes(calibrationState)) {
      setPointsChecked([false, false, false, false, false, false, false, false, false]);
      setCalibrationState("running");
    } else if (calibrationState === "ready") {
      setCalibrationState("done");
      apiApplyLH2Calibration();
    }
  };

  useEffect(() => {
    if (!calibrationFetched) {
      fetchCalibrationState();
    }
    if (pointsChecked.every(v => v === true)) {
      setCalibrationState("ready");
    }
  }, [calibrationFetched, fetchCalibrationState, pointsChecked, setCalibrationState]);

  let calibrationButtonLabel = "Start calibration";
  let calibrationButtonClass = "btn-primary";
  if (calibrationState === "running") {
    calibrationButtonLabel = <><span className="spinner-border spinner-border-sm text-light me-2 mt-1" role="status"></span>Calibration in progress...</>;
    calibrationButtonClass = "btn-secondary disabled";
  } else if (calibrationState === "ready") {
    calibrationButtonLabel = "Apply calibration";
    calibrationButtonClass = "btn-success";
  } else if (calibrationState === "done") {
    calibrationButtonLabel = "Update calibration";
  }

  return (
    <div className={`${props.dotbots && props.dotbots.length > 0 ? "visible" : "invisible"}`}>
      <div className="row justify-content-center">
        <div className="col d-flex justify-content-center">
          <div style={{ height: '401px', width: '401px' }}>
            <svg style={{ height: '401px', width: '401px'}}>
              <defs>
                <pattern id="smallGrid" width="8" height="8" patternUnits="userSpaceOnUse">
                  <path d="M 8 0 L 0 0 0 8" fill="none" stroke="gray" strokeWidth="0.5"/>
                </pattern>
                <pattern id="grid" width="80" height="80" patternUnits="userSpaceOnUse">
                  <rect width="80" height="80" fill="url(#smallGrid)"/>
                  <path d="M 80 0 L 0 0 0 80" fill="none" stroke="gray" strokeWidth="1"/>
                </pattern>
              </defs>
              {/* Map grid */}
              <rect width="100%" height="100%" fill="url(#grid)" />
              {/* DotBots points */}
              {
                props.dotbots && props.dotbots
                  .filter(dotbot => dotbot.lh2_position)
                  .map(dotbot => <DotBotsMapPoint key={dotbot.address} dotbot={dotbot} active={props.active}/>)
              }
              {
                ["running", "ready"].includes(calibrationState) && (
                  <>
                  <rect x="160" y="160" width="10" height="10" fill={pointsChecked[0] ? "green" : "grey"} onClick={() => pointClicked(0)} />
                  <rect x="195" y="160" width="10" height="10" fill={pointsChecked[1] ? "green" : "grey"} onClick={() => pointClicked(1)} />
                  <rect x="230" y="160" width="10" height="10" fill={pointsChecked[2] ? "green" : "grey"} onClick={() => pointClicked(2)} />
                  <rect x="160" y="195" width="10" height="10" fill={pointsChecked[3] ? "green" : "grey"} onClick={() => pointClicked(3)} />
                  <rect x="195" y="195" width="10" height="10" fill={pointsChecked[4] ? "green" : "grey"} onClick={() => pointClicked(4)} />
                  <rect x="230" y="195" width="10" height="10" fill={pointsChecked[5] ? "green" : "grey"} onClick={() => pointClicked(5)} />
                  <rect x="160" y="230" width="10" height="10" fill={pointsChecked[6] ? "green" : "grey"} onClick={() => pointClicked(6)} />
                  <rect x="195" y="230" width="10" height="10" fill={pointsChecked[7] ? "green" : "grey"} onClick={() => pointClicked(7)} />
                  <rect x="230" y="230" width="10" height="10" fill={pointsChecked[8] ? "green" : "grey"} onClick={() => pointClicked(8)} />
                  </>
                )
              }
            </svg>
          </div>
        </div>
      </div>
      <div className="row">
        <div className="col d-flex justify-content-center">
          <button className={`btn btn-sm m-1 ${calibrationButtonClass}`} onClick={calibrateClicked}>{calibrationButtonLabel}</button>
        </div>
      </div>
      {calibrationState === "running" && (
      <div className="d-flex justify-content-center">
        <p className="text-center" style={{ width: '400px' }}>
          Place a DotBot on the marks on the ground and once done, click the corresponding rectangle on the grid. Repeat the operation for each marks.
          Once all rectangles are green, click "Apply calibration".
        </p>
      </div>
      )}
    </div>
  )
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
    <nav className="navbar navbar-expand-lg bg-dark">
      <div className="container-fluid">
        <a className="navbar-brand text-light" href="http://www.dotbots.org">DotBots</a>
      </div>
    </nav>
    <div className="container">
      <div className="card m-1">
        <div className="card-header">Available DotBots</div>
        <div className="card-body p-0 mb-1">
          <div className="accordion accordion-flush" id="accordion-dotbots">
            {dotbots && dotbots.map(dotbot => <DotBotAccordionItem key={dotbot.address} dotbot={dotbot} active={activeDotbot} updateActive={updateActive} refresh={fetchDotBots} />)}
          </div>
        </div>
      </div>
      <div className="p-0">
        <DotBotsMap dotbots={dotbots} active={activeDotbot} />
      </div>
    </div>
    </>
  );
}

export default DotBots;
