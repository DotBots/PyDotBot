import React from "react";
import { useCallback, useEffect, useState } from "react";
import { RgbColorPicker } from "react-colorful";
import useWebSocket from 'react-use-websocket';

import { Joystick } from "./Joystick";
import { DotBotsMap } from "./DotBotsMap";
import {
  apiUpdateActiveDotbotAddress, apiFetchActiveDotbotAddress,
  apiFetchDotbots, apiUpdateRgbLed
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
      {dotbots && dotbots.length > 0 && (
      <>
      <div className="row">
        <div className="col col-md-6">
          <div className="card m-1">
            <div className="card-header">Available DotBots</div>
            <div className="card-body p-1">
              <div className="accordion accordion-flush" id="accordion-dotbots">
                {dotbots && dotbots.map(dotbot => <DotBotAccordionItem key={dotbot.address} dotbot={dotbot} active={activeDotbot} updateActive={updateActive} refresh={fetchDotBots} />)}
              </div>
            </div>
          </div>
        </div>
        <div className="col col-md-6">
          <div className="m-1">
            <DotBotsMap dotbots={dotbots} active={activeDotbot} mapSize={650} />
           </div>
        </div>
      </div>
      </>
      )}
    </div>
    </>
  );
}

export default DotBots;
