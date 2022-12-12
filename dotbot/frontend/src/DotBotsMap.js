import React from "react";
import { useCallback, useEffect, useState } from "react";

import {
    apiFetchLH2CalibrationState, apiApplyLH2Calibration,
    apiAddLH2CalibrationPoint, inactiveAddress
} from "./rest";

const referencePoints = [
  {x: -0.1, y: 0.1},
  {x: 0.1, y: 0.1},
  {x: -0.1, y: -0.1},
  {x: 0.1, y: -0.1},
]

const DotBotsMapPoint = (props) => {
  const [hovered, setHovered ] = useState(false);

  let rgbColor = "rgb(0, 0, 0)"
  if (props.dotbot.rgb_led) {
    rgbColor = `rgb(${props.dotbot.rgb_led.red}, ${props.dotbot.rgb_led.green}, ${props.dotbot.rgb_led.blue})`
  }

  const posX = props.mapSize * parseFloat(props.dotbot.lh2_position.x);
  const posY = props.mapSize * parseFloat(props.dotbot.lh2_position.y);

  const onMouseEnter = () => {
    if (props.dotbot.status !== 0) {
      return;
    }

    setHovered(true);
  };

  const onMouseLeave = () => {
    setHovered(false);
  };

  return (
    <>
    { (props.dotbot.address === props.active) &&
      <circle cx={posX} cy={posY} r="8" stroke="black" strokeWidth="2" fill="none" />
    }
    <circle cx={posX} cy={posY}
        r={(props.dotbot.address === props.active || hovered) ? 8: 5}
        opacity={`${props.dotbot.status === 0 ? "80%" : "20%"}`}
        fill={rgbColor}
        style={{ cursor: "pointer" }}
        onClick={
          () => {
            props.updateActive(props.dotbot.address === props.active ? inactiveAddress : props.dotbot.address)
          }
        }
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave} >
      <title>{`${props.dotbot.address}@${posX}x${posY}`}</title>
    </circle>
    </>
  )
}

export const DotBotsMap = (props) => {

  const [ displayGrid, setDisplayGrid ] = useState(true);
  const [ calibrationFetched, setCalibrationFetched ] = useState(false);
  const [ calibrationState, setCalibrationState ] = useState("unknown");
  const [ pointsChecked, setPointsChecked ] = useState([false, false, false, false]);

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
      setPointsChecked([false, false, false, false]);
      setCalibrationState("running");
    } else if (calibrationState === "ready") {
      setCalibrationState("done");
      apiApplyLH2Calibration();
    }
  };

  const coordinateToPixel = (coordinate) => {
    return mapSize * (coordinate + 0.5) - 5;
  };

  const updateDisplayGrid = (event) => {
    setDisplayGrid(event.target.checked);
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

  const mapSize = props.mapSize;
  const gridSize = `${mapSize + 1}px`;
  const calibrationTextWidth = `${mapSize}px`;

  return (
    <div className={`${props.dotbots && props.dotbots.length > 0 ? "visible" : "invisible"}`}>
      <div className="row justify-content-center">
        <div className="col d-flex justify-content-center">
          <div style={{ height: gridSize, width: gridSize }}>
            <svg style={{ height: gridSize, width: gridSize }}>
              <defs>
                <pattern id={`smallGrid${mapSize}`} width={`${mapSize / 50}`} height={`${mapSize / 50}`} patternUnits="userSpaceOnUse">
                  <path d={`M ${mapSize / 50} 0 L 0 0 0 ${mapSize / 50}`} fill="none" stroke="gray" strokeWidth="0.5"/>
                </pattern>
                <pattern id={`grid${mapSize}`} width={`${mapSize / 5}`} height={`${mapSize / 5}`} patternUnits="userSpaceOnUse">
                  <rect width={`${mapSize / 5}`} height={`${mapSize / 5}`} fill={`url(#smallGrid${mapSize})`}/>
                  <path d={`M ${mapSize / 5} 0 L 0 0 0 ${mapSize / 5}`} fill="none" stroke="gray" strokeWidth="1"/>
                </pattern>
              </defs>
              {/* Map grid */}
              <rect width="100%" height="100%" fill={displayGrid ? `url(#grid${mapSize})`: "none"} stroke="gray" strokeWidth="1"/>
              {/* DotBots points */}
              {
                props.dotbots && props.dotbots
                  .filter(dotbot => dotbot.lh2_position)
                  .filter(dotbot => dotbot.status !== 2)
                  .map(dotbot => <DotBotsMapPoint key={dotbot.address} dotbot={dotbot} active={props.active} updateActive={props.updateActive} mapSize={props.mapSize} />)
              }
              {
                ["running", "ready"].includes(calibrationState) && (
                  <>
                  {referencePoints.map((point, index) => (
                    <rect key={index} x={coordinateToPixel(point.x)} y={coordinateToPixel(point.y * -1)} width="10" height="10" fill={pointsChecked[index] ? "green" : "grey"} style={{ cursor: "pointer" }} onClick={() => pointClicked(index)}><title>{index + 1}</title></rect>
                  ))}
                  </>
                )
              }
            </svg>
          </div>
        </div>
      </div>
      <div className="card m-1">
        <div className="card-header">Map settings</div>
        <div className="card-body">
          <div className="d-flex mb-2">
            <div className="form-check">
              <input className="form-check-input" type="checkbox" id="flexCheckDisplayGrid" defaultChecked={displayGrid} onChange={updateDisplayGrid} />
              <label className="form-check-label" htmlFor="flexCheckDisplayGrid">Display grid</label>
            </div>
          </div>
          <div className="d-flex">
            <button className={`btn btn-sm ${calibrationButtonClass}`} onClick={calibrateClicked}>{calibrationButtonLabel}</button>
          </div>
          {calibrationState === "running" && (
          <div className="d-flex">
            <p style={{ width: calibrationTextWidth }}>
              Place a DotBot on the marks on the ground and once done, click the corresponding rectangle on the grid. Repeat the operation for each marks.
              Once all rectangles are green, click "Apply calibration".
            </p>
          </div>
          )}
        </div>
      </div>
    </div>
  )
}
