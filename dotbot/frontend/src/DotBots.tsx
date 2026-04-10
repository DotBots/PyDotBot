import React, { useCallback, useEffect, useState } from "react";

import { useKeyPress } from "./hooks/keyPress";
import { DotBotItem } from "./DotBotItem";
import { DotBotsMap } from "./DotBotsMap";
import { SailBotItem } from "./SailBotItem";
import { SailBotsMap } from "./SailBotsMap";
import { XGOItem } from "./XGOItem";
import { ApplicationType, inactiveAddress, maxWaypoints, maxPositionHistory } from "./utils/constants";
import { AreaSize, BackgroundMap, DotBot, GpsPosition, LH2Position, PublishCommandFn } from "./types";

import logger from './utils/logger';
const log = logger.child({ module: 'DotBots' });

interface DotBotsProps {
  dotbots: DotBot[];
  areaSize: AreaSize;
  backgroundMap?: BackgroundMap;
  updateDotbots: React.Dispatch<React.SetStateAction<DotBot[]>>;
  publishCommand: PublishCommandFn;
  publish: (topic: string, message: unknown) => void;
}

const DotBots: React.FC<DotBotsProps> = ({ dotbots, areaSize, backgroundMap, updateDotbots, publishCommand, publish }) => {
  const [activeDotbot, setActiveDotbot] = useState(inactiveAddress);
  const [showDotBotHistory, setShowDotBotHistory] = useState(true);
  const [dotbotHistorySize, setDotbotHistorySize] = useState(maxPositionHistory);
  const [showSailBotHistory, setShowSailBotHistory] = useState(true);

  const control = useKeyPress("Control");
  const enter = useKeyPress("Enter");
  const backspace = useKeyPress("Backspace");

  const updateActive = useCallback(async (address: string) => {
    log.info(`Updating active dotbot to ${address}`);
    setActiveDotbot(address);
  }, [setActiveDotbot]);

  const updateShowHistory = (show: boolean, application: number): void => {
    if (application === ApplicationType.SailBot) {
      setShowSailBotHistory(show);
    } else {
      setShowDotBotHistory(show);
    }
  };

  const mapClicked = useCallback((x: number, y: number) => {
    if (!dotbots || dotbots.length === 0) return;

    const activeDotbots = dotbots.filter(dotbot => activeDotbot === dotbot.address);
    if (activeDotbots.length === 0) return;

    const dotbot = activeDotbots[0];

    if (dotbot.waypoints.length >= maxWaypoints) return;

    if (dotbot.application === ApplicationType.SailBot) {
      const newWaypoints = [...dotbot.waypoints] as GpsPosition[];
      if (newWaypoints.length === 0 && dotbot.gps_position) {
        newWaypoints.push({
          latitude: dotbot.gps_position.latitude,
          longitude: dotbot.gps_position.longitude,
        });
      }
      newWaypoints.push({ latitude: x, longitude: y });

      updateDotbots(dotbots.map(db =>
        db.address !== dotbot.address ? db : { ...db, waypoints: newWaypoints }
      ));
    }
    if (dotbot.application === ApplicationType.DotBot) {
      const newWaypoints = [...dotbot.waypoints] as LH2Position[];
      if (newWaypoints.length === 0 && dotbot.lh2_position) {
        newWaypoints.push({ x: dotbot.lh2_position.x, y: dotbot.lh2_position.y, z: 0 });
      }
      newWaypoints.push({ x, y, z: 0 });

      updateDotbots(dotbots.map(db =>
        db.address !== dotbot.address ? db : { ...db, waypoints: newWaypoints }
      ));
    }
  }, [activeDotbot, dotbots, updateDotbots]);

  const applyWaypoints = useCallback(async (address: string, application: number) => {
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        await publishCommand(address, application, "waypoints", {
          threshold: dotbots[idx].waypoints_threshold,
          waypoints: dotbots[idx].waypoints,
        });
        return;
      }
    }
  }, [dotbots, publishCommand]);

  const clearWaypoints = useCallback(async (address: string, application: number) => {
    const dotbotsTmp = dotbots.slice();
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        dotbotsTmp[idx].waypoints = [];
        await publishCommand(address, application, "waypoints", {
          threshold: dotbots[idx].waypoints_threshold,
          waypoints: [],
        });
        updateDotbots(dotbotsTmp);
        return;
      }
    }
  }, [dotbots, updateDotbots, publishCommand]);

  const clearPositionsHistory = async (address: string): Promise<void> => {
    const dotbotsTmp = dotbots.slice();
    for (let idx = 0; idx < dotbots.length; idx++) {
      if (dotbots[idx].address === address) {
        dotbotsTmp[idx].position_history = [];
        await publishCommand(address, dotbots[idx].application, "clear_position_history", "");
        updateDotbots(dotbotsTmp);
        return;
      }
    }
  };

  const updateWaypointThreshold = useCallback((address: string, threshold: number): void => {
    updateDotbots(prev => prev.map(db =>
      db.address !== address ? db : { ...db, waypoints_threshold: threshold }
    ));
  }, [updateDotbots]);

  useEffect(() => {
    if (dotbots && control) {
      if (enter) {
        if (activeDotbot !== inactiveAddress) {
          for (let idx = 0; idx < dotbots.length; idx++) {
            if (dotbots[idx].address === activeDotbot) {
              applyWaypoints(activeDotbot, dotbots[idx].application);
              break;
            }
          }
        }
      }
      if (backspace) {
        if (activeDotbot !== inactiveAddress) {
          for (let idx = 0; idx < dotbots.length; idx++) {
            if (dotbots[idx].address === activeDotbot) {
              clearWaypoints(activeDotbot, dotbots[idx].application);
              break;
            }
          }
        }
      }
    }
  }, [dotbots, control, enter, backspace, applyWaypoints, clearWaypoints, activeDotbot]);

  const needDotBotMap = dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot).some(dotbot => (dotbot.calibrated ?? 0) > 0x00);
  const dotbotCount = dotbots.filter(dotbot => dotbot.application === ApplicationType.DotBot).length;
  const sailbotCount = dotbots.filter(dotbot => dotbot.application === ApplicationType.SailBot).length;
  const xgoCount = dotbots.filter(dotbot => dotbot.application === ApplicationType.XGO).length;

  return (
    <>
      <nav className="navbar navbar-dark navbar-expand-lg bg-dark">
        <div className="container-fluid">
          <a className="navbar-brand text-light" href="http://www.dotbots.org">The DotBots project</a>
          <button className="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
            <span className="navbar-toggler-icon"></span>
          </button>
        </div>
      </nav>
      <div className="container">
        {dotbots && dotbots.length > 0 && (
          <>
            {dotbotCount > 0 && (
              <div className="row">
                <div className={`col ${needDotBotMap ? "col-xxl-3" : ""}`}>
                  <div className="card m-1">
                    <div className="card-header">Available DotBots ({`${dotbotCount}`})</div>
                    <div className="card-body p-1">
                      <div className="accordion" id="accordion-dotbots">
                        {dotbots
                          .filter(dotbot => dotbot.application === ApplicationType.DotBot)
                          .map(dotbot => (
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
                          ))
                        }
                      </div>
                    </div>
                  </div>
                </div>
                {needDotBotMap && (
                  <div className="col col-xxl-9">
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
                        areaSize={areaSize}
                        backgroundMap={backgroundMap}
                        publish={publish}
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
                        mapSize={1000}
                        areaSize={areaSize}
                        backgroundMap={backgroundMap}
                        publish={publish}
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
            {sailbotCount > 0 && (
              <div className="row">
                <div className="col col-xxl-6">
                  <div className="card m-1">
                    <div className="card-header">Available SailBots</div>
                    <div className="card-body p-1">
                      <div className="accordion" id="accordion-sailbots">
                        {dotbots
                          .filter(dotbot => dotbot.application === ApplicationType.SailBot)
                          .map(dotbot => (
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
                          ))
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
            )}
            {xgoCount > 0 && (
              <div className="row">
                <div className="col">
                  <div className="card m-1">
                    <div className="card-header">Available XGO</div>
                    <div className="card-body p-1">
                      <div className="accordion" id="accordion-xgo">
                        {dotbots
                          .filter(dotbot => dotbot.application === ApplicationType.XGO)
                          .map(dotbot => (
                            <XGOItem
                              key={dotbot.address}
                              dotbot={dotbot}
                              updateActive={updateActive}
                              publishCommand={publishCommand}
                            />
                          ))
                        }
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
};

export default DotBots;
