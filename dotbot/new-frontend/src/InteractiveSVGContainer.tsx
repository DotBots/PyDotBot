import {
  ReactNode,
  MouseEventHandler,
  WheelEventHandler,
  useState,
} from "react";
import { Box } from "@chakra-ui/react";

interface InteractiveSVGContainerProps {
  width: number;
  height: number;
  children?: ReactNode;
}

/**
 * Container for SVG elements that implements pan, rotation and zoom.
 */
export const InteractiveSVGContainer = ({
  width,
  height,
  children,
}: InteractiveSVGContainerProps): React.JSX.Element => {
  // Transformation state
  const [translationX, setTranslationX] = useState<number>(0);
  const [translationY, setTranslationY] = useState<number>(0);
  const [scale, setScale] = useState<number>(1);
  const [rotation, setRotation] = useState<number>(0);

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
    const newScale = scale * (1 + event.deltaY * 0.001);
    setScale(newScale);
  };

  return (
    <Box width={width} height={height} bg="gray.50" border="2px solid" borderColor="gray.400">
      <svg
        width="100%"
        height="100%"
        viewBox="0 0 100 100"
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
          <circle cx={50} cy={50} r={1} fill="red" /> {/* Debug arbitrary point */}
          <circle cx={0} cy={0} r={1} fill="blue" /> {/* Debug origin */}
          {children}
        </g>
      </svg>
    </Box>
  );
};