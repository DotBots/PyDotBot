import React, { memo, useState } from "react";
import { ApplicationType, inactiveAddress, dotbotRadius } from "./utils/constants";
import { Area, BackgroundMap, DotBot, LH2Position } from "./types";

interface DotBotsWaypointProps {
  index: number;
  point: LH2Position;
  color: string;
  opacity: string;
  waypoints: LH2Position[];
  threshold: number;
  viewport: Area;
  mapSize: number;
}

const DotBotsWaypoint: React.FC<DotBotsWaypointProps> = (props) => {
  return (
    <>
      {props.index === 0 ? (
        <circle
          cx={(props.point.x - props.viewport.x) * props.mapSize / props.viewport.w}
          cy={(props.point.y - props.viewport.y) * props.mapSize / props.viewport.w}
          r="4"
          fill="none"
          stroke={props.color}
          strokeWidth="2"
          opacity={props.opacity}
        />
      ) : (
        <>
          <circle
            cx={(props.point.x - props.viewport.x) * props.mapSize / props.viewport.w}
            cy={(props.point.y - props.viewport.y) * props.mapSize / props.viewport.w}
            r={props.threshold * props.mapSize / props.viewport.w}
            fill={props.color}
            stroke="none"
            opacity="10%"
          />
          <line
            x1={(props.waypoints[props.index - 1].x - props.viewport.x) * props.mapSize / props.viewport.w}
            y1={(props.waypoints[props.index - 1].y - props.viewport.y) * props.mapSize / props.viewport.w}
            x2={(props.point.x - props.viewport.x) * props.mapSize / props.viewport.w}
            y2={(props.point.y - props.viewport.y) * props.mapSize / props.viewport.w}
            stroke={props.color} strokeWidth="2" strokeDasharray="2" opacity={props.opacity}
          />
          <rect
            x={(props.point.x - props.viewport.x) * props.mapSize / props.viewport.w - 2}
            y={(props.point.y - props.viewport.y) * props.mapSize / props.viewport.w - 2}
            width="4" height="4" fill={props.color} opacity={props.opacity}
          />
        </>
      )}
    </>
  );
};

interface DotBotsPositionProps {
  index: number;
  point: LH2Position;
  color: string;
  opacity: string;
  history: LH2Position[];
  viewport: Area;
  mapSize: number;
}

const DotBotsPosition: React.FC<DotBotsPositionProps> = (props) => {
  return (
    <>
      {props.index === 0 ? (
        <circle
          cx={(props.point.x - props.viewport.x) * props.mapSize / props.viewport.w}
          cy={(props.point.y - props.viewport.y) * props.mapSize / props.viewport.w}
          r="4"
          fill="none"
          stroke={props.color}
          strokeWidth="2"
          opacity={props.opacity}
        />
      ) : (
        <>
          <line
            x1={(props.history[props.index - 1].x - props.viewport.x) * props.mapSize / props.viewport.w}
            y1={(props.history[props.index - 1].y - props.viewport.y) * props.mapSize / props.viewport.w}
            x2={(props.point.x - props.viewport.x) * props.mapSize / props.viewport.w}
            y2={(props.point.y - props.viewport.y) * props.mapSize / props.viewport.w}
            stroke={props.color} strokeWidth="2"
            opacity={props.opacity}
          />
          <circle
            cx={(props.point.x - props.viewport.x) * props.mapSize / props.viewport.w}
            cy={(props.point.y - props.viewport.y) * props.mapSize / props.viewport.w}
            r="2"
            fill={props.color}
            opacity={props.opacity}
          />
        </>
      )}
    </>
  );
};

interface DotBotsMapPointProps {
  dotbot: DotBot;
  viewport: Area;
  mapSize: number;
  showHistory: boolean;
  historySize: number;
  active: string;
  updateActive: (address: string) => void;
}

