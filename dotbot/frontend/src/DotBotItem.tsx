import React, { useEffect, useState } from "react";
import { RgbColorPicker } from "react-colorful";
import { Joystick } from "./Joystick";
import { dotbotStatuses, dotbotBadgeStatuses } from "./utils/constants";
import { DotBot, PublishCommandFn } from "./types";

import logger from './utils/logger';
const log = logger.child({ module: 'DotBotItem' });

interface RgbColor {
  r: number;
  g: number;
  b: number;
}

interface DotBotItemProps {
  dotbot: DotBot;
  publishCommand: PublishCommandFn;
  updateActive: (address: string) => void;
  applyWaypoints: (address: string, application: number) => Promise<void>;
  clearWaypoints: (address: string, application: number) => Promise<void>;
  updateWaypointThreshold: (address: string, threshold: number) => void;
  clearPositionsHistory: (address: string) => Promise<void>;
}

export const DotBotItem: React.FC<DotBotItemProps> = ({
  dotbot,
  publishCommand,
  updateActive,
  applyWaypoints,
  clearWaypoints,
  updateWaypointThreshold,
  clearPositionsHistory,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [color, setColor] = useState<RgbColor>({ r: 0, g: 0, b: 0 });

  const applyColor = async (): Promise<void> => {
    log.info(`Applying color ${color.r}, ${color.g}, ${color.b}`);
    await publishCommand(dotbot.address, dotbot.application, "rgb_led", { red: color.r, green: color.g, blue: color.b });
  };

  const thresholdUpdate = (event: React.ChangeEvent<HTMLInputElement>): void => {
    updateWaypointThreshold(dotbot.address, parseInt(event.target.value));
  };

  let rgbColor = "rgb(0, 0, 0)";
  if (dotbot.rgb_led) {
    rgbColor = `rgb(${dotbot.rgb_led.red}, ${dotbot.rgb_led.green}, ${dotbot.rgb_led.blue})`;
  }

  useEffect(() => {
    if (dotbot.rgb_led) {
      setColor({ r: dotbot.rgb_led.red, g: dotbot.rgb_led.green, b: dotbot.rgb_led.blue });
    } else {
      setColor({ r: 0, g: 0, b: 0 });
    }

    const collapsibleElement = document.getElementById(`collapse-${dotbot.address}`);
    if (collapsibleElement) {
      collapsibleElement.addEventListener('hide.bs.collapse', () => {
        setExpanded(false);
      });
      collapsibleElement.addEventListener('shown.bs.collapse', () => {
        setExpanded(true);
      });
    }
  }, [dotbot.address, dotbot.rgb_led, setColor, setExpanded]);

  const batteryLevel = parseFloat(String(dotbot.battery ?? 0));
  let batteryIcon = "bi-battery-full";
  let batteryBadgeClass = "success";
  let batteryTextColorClass = "text-light";
  if (batteryLevel < 2) {
    batteryIcon = "bi-battery";
    batteryBadgeClass = "danger";
    batteryTextColorClass = "text-warning";
  } else if (batteryLevel < 2.25) {
    batteryIcon = "bi-battery-low";
    batteryBadgeClass = "warning";
    batteryTextColorClass = "text-danger";
  } else if (batteryLevel < 2.75) {
    batteryIcon = "bi-battery-half";
    batteryBadgeClass = "primary";
  }

  return (
    <div className="accordion-item">
      <h2 className="accordion-header" id={`heading-${dotbot.address}`}>
        <button
          className="accordion-button collapsed"
          onClick={() => updateActive(dotbot.address)}
          type="button"
          data-bs-toggle="collapse"
          data-bs-target={`#collapse-${dotbot.address}`}
          aria-controls={`collapse-${dotbot.address}`}
        >
          <div className="d-flex flex-wrap" style={{ width: '100%' }}>
            <div className="me-2">
              <svg style={{ height: '12px', width: '12px' }}>
                <circle cx={5} cy={5} r={5} fill={rgbColor} opacity={`${dotbot.status === 0 ? "100%" : "30%"}`} />
              </svg>
            </div>
            <div className="me-auto">{dotbot.address.slice(-6)}</div>
            <div className="me-2">
              <div className={`badge text-bg-${batteryBadgeClass} ${batteryTextColorClass} border-0 me-1`}>
                <i className={`bi ${batteryIcon}`}></i>&nbsp;{`${(dotbot.battery ?? 0).toFixed(1)}V`}
              </div>
              <div className={`badge text-bg-${dotbotBadgeStatuses[dotbot.status]} text-light border-0`}>
                {dotbotStatuses[dotbot.status]}
              </div>
            </div>
          </div>
        </button>
      </h2>
      <div
        id={`collapse-${dotbot.address}`}
        className="accordion-collapse collapse"
        aria-labelledby={`heading-${dotbot.address}`}
        data-bs-parent="#accordion-dotbots"
      >
        <div className="accordion-body">
          <div className="d-flex flex-wrap">
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
          {dotbot.waypoints && dotbot.waypoints.length > 0 && (
            <>
              <div className="d-flex mx-auto card">
                <div className="card-body p-1">
                  <div className="m-0 p-0">
                    <div>Autonomous navigation</div>
                    <button className="btn btn-primary btn-sm m-1" onClick={async () => applyWaypoints(dotbot.address, dotbot.application)}>Start</button>
                    <button className="btn btn-primary btn-sm m-1" onClick={async () => clearWaypoints(dotbot.address, dotbot.application)}>Clear</button>
                  </div>
                  <div className="mx-auto justify-content-center">
                    <p>{`Target threshold: ${dotbot.waypoints_threshold}`}</p>
                    <input type="range" min="0" max="1000" defaultValue={dotbot.waypoints_threshold} onChange={thresholdUpdate} />
                  </div>
                </div>
              </div>
            </>
          )}
          {dotbot.position_history && dotbot.position_history.length > 0 && (
            <div className="d-flex me-auto">
              <button className="btn btn-primary btn-sm m-1" onClick={async () => clearPositionsHistory(dotbot.address)}>Clear positions history</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
