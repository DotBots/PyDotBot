import React from "react";
import { useCallback, useEffect, useState } from "react";

import {
    apiFetchLH2CalibrationState, apiApplyLH2Calibration, apiAddLH2CalibrationPoint
} from "./rest";

const referencePoints = [
  {x: -0.2, y: 0.2},
  {x: 0.2, y: 0.2},
  {x: -0.2, y: -0.2},
  {x: 0.2, y: -0.2},
]

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

export const DotBotsMap = (props) => {

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
    return 200 * (1 + coordinate) - 5;
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
                  {referencePoints.map((point, index) => <rect key={index} x={coordinateToPixel(point.x)} y={coordinateToPixel(point.y * -1)} width="10" height="10" fill={pointsChecked[index] ? "green" : "grey"} onClick={() => pointClicked(index)} />)}
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
