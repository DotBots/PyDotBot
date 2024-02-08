import { useEffect, useState } from "react";
import { RgbColorPicker } from "react-colorful";
import { Joystick } from "./Joystick";
import { dotbotStatuses, dotbotBadgeStatuses } from "./utils/constants";

import logger from './utils/logger';
const log = logger.child({module: 'dotbot-item'});

export const DotBotItem = ({dotbot, publishCommand, updateActive, applyWaypoints, clearWaypoints, updateWaypointThreshold, clearPositionsHistory}) => {

  const [ expanded, setExpanded ] = useState(false);
  const [ color, setColor ] = useState({ r: 0, g: 0, b: 0 });

  const applyColor = async () => {
    log.info(`Applying color ${color.r}, ${color.g}, ${color.b}`);
    await publishCommand(dotbot.address, dotbot.application, "rgb_led", { red: color.r, green: color.g, blue: color.b });
  }

  const thresholdUpdate = async (event) => {
    updateWaypointThreshold(dotbot.address, parseInt(event.target.value));
  };

  let rgbColor = "rgb(0, 0, 0)"
  if (dotbot.rgb_led) {
    rgbColor = `rgb(${dotbot.rgb_led.red}, ${dotbot.rgb_led.green}, ${dotbot.rgb_led.blue})`
  }

  useEffect(() => {
    if (dotbot.rgb_led) {
      setColor({ r: dotbot.rgb_led.red, g: dotbot.rgb_led.green, b: dotbot.rgb_led.blue })
    } else {
      setColor({ r: 0, g: 0, b: 0 })
    }

    // Add collapse/expand event listener to avoid weird effects with the joystick
    let collapsibleElement = document.getElementById(`collapse-${dotbot.address}`)
    collapsibleElement.addEventListener('hide.bs.collapse', () => {
      setExpanded(false);
    })
    collapsibleElement.addEventListener('shown.bs.collapse', () => {
      setExpanded(true);
    })
  }, [dotbot.address, dotbot.rgb_led, setColor, setExpanded]);

  return (
    <div className="accordion-item">
      <h2 className="accordion-header" id={`heading-${dotbot.address}`}>
        <button className="accordion-button collapsed" onClick={() => updateActive(dotbot.address)} type="button" data-bs-toggle="collapse" data-bs-target={`#collapse-${dotbot.address}`} aria-controls={`collapse-${dotbot.address}`}>
          <div className="d-flex" style={{ width: '100%' }}>
            <div className="me-2">
              <svg style={{ height: '12px', width: '12px'}}>
                <circle cx={5} cy={5} r={5} fill={rgbColor} opacity={`${dotbot.status === 0 ? "100%" : "30%"}`} />
              </svg>
            </div>
            <div className="me-auto">{dotbot.address}</div>
            <div className="me-2">
              <div className={`badge text-bg-${dotbotBadgeStatuses[dotbot.status]} text-light border-0`}>
                {dotbotStatuses[dotbot.status]}
              </div>
            </div>
          </div>
        </button>
      </h2>
      <div id={`collapse-${dotbot.address}`} className="accordion-collapse collapse" aria-labelledby={`heading-${dotbot.address}`} data-bs-parent="#accordion-dotbots">
        <div className="accordion-body">
          <div className="d-flex">
            <div className={`mx-auto justify-content-center ${!expanded && "invisible"}`}>
              <Joystick address={dotbot.address} application={dotbot.application} publishCommand={publishCommand} />
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
          {dotbot.waypoints && dotbot.waypoints.length > 0 &&
          <>
            <div className="d-flex mx-auto card">
              <div className="card-body p-1">
                <p className="m-0 p-0">
                  <span>Autonomous mode: </span>
                  <button className="btn btn-primary btn-sm m-1" onClick={async () => applyWaypoints(dotbot.address, dotbot.application)}>Start</button>
                  <button className="btn btn-primary btn-sm m-1" onClick={async () => clearWaypoints(dotbot.address, dotbot.application)}>Clear</button>
                </p>
                <div className="mx-auto justify-content-center">
                  <p>{`Target threshold: ${dotbot.waypoints_threshold}`}</p>
                  <input type="range" min="0" max="100" defaultValue={dotbot.waypoints_threshold} onChange={thresholdUpdate}/>
                </div>
              </div>
            </div>
          </>
          }
          {dotbot.position_history && dotbot.position_history.length > 0 &&
            <div className="d-flex me-auto">
              <button className="btn btn-primary btn-sm m-1" onClick={async () => clearPositionsHistory(dotbot.address)}>Clear positions history</button>
            </div>
          }
        </div>
      </div>
    </div>
  )
}
