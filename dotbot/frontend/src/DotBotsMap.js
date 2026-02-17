import React from "react";
import { useState } from "react";
import { ApplicationType, inactiveAddress, dotbotRadius } from "./utils/constants";


const DotBotsWaypoint = (props) => {
  return (
    <>
      {(props.index === 0) ? (
        <circle
          cx={props.point.x * props.mapSize / props.areaSize.width}
          cy={props.point.y * props.mapSize / props.areaSize.width}
          r="4"
          fill="none"
          stroke={props.color}
          strokeWidth="2"
          opacity={props.opacity}
        />
      ) : (
        <>
          <circle
            cx={props.point.x * props.mapSize / props.areaSize.width}
            cy={props.point.y * props.mapSize / props.areaSize.width}
            r={props.threshold * props.mapSize / props.areaSize.width}
            fill={props.color}
            stroke="none"
            opacity="10%"
          />
          <line
            x1={props.waypoints[props.index - 1].x * props.mapSize / props.areaSize.width}
            y1={props.waypoints[props.index - 1].y * props.mapSize / props.areaSize.width}
            x2={props.point.x * props.mapSize / props.areaSize.width}
            y2={props.point.y * props.mapSize / props.areaSize.width}
            stroke={props.color} strokeWidth="2" strokeDasharray="2" opacity={props.opacity}
          />
          <rect
            x={props.point.x * props.mapSize / props.areaSize.width - 2}
            y={props.point.y * props.mapSize / props.areaSize.width - 2}
            width="4" height="4" fill={props.color} opacity={props.opacity}
          />
        </>
      )}
    </>
  )
}

const DotBotsPosition = (props) => {
  return (
    <>
      {(props.index === 0) ? (
        <circle
          cx={props.point.x * props.mapSize / props.areaSize.width}
          cy={props.point.y * props.mapSize / props.areaSize.width}
          r="4"
          fill="none"
          stroke={props.color}
          strokeWidth="2"
          opacity={props.opacity}
        />
      ) : (
        <>
          <line
            x1={props.history[props.index - 1].x * props.mapSize / props.areaSize.width}
            y1={props.history[props.index - 1].y * props.mapSize / props.areaSize.width}
            x2={props.point.x * props.mapSize / props.areaSize.width}
            y2={props.point.y * props.mapSize / props.areaSize.width}
            stroke={props.color} strokeWidth="2"
            opacity={props.opacity}
          />
          <circle
            cx={props.point.x * props.mapSize / props.areaSize.width}
            cy={props.point.y * props.mapSize / props.areaSize.width}
            r="2"
            fill={props.color}
            opacity={props.opacity}
          />
        </>
      )}
    </>
  )
}

const DotBotsMapPoint = (props) => {
  const [hovered, setHovered ] = useState(false);

  let rgbColor = "rgb(0, 0, 0)"
  if (props.dotbot.rgb_led) {
    rgbColor = `rgb(${props.dotbot.rgb_led.red}, ${props.dotbot.rgb_led.green}, ${props.dotbot.rgb_led.blue})`
  }

  const posX = props.mapSize * parseInt(props.dotbot.lh2_position.x) / props.areaSize.width;
  const posY = props.mapSize * parseInt(props.dotbot.lh2_position.y) / props.areaSize.width;

  const rotation = (props.dotbot.direction) ? props.dotbot.direction : 0;
  const radius = (props.dotbot.address === props.active || hovered) ? props.mapSize * (dotbotRadius + 5) / props.areaSize.width : props.mapSize * dotbotRadius / props.areaSize.width;
  const directionShift = (props.dotbot.address === props.active || hovered) ? 2: 1;
  const directionSize = (props.dotbot.address === props.active || hovered) ? props.mapSize * (dotbotRadius + 5) / props.areaSize.width : props.mapSize * dotbotRadius / props.areaSize.width;
  const opacity = `${props.dotbot.status === 0 ? "80%" : "20%"}`
  const waypointOpacity = `${props.dotbot.status === 0 ? "50%" : "10%"}`

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
    {(props.dotbot.waypoints.length > 0) && (
      props.dotbot.waypoints.map((point, index) => (
        <DotBotsWaypoint
          key={`waypoint-${index}`}
          index={index}
          point={point}
          color={rgbColor}
          opacity={waypointOpacity}
          waypoints={props.dotbot.waypoints}
          threshold={props.dotbot.waypoints_threshold}
          {...props}
          />
      ))
    )}
    {(props.showHistory && props.dotbot.position_history.length > 0) && (
      props.dotbot.position_history
        .slice(-props.historySize)
        .map((point, index) => (
        <DotBotsPosition key={`position-${index}`} index={index} point={point} color={rgbColor} opacity={opacity} history={props.dotbot.position_history.slice(-props.historySize)} {...props} />
      ))
    )}
    <g transform={`rotate(${rotation} ${posX} ${posY})`} stroke={`${(props.dotbot.address === props.active) ? "black" : "none"}`} strokeWidth="1">
    <circle cx={posX} cy={posY}
        r={radius}
        opacity={opacity}
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
    {(props.dotbot.direction) && <polygon points={`${posX - radius + 10},${posY + radius + directionShift} ${posX + radius - 10},${posY + radius + directionShift} ${posX},${posY + radius + directionSize + directionShift}`} fill={rgbColor} opacity={opacity} />}
    </g>
    </>
  )
}

