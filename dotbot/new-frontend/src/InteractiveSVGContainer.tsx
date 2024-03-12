import {
  ReactNode,
  MouseEventHandler,
  WheelEventHandler,
  useState,
} from "react";
import { Box } from "@chakra-ui/react";
import { MAP_SIZE } from "./constants";

interface InteractiveSVGContainerProps {
  width: number;
  height: number;
  children?: ReactNode;
  translationX: number;
  setTranslationX: (x: number) => void;
  translationY: number;
  setTranslationY: (y: number) => void;
  scale: number;
  setScale: (scale: number) => void;
  rotation: number;
  setRotation: (rotation: number) => void;
}

/**
 * Container for SVG elements that implements pan, rotation and zoom.
 */
export const InteractiveSVGContainer = ({
  width,
  height,
  children,
  translationX,
  setTranslationX,
  translationY,
  setTranslationY,
  scale,
  setScale,
  rotation,
  setRotation,
}: InteractiveSVGContainerProps): React.JSX.Element => {
  // Mouse state
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const [isRotating, setIsRotating] = useState<boolean>(false);

  // Handle mouse down: left click is for panning, right click is for rotating
  const handleMouseDown: MouseEventHandler<SVGSVGElement> = (event) => {
    // Left click
    if (event.button === 0) {
      setIsPanning(true);
      // Set mouse to pan cursor
      event.currentTarget.style.cursor = "grabbing";
    }
    // Right click
    else if (event.button === 2) {
      setIsRotating(true);
      // Set mouse to left-right cursor
      event.currentTarget.style.cursor = "ew-resize";
    }
  };

  // Handle pan/rotate movement
  const handleMouseMove: MouseEventHandler<SVGSVGElement> = (event) => {
    if (isPanning) {
      setTranslationX(translationX + event.movementX);
      setTranslationY(translationY + event.movementY);
    }
    if (isRotating) {
      setRotation(rotation + event.movementX);
    }
  };

  // Stop panning/rotating when mouse is released (or leaves the SVG)
  const handleMouseUp: MouseEventHandler<SVGSVGElement> = (event) => {
    setIsPanning(false);
    setIsRotating(false);
    // Set cursor back to default
    event.currentTarget.style.cursor = "default";
  };

  // Handle zoom movement
  const handleMouseWheel: WheelEventHandler<SVGSVGElement> = (event) => {
    const newScale = scale * (1 - event.deltaY * 0.001);
    setScale(newScale);
  };

  return (
    <Box
      width={width}
      height={height}
      bg="gray.50"
      border="2px solid"
      borderColor="gray.400"
    >
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${MAP_SIZE} ${MAP_SIZE}`}
        xmlns="http://www.w3.org/2000/svg"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleMouseWheel}
        onContextMenu={(event) => event.preventDefault()}
      >
        <g
          transform={`translate(${translationX}, ${translationY}) scale(${scale}) rotate(${rotation})`}
        >
          {/* Debug arbitrary point */}
          <circle
            cx={MAP_SIZE / 2}
            cy={MAP_SIZE / 2}
            r={MAP_SIZE / 100}
            fill="green"
          />
          {/* Debug origin */}
          <circle cx={0} cy={0} r={MAP_SIZE / 100} fill="blue" />
          {children}
        </g>
      </svg>
    </Box>
  );
};