const DotBotsMapPoint: React.FC<DotBotsMapPointProps> = memo((props) => {
  const [hovered, setHovered] = useState(false);

  let rgbColor = "rgb(0, 0, 0)";
  if (props.dotbot.rgb_led) {
    rgbColor = `rgb(${props.dotbot.rgb_led.red}, ${props.dotbot.rgb_led.green}, ${props.dotbot.rgb_led.blue})`;
  }

  const lh2Pos = props.dotbot.lh2_position!;
  const posX = props.mapSize * (parseInt(String(lh2Pos.x)) - props.viewport.x) / props.viewport.w;
  const posY = props.mapSize * (parseInt(String(lh2Pos.y)) - props.viewport.y) / props.viewport.w;

  const rotation = (props.dotbot.direction !== -1000) ? props.dotbot.direction : 0;
  const isActiveOrHovered = props.dotbot.address === props.active || hovered;
  const radius = isActiveOrHovered
    ? props.mapSize * (dotbotRadius + 5) / props.viewport.w
    : props.mapSize * dotbotRadius / props.viewport.w;
  const directionShift = isActiveOrHovered ? 2 : 1;
  const directionSize = isActiveOrHovered
    ? props.mapSize * (dotbotRadius + 5) / props.viewport.w
    : props.mapSize * dotbotRadius / props.viewport.w;
  const opacity = `${props.dotbot.status === 0 ? "80%" : "20%"}`;
  const waypointOpacity = `${props.dotbot.status === 0 ? "50%" : "10%"}`;

  const onMouseEnter = (): void => {
    if (props.dotbot.status !== 0) return;
    setHovered(true);
  };

  const onMouseLeave = (): void => {
    setHovered(false);
  };

  const lh2Waypoints = props.dotbot.waypoints as LH2Position[];
  const lh2History = props.dotbot.position_history as LH2Position[];

  return (
    <>
      {lh2Waypoints.length > 0 &&
        lh2Waypoints.map((point, index) => (
          <DotBotsWaypoint
            key={`waypoint-${index}`}
            index={index}
            point={point}
            color={rgbColor}
            opacity={waypointOpacity}
            waypoints={lh2Waypoints}
            threshold={props.dotbot.waypoints_threshold}
            viewport={props.viewport}
            mapSize={props.mapSize}
          />
        ))
      }
      {props.showHistory && lh2History.length > 0 &&
        lh2History
          .slice(-props.historySize)
          .map((point, index) => (
            <DotBotsPosition
              key={`position-${index}`}
              index={index}
              point={point}
              color={rgbColor}
              opacity={opacity}
              history={lh2History.slice(-props.historySize)}
              viewport={props.viewport}
              mapSize={props.mapSize}
            />
          ))
      }
        <circle
          cx={posX}
          cy={posY}
          r={radius}
          opacity={opacity}
          fill={rgbColor}
          style={{ cursor: "pointer" }}
          stroke={`${(props.dotbot.address === props.active) ? "black" : "none"}`} strokeWidth="1"
          onClick={() => {
            props.updateActive(props.dotbot.address === props.active ? inactiveAddress : props.dotbot.address);
          }}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
        >
        <title>{`${props.dotbot.address}@${posX}x${posY}`}</title>
        </circle>
        {props.dotbot.direction !== -1000 && (
        <g
          transform={`rotate(${rotation} ${posX} ${posY})`}
          stroke={`${props.dotbot.address === props.active ? "black" : "none"}`}
          strokeWidth="1">
          <polygon
            points={`${posX - radius + 10 * props.mapSize / props.viewport.w},${posY + radius + directionShift} ${posX + radius - 10 * props.mapSize / props.viewport.w},${posY + radius + directionShift} ${posX},${posY + radius + directionSize + directionShift}`}
            fill={rgbColor}
            opacity={opacity}
          />
        </g>
        )}
    </>
  );
});

interface DotBotsMapProps {
  dotbots: DotBot[];
  active: string;
  // The part of the frame this map draws: the whole site plus a margin.
  viewport: Area;
  // The areas shown, drawn solid; every other area of the site is outlined.
  activeAreas: Area[];
  siteAreas: Area[];
  backgroundMap?: BackgroundMap;
  mapSize: number;
  showHistory: boolean;
  historySize: number;
  setHistorySize: (size: number) => void;
  updateActive: (address: string) => void;
  updateShowHistory: (show: boolean, application: number) => void;
  mapClicked: (x: number, y: number) => void;
  publish: (topic: string, message: unknown) => void;
}

