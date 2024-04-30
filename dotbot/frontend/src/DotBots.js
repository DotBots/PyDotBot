import React from "react";
import { useCallback, useEffect, useState } from "react";

import { useKeyPress } from "./hooks/keyPress";
import { DotBotItem } from "./DotBotItem";
import { DotBotsMap } from "./DotBotsMap";
import { SailBotItem } from "./SailBotItem";
import { SailBotsMap } from "./SailBotsMap";
import { XGOItem } from "./XGOItem";
import { ApplicationType, inactiveAddress, maxWaypoints, maxPositionHistory } from "./utils/constants";


const DotBots = ({ dotbots, updateDotbots, publishCommand, publish, calibrationState, updateCalibrationState }) => {
  const [ activeDotbot, setActiveDotbot ] = useState(inactiveAddress);
  const [ showDotBotHistory, setShowDotBotHistory ] = useState(true);
  const [ dotbotHistorySize, setDotbotHistorySize ] = useState(maxPositionHistory);
  const [ showSailBotHistory, setShowSailBotHistory ] = useState(true);

  const control = useKeyPress("Control");
  const enter = useKeyPress("Enter")
  const backspace = useKeyPress("Backspace");

  const updateActive = useCallback(async (address) => {
    setActiveDotbot(address);
  }, [setActiveDotbot]
  );

  const updateShowHistory = (show, application) => {
    if (application === ApplicationType.SailBot) {
      setShowSailBotHistory(show);
    } else {
      setShowDotBotHistory(show);
    }
  };

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
          updateDotbots(dotbotsTmp);
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
          updateDotbots(dotbotsTmp);
        }
      }
    }
  }, [activeDotbot, dotbots, updateDotbots]
  );

  const applyWaypoints = useCallback(async (address, application) => {
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        await publishCommand(address, application, "waypoints", { threshold: dotbots[idx].waypoints_threshold, waypoints: dotbots[idx].waypoints });
        return;
      }
    }
  }, [dotbots, publishCommand]
  );

  const clearWaypoints = useCallback(async (address, application) => {
    let dotbotsTmp = dotbots.slice();
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        dotbotsTmp[idx].waypoints = [];
        await publishCommand(address, application, "waypoints", { threshold: dotbots[idx].waypoints_threshold, waypoints: [] });
        updateDotbots(dotbotsTmp);
        return;
      }
    }
  }, [dotbots, updateDotbots, publishCommand]
  );

  const clearPositionsHistory = async (address) => {
    let dotbotsTmp = dotbots.slice();
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        dotbotsTmp[idx].position_history = [];
        await publishCommand(address, dotbots[idx].application, "clear_position_history", "");
        updateDotbots(dotbotsTmp);
        return;
      }
    }
  };

  const updateWaypointThreshold = (address, threshold) => {
    let dotbotsTmp = dotbots.slice();
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        dotbotsTmp[idx].waypoints_threshold = threshold;
        updateDotbots(dotbotsTmp);
        return;
      }
    }
  };

  useEffect(() => {

    if (dotbots && control && enter) {
      if (activeDotbot !== inactiveAddress) {
        for (let idx = 0; idx < dotbots.length; idx++) {
          if (dotbots[idx].address === activeDotbot) {
            applyWaypoints(activeDotbot, dotbots[idx].application);
            break;
          }
        }
      }
    }
    if (dotbots && control && backspace) {
      if (activeDotbot !== inactiveAddress) {
        for (let idx = 0; idx < dotbots.length; idx++) {
          if (dotbots[idx].address === activeDotbot) {
            clearWaypoints(activeDotbot, dotbots[idx].application);
            break;
          }
        }
      }
    }
  }, [
    dotbots,
    control, enter, backspace,
    applyWaypoints, clearWaypoints, activeDotbot
  ]);

  return (
    <>
    <nav className="navbar navbar-dark navbar-expand-lg bg-dark">
      <div className="container-fluid">
        <a className="navbar-brand text-light" href="http://www.dotbots.org">The DotBots project</a>
        <button className="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
          <span className="navbar-toggler-icon"></span>
        </button>
        {/* <div className="collapse navbar-collapse" id="navbarNav">
          <ul className="navbar-nav">
            <li className="nav-item">
              <a className="nav-link active" aria-current="page" href="http://localhost:8000/api" target="_blank" rel="noreferrer noopener">API</a>
            </li>
          </ul>
        </div> */}
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
                    <DotBotItem
                      key={dotbot.address}
                      dotbot={dotbot}
                      updateActive={updateActive}
                      applyWaypoints={applyWaypoints}
                      clearWaypoints={clearWaypoints}
                      clearPositionsHistory={clearPositionsHistory}
                      updateWaypointThreshold={updateWaypointThreshold}
                      publishCommand={publishCommand}
                    />
                  )
                }
              </div>
            </div>
          </div>
        </div>
        <div className="col col-xxl-6">
          <div className="d-block d-md-none m-1">
            <DotBotsMap
              dotbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot)}
              active={activeDotbot}
              updateActive={updateActive}
              showHistory={showDotBotHistory}
              updateShowHistory={updateShowHistory}
              historySize={dotbotHistorySize}
              setHistorySize={setDotbotHistorySize}
              mapClicked={mapClicked}
              mapSize={350}
              publish={publish}
              calibrationState={calibrationState}
              updateCalibrationState={updateCalibrationState}
            />
          </div>
          <div className="d-none d-md-block m-1">
            <DotBotsMap
              dotbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot)}
              active={activeDotbot}
              updateActive={updateActive}
              showHistory={showDotBotHistory}
              updateShowHistory={updateShowHistory}
              historySize={dotbotHistorySize}
              setHistorySize={setDotbotHistorySize}
              mapClicked={mapClicked}
              mapSize={650}
              publish={publish}
              calibrationState={calibrationState}
              updateCalibrationState={updateCalibrationState}
            />
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
                      updateActive={updateActive}
                      applyWaypoints={applyWaypoints}
                      clearWaypoints={clearWaypoints}
                      clearPositionsHistory={clearPositionsHistory}
                      updateWaypointThreshold={updateWaypointThreshold}
                      publishCommand={publishCommand}
                    />
                  )
                }
              </div>
            </div>
          </div>
        </div>
        <div className="col col-xxl-6">
          <div className="d-block d-md-none m-1">
            <SailBotsMap
              sailbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.SailBot)}
              active={activeDotbot}
              showHistory={showSailBotHistory}
              updateShowHistory={updateShowHistory}
              mapClicked={mapClicked}
              mapSize={350}
            />
          </div>
          <div className="d-none d-md-block m-1">
            <SailBotsMap
              sailbots={dotbots.filter(dotbot => dotbot.application === ApplicationType.SailBot)}
              active={activeDotbot}
              showHistory={showSailBotHistory}
              updateShowHistory={updateShowHistory}
              mapClicked={mapClicked}
              mapSize={650}
            />
          </div>
        </div>
      </div>
      }
      {dotbots.filter(dotbot => dotbot.application === ApplicationType.XGO).length > 0 &&
      <div className="row">
        <div className="col">
          <div className="card m-1">
            <div className="card-header">Available XGO</div>
            <div className="card-body p-1">
              <div className="accordion" id="accordion-xgo">
                {dotbots
                  .filter(dotbot => dotbot.application === ApplicationType.XGO)
                  .map(dotbot =>
                    <XGOItem
                      key={dotbot.address}
                      dotbot={dotbot}
                      updateActive={updateActive}
                      publishCommand={publishCommand}
                    />
                  )
                }
              </div>
            </div>
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