export const DotBotsMap = (props) => {

  const [ displayGrid, setDisplayGrid ] = useState(true);

  const mapClicked = (event) => {
    // const { farthestViewportElement: svgRoot } = event.target;
    // const dim = svgRoot.getBoundingClientRect();
    const dim = event.target.getBoundingClientRect();
    const x = event.clientX - dim.left;
    const y = event.clientY - dim.top;
    props.mapClicked(x * props.areaSize.width / props.mapSize, y * props.areaSize.width / props.mapSize);
  };

  const updateDisplayGrid = (event) => {
    setDisplayGrid(event.target.checked);
  };

  const mapSize = props.mapSize;
  const gridWidth = `${mapSize + 1}px`;
  const gridHeight = `${mapSize * props.areaSize.height / props.areaSize.width + 1}px`;

  return (
    <div className={`${props.dotbots && props.dotbots.length > 0 ? "visible" : "invisible"}`}>
      <div className="row justify-content-center">
        <div className="col d-flex justify-content-center">
          <div style={{ height: gridHeight, width: gridWidth }}>
            <svg style={{ height: gridHeight, width: gridWidth }}>
              <defs>
                {/* <pattern id={`smallGrid${mapSize}`} width={`${mapSize / 50}`} height={`${mapSize / 50}`} patternUnits="userSpaceOnUse">
                  <path d={`M ${mapSize / 50} 0 L 0 0 0 ${mapSize / 50}`} fill="none" stroke="gray" strokeWidth="0.5"/>
                </pattern> */}
                <pattern id={`grid${mapSize}`} width={`${500 * mapSize / props.areaSize.width}`} height={`${500 * mapSize / props.areaSize.width}`} patternUnits="userSpaceOnUse">
                  <rect width={`${500 * mapSize / props.areaSize.width}`} height={`${500 * mapSize / props.areaSize.width}`} fill={`url(#smallGrid${mapSize})`}/>
                  <path d={`M ${500 * mapSize / props.areaSize.width} 0 L 0 0 0 ${500 * mapSize / props.areaSize.width}`} fill="none" stroke="gray" strokeWidth="1"/>
                </pattern>
              </defs>
              {/* Map grid */}
              <rect width="100%" height="100%" fill={displayGrid ? `url(#grid${mapSize})`: "none"} stroke="gray" strokeWidth="1" onClick={(event) => mapClicked(event)}/>
              {/* DotBots points */}
              {
                props.dotbots && props.dotbots
                  .filter(dotbot => dotbot.status !== 2)
                  .filter(dotbot => dotbot.lh2_position)
                  .map(dotbot => <DotBotsMapPoint key={dotbot.address} dotbot={dotbot} {...props} />)
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
          <div className="d-flex mb-2">
            <div className="form-check">
              <input className="form-check-input" type="checkbox" id="flexCheckDisplayHistory" defaultChecked={props.showHistory} onChange={(event) => props.updateShowHistory(event.target.checked, ApplicationType.DotBot)} />
              <label className="form-check-label" htmlFor="flexCheckDisplayHistory">Display position history</label>
            </div>
          </div>
          <form className="form-inline">
            <label htmlFor="dotbotHistorySize">Position history size:</label>
            <input className="form-control my-1 mr-sm-2" type="number" id="dotbotHistorySize" min="10" max="1000" value={props.historySize} onChange={event => props.setHistorySize(event.target.value)}/>
          </form>
        </div>
      </div>
    </div>
  )
}
