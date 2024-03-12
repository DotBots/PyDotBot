import { useState, useCallback } from "react";
import { INACTIVE_ADDRESS } from "./constants";
import {
  DotBotAddressModel,
  DotBotLH2Position,
  DotBotModel,
  DotBotStatus,
} from "./models";
import * as api from "./api";

const referencePoints = [
  { x: -0.1, y: 0.1 },
  { x: 0.1, y: 0.1 },
  { x: -0.1, y: -0.1 },
  { x: 0.1, y: -0.1 },
];

interface DotBotPositionProps {
  index: number;
  point: DotBotLH2Position;
  color: string;
  opacity: string;
  history: DotBotLH2Position[];
}

const DotBotsPosition = ({
  index,
  point,
  color,
  opacity,
  history,
}: DotBotPositionProps) => {
  return (
    <>
      {index === 0 ? (
        <circle
          cx={point.x}
          cy={point.y}
          r="4"
          fill="none"
          stroke={color}
          strokeWidth="2"
          opacity={opacity}
        />
      ) : (
        <>
          <line
            x1={history[index - 1].x}
            y1={history[index - 1].y}
            x2={point.x}
            y2={point.y}
            stroke={color}
            strokeWidth="2"
            opacity={opacity}
          />
          <circle
            cx={point.x}
            cy={point.y}
            r="2"
            fill={color}
            opacity={opacity}
          />
        </>
      )}
    </>
  );
};

interface DotBotsMapPointProps {
  dotBot: DotBotModel; // The DotBot to display
  active: DotBotAddressModel; // The current active DotBot
  updateActive: (address: DotBotAddressModel) => void; // Function to update the active DotBot
  mapSize: number;
  showHistory: boolean;
}

const DotBotsMapPoint = ({
  dotBot,
  active,
  updateActive,
  mapSize,
  showHistory,
}: DotBotsMapPointProps) => {
  const [hovered, setHovered] = useState<boolean>(false);

  let rgbColor = "rgb(0, 0, 0)";
  if (dotBot.rgb_led) {
    rgbColor = `rgb(${dotBot.rgb_led.red}, ${dotBot.rgb_led.green}, ${dotBot.rgb_led.blue})`;
  }

  if (!dotBot.lh2_position) {
    return <></>;
  }

  const posX: number = dotBot.lh2_position.x;
  const posY: number = dotBot.lh2_position.y;
  const rotation = dotBot.direction ? dotBot.direction : 0;
  const radius = dotBot.address === active.address || hovered ? 0.03 : 0.02;
  const directionShift = dotBot.address === active.address || hovered ? 0.02 : 0.01;
  const directionSize = dotBot.address === active.address || hovered ? 0.08 : 0.05;
  const opacity = `${dotBot.status === DotBotStatus.ALIVE ? "80%" : "20%"}`;
  const waypointOpacity = `${dotBot.status === DotBotStatus.ALIVE ? "50%" : "10%"}`;

  const onMouseEnter = () => {
    if (dotBot.status !== DotBotStatus.ALIVE) {
      return;
    }
    setHovered(true);
  };

  const onMouseLeave = () => {
    setHovered(false);
  };

  // Render waypoints, if any
  const waypoints =
    dotBot.waypoints.length > 0 &&
    typeof dotBot.waypoints[0] === "object" &&
    "x" in dotBot.waypoints[0] &&
    "y" in dotBot.waypoints[0] &&
    dotBot.waypoints.map((point, index) =>
      index === 0 ? (
        <circle
          cx={point.x}
          cy={point.y}
          r="4"
          fill="none"
          stroke={rgbColor}
          strokeWidth="2"
          opacity={waypointOpacity}
        />
      ) : (
        <>
          <circle
            cx={point.x}
            cy={point.y}
            r={dotBot.waypoints_threshold / 1000}
            fill={rgbColor}
            stroke="none"
            opacity="10%"
          />
          <line
            x1={dotBot.waypoints[index - 1].x}
            y1={dotBot.waypoints[index - 1].y}
            x2={point.x}
            y2={point.y}
            stroke={rgbColor}
            strokeWidth="2"
            strokeDasharray="2"
            opacity={waypointOpacity}
          />
          <rect
            x={point.x}
            y={point.y}
            width="4"
            height="4"
            fill={rgbColor}
            opacity={waypointOpacity}
          />
        </>
      ),
    );

  // Stitch everything together: the waypoints, position history
  // and finally the DotBot circle.
  return (
    // We wrap everything in a group (<g>) to 
    // scale [0,1] -> [0,mapSize]
    <g transform={`scale(${mapSize})`}>
      {waypoints}
      {showHistory &&
        dotBot.position_history.length > 0 &&
        dotBot.position_history
          .slice()
          .map((point, index) => (
            <DotBotsPosition
              key={`position-${index}`}
              index={index}
              point={point}
              color={rgbColor}
              opacity={opacity}
              history={dotBot.position_history.slice()}
            />
          ))}
      <g
        transform={`rotate(${rotation} ${posX} ${posY})`}
        stroke={`${dotBot.address === active.address ? "black" : "none"}`}
        strokeWidth="0.005"
      >
        <circle
          cx={posX}
          cy={posY}
          r={radius}
          opacity={opacity}
          fill={rgbColor}
          style={{ cursor: "pointer" }}
          onClick={() => {
            updateActive({
              address:
                dotBot.address === active.address
                  ? INACTIVE_ADDRESS
                  : dotBot.address,
            });
          }}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
        >
          <title>{`${dotBot.address}@${posX}x${posY}`}</title>
        </circle>
        {dotBot.direction && (
          <polygon
            points={`${posX - radius + 2},${posY + radius + directionShift} ${posX + radius - 2},${posY + radius + directionShift} ${posX},${posY + radius + directionSize + directionShift}`}
            fill={rgbColor}
            opacity={opacity}
          />
        )}
      </g>
    </g>
  );
};