export const DotBotsMap: React.FC<DotBotsMapProps> = (props) => {
  const [displayGrid, setDisplayGrid] = useState(true);

  const mapClicked = (event: React.MouseEvent<SVGRectElement>): void => {
    const dim = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - dim.left;
    const y = event.clientY - dim.top;
    props.mapClicked(props.viewport.x + x * props.viewport.w / props.mapSize, props.viewport.y + y * props.viewport.w / props.mapSize);
  };

  const updateDisplayGrid = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setDisplayGrid(event.target.checked);
  };

  const mapSize = props.mapSize;
  const gridWidth = `${mapSize + 1}px`;
  const gridHeight = `${mapSize * props.viewport.h / props.viewport.w + 1}px`;

  // One area as a pixel box of this map, in the same scale as a bot position.
  const areaBox = (area: Area) => ({
    x: (area.x - props.viewport.x) * mapSize / props.viewport.w,
    y: (area.y - props.viewport.y) * mapSize / props.viewport.w,
    width: area.w * mapSize / props.viewport.w,
    height: area.h * mapSize / props.viewport.w,
  });
  const activeNames = new Set(props.activeAreas.map(area => area.name ?? ""));

  return (
    <div className={`${props.dotbots && props.dotbots.length > 0 ? "visible" : "invisible"}`}>
      <div className="row justify-content-center">
        <div className="col d-flex justify-content-center">
          <div style={{ height: gridHeight, width: gridWidth }}>
            <svg style={{ height: gridHeight, width: gridWidth }}>
              <defs>
                <pattern
                  id={`grid${mapSize}`}
                  width={`${500 * mapSize / props.viewport.w}`}
                  height={`${500 * mapSize / props.viewport.w}`}
                  patternUnits="userSpaceOnUse"
                >
                  <rect
                    width={`${500 * mapSize / props.viewport.w}`}
                    height={`${500 * mapSize / props.viewport.w}`}
                    fill={`url(#smallGrid${mapSize})`}
                  />
                  <path
                    d={`M ${500 * mapSize / props.viewport.w} 0 L 0 0 0 ${500 * mapSize / props.viewport.w}`}
                    fill="none"
                    stroke="gray"
                    strokeWidth="1"
                  />
                </pattern>
              </defs>
              {/* Background map */}
              {props.backgroundMap?.data &&
                <image href={`data:image/png;base64,${props.backgroundMap.data}`} x="0" y="0" width={gridWidth} height={gridHeight} />
              }
              <rect
                width="100%"
                height="100%"
                fill={displayGrid ? `url(#grid${mapSize})` : "none"}
                stroke="gray"
                strokeWidth="1"
                onClick={mapClicked}
              />
              {/* the site's areas: the shown ones solid, the rest outlined */}
              {props.siteAreas
                .filter(area => !activeNames.has(area.name ?? ""))
                .map(area => (
                  <g key={`area-${area.name}`} pointerEvents="none">
                    <rect
                      {...areaBox(area)}
                      fill="none"
                      stroke="gray"
                      strokeWidth="1"
                      strokeDasharray="4 3"
                      opacity="0.6"
                    />
                    <text
                      x={areaBox(area).x + 4}
                      y={areaBox(area).y + 12}
                      fontSize="10"
                      fill="gray"
                    >
                      {area.name}
                    </text>
                  </g>
                ))}
              {props.activeAreas.map((area, index) => (
                <rect
                  key={`active-${area.name ?? index}`}
                  {...areaBox(area)}
                  fill="none"
                  stroke="gray"
                  strokeWidth="2"
                  pointerEvents="none"
                />
              ))}
              {props.dotbots &&
                props.dotbots
                  .filter(dotbot => dotbot.status !== 2)
                  .filter(dotbot => dotbot.lh2_position)
                  .map(dotbot => (
                    <DotBotsMapPoint
                      key={dotbot.address}
                      dotbot={dotbot}
                      viewport={props.viewport}
                      mapSize={props.mapSize}
                      showHistory={props.showHistory}
                      updateActive={props.updateActive}
                      active={props.active}
                      historySize={props.historySize}
                    />
                  ))
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
              <input
                className="form-check-input"
                type="checkbox"
                id="flexCheckDisplayGrid"
                defaultChecked={displayGrid}
                onChange={updateDisplayGrid}
              />
              <label className="form-check-label" htmlFor="flexCheckDisplayGrid">Display grid</label>
            </div>
          </div>
          <div className="d-flex mb-2">
            <div className="form-check">
              <input
                className="form-check-input"
                type="checkbox"
                id="flexCheckDisplayHistory"
                defaultChecked={props.showHistory}
                onChange={(event) => props.updateShowHistory(event.target.checked, ApplicationType.DotBot)}
              />
              <label className="form-check-label" htmlFor="flexCheckDisplayHistory">Display position history</label>
            </div>
          </div>
          <form className="form-inline">
            <label htmlFor="dotbotHistorySize">Position history size:</label>
            <input
              className="form-control my-1 mr-sm-2"
              type="number"
              id="dotbotHistorySize"
              min="10"
              max="1000"
              value={props.historySize}
              onChange={event => props.setHistorySize(Number(event.target.value))}
            />
          </form>
        </div>
      </div>
    </div>
  );
};
