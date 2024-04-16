import { useEffect, useState } from "react";
import useInterval from "use-interval";
import { RgbColorPicker } from "react-colorful";
import { ApplicationType, dotbotStatuses, dotbotBadgeStatuses } from "./utils/constants";


export const SailBotItem = ({dotbot, publishCommand, updateActive, applyWaypoints, clearWaypoints, updateWaypointThreshold, clearPositionsHistory}) => {

  const [rudderValue, setRudderValue] = useState(0);
  const [sailValue, setSailValue] = useState(0);
  const [active, setActive] = useState(true);
  const [color, setColor] = useState({ r: 0, g: 0, b: 0 });
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('0'); // used for editing the value as a string

  const applyColor = async () => {
    await publishCommand(dotbot.address, dotbot.application, "rgb_led", { red: color.r, green: color.g, blue: color.b });
  }

  const handleTextClick = () => {
    setIsEditing(true);
    setEditValue(rudderValue.toString());
  };

  const clampValue = (value) => {
    const num = parseInt(value, 10);
    if (isNaN(num)) return 0;
    return Math.min(Math.max(num, -128), 127);
  };

  const handleInputChange = (event) => {
    setEditValue(event.target.value);
  };

  const handleInputConfirm = () => {
    const newValue = clampValue(editValue);
    rudderUpdate(newValue);
    setIsEditing(false);
  };

  const handleInputBlur = () => handleInputConfirm();
  const handleKeyPress = (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      handleInputConfirm();
    }
  };

  const rudderUpdate = async (event) => {
    let newRudderValue;
    if (typeof event === 'object' && event.target) {
      newRudderValue = parseInt(event.target.value, 10);
    } else if (typeof event === 'number') {
      newRudderValue = event;
    } else {
      return;
    }
    setRudderValue(newRudderValue);
    setActive(newRudderValue !== undefined && newRudderValue !== null);
  };

  const sailUpdate = async (event) => {
    const newSailValue = parseInt(event.target.value);
    setSailValue(newSailValue);
    setActive(newSailValue !== undefined && newSailValue !== null);
  };

  const thresholdUpdate = async (event) => {
    updateWaypointThreshold(dotbot.address, parseInt(event.target.value));
  };

  useInterval(async () => {
    if (rudderValue === 0 && sailValue === 0) {
      setActive(false);
    }
    await publishCommand(dotbot.address, dotbot.application, "move_raw", { left_x: rudderValue, left_y: 0, right_x: 0, right_y: sailValue });
  }, active ? 100 : null);

  useEffect(() => {
    if (dotbot.rgb_led) {
      setColor({ r: dotbot.rgb_led.red, g: dotbot.rgb_led.green, b: dotbot.rgb_led.blue })
    } else {
      setColor({ r: 0, g: 0, b: 0 })
    }
  }, [dotbot.rgb_led, setColor]);

  return (
    <div className="accordion-item">
      <h2 className="accordion-header" id={`heading-${dotbot.address}`}>
        <button className="accordion-button collapsed" onClick={() => updateActive(dotbot.address)} type="button" data-bs-toggle="collapse" data-bs-target={`#collapse-${dotbot.address}`} aria-controls={`collapse-${dotbot.address}`}>
          <div className="d-flex" style={{ width: '100%' }}>
            <div className="me-auto">{dotbot.address}</div>
            <div className="me-2">
              <div className={`badge text-bg-${dotbotBadgeStatuses[dotbot.status]} text-light border-0`}>
                {dotbotStatuses[dotbot.status]}
              </div>
            </div>
          </div>
        </button>
      </h2>
      <div id={`collapse-${dotbot.address}`} className="accordion-collapse collapse" aria-labelledby={`heading-${dotbot.address}`} data-bs-parent="#accordion-sailbots">
        <div className="accordion-body">
          <div className="d-flex">
            <div className="mx-auto justify-content-center">
              {isEditing ? (
                <input
                  type="text"
                  value={editValue}
                  onChange={handleInputChange}
                  onBlur={handleInputBlur}
                  onKeyPress={handleKeyPress}
                  autoFocus
                />
              ) : (
                <p onClick={handleTextClick}>{`Rudder: ${rudderValue}`}</p>
              )}
              <input
                type="range" min="-128" max="127" value={rudderValue} onChange={rudderUpdate}
              />
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
          {dotbot.waypoints && dotbot.waypoints.length > 0 &&
            <>
              <div className="d-flex mx-auto card">
                <div className="card-body p-1">
                  <p className="m-0 p-0">
                    <span>Autonomous mode: </span>
                    <button className="btn btn-primary btn-sm m-1" onClick={async () => applyWaypoints(dotbot.address, ApplicationType.SailBot)}>Start</button>
                    <button className="btn btn-primary btn-sm m-1" onClick={async () => clearWaypoints(dotbot.address, ApplicationType.SailBot)}>Stop</button>
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
  );
}