interface DotBotsMapProps {
  dotBots: DotBotModel[];
  mapSize: number;
  displayGrid: boolean;
  active: DotBotAddressModel;
  updateActive: (address: DotBotAddressModel) => void;
  showHistory: boolean;
}

export const DotBotsMap = ({
  dotBots,
  mapSize,
  displayGrid,
  active,
  updateActive,
  showHistory,
}: DotBotsMapProps) => {
  const [calibrationState, setCalibrationState] = useState("unknown");
  const [pointsChecked, setPointsChecked] = useState([
    false,
    false,
    false,
    false,
  ]);

  const pointClicked = useCallback(
    (index: number) => {
      const newPointsChecked = pointsChecked.slice();
      newPointsChecked[index] = true;
      setPointsChecked(newPointsChecked);
      api.addLH2CalibrationPoint(index).catch((error) => {
        console.error(error);
      });
    },
    [pointsChecked, setPointsChecked],
  );

  const gridSize = `${mapSize + 1}px`;
  return (
    <svg style={{ height: gridSize, width: gridSize }}>
      <defs>
        <pattern
          id={`smallGrid${mapSize}`}
          width={`${mapSize / 50}`}
          height={`${mapSize / 50}`}
          patternUnits="userSpaceOnUse"
        >
          <path
            d={`M ${mapSize / 50} 0 L 0 0 0 ${mapSize / 50}`}
            fill="none"
            stroke="gray"
            strokeWidth="0.5"
          />
        </pattern>
        <pattern
          id={`grid${mapSize}`}
          width={`${mapSize / 5}`}
          height={`${mapSize / 5}`}
          patternUnits="userSpaceOnUse"
        >
          <rect
            width={`${mapSize / 5}`}
            height={`${mapSize / 5}`}
            fill={`url(#smallGrid${mapSize})`}
          />
          <path
            d={`M ${mapSize / 5} 0 L 0 0 0 ${mapSize / 5}`}
            fill="none"
            stroke="gray"
            strokeWidth="1"
          />
        </pattern>
      </defs>
      {/* Map grid */}
      <rect
        width="100%"
        height="100%"
        fill={displayGrid ? `url(#grid${mapSize})` : "none"}
        stroke="gray"
        strokeWidth="1"
      // onClick={(event) => mapClicked(event)} // TODO: Implement mapClicked
      />
      {/* DotBots points */}
      {dotBots &&
        dotBots
          .filter((dotBot) => dotBot.status !== DotBotStatus.DEAD)
          .filter((dotBot) => dotBot.lh2_position)
          .map((dotBot) => (
            <DotBotsMapPoint
              key={dotBot.address}
              dotBot={dotBot}
              mapSize={mapSize}
              active={active}
              showHistory={showHistory}
              updateActive={updateActive}
            />
          ))}
      {/*
      {dotBots && dotBots.length > 0 && dotBots[0].lh2_position &&
        <g transform="scale(500)">
      <circle cx={dotBots[0].lh2_position.x} cy={dotBots[0].lh2_position.y} r={0.02} fill="red"> </circle>
          <rect x={0} y={0} width="1" height="1" stroke="black" stroke-width="0.01" fill="transparent"></rect>
      </g>}
      */}
      {["running", "ready"].includes(calibrationState) && (
        <>
          {referencePoints.map((point, index) => (
            <rect
              key={index}
              x={point.x}
              y={point.y}
              width="10"
              height="10"
              fill={pointsChecked[index] ? "green" : "grey"}
              style={{ cursor: "pointer" }}
              onClick={() => pointClicked(index)}
            >
              <title>{index + 1}</title>
            </rect>
          ))}
        </>
      )}
    </svg>
  );
};
