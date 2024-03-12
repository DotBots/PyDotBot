import { MenuButton } from "./MenuButton";
import { AiOutlineSetting, AiOutlineHistory } from "react-icons/ai";
import {
  Box,
  Center,
  Checkbox,
  Flex,
  Slider,
  SliderFilledTrack,
  SliderThumb,
  SliderTrack,
} from "@chakra-ui/react";

interface DotBotListProps {
  showHistory: boolean;
  setShowHistory: (show: boolean) => void;
  historySize: number;
  setHistorySize: (size: number) => void;
  displayGrid: boolean;
  setDisplayGrid: (display: boolean) => void;
}

/**
 * Component for a botton tab that shows the list of DotBots in a popover.
 */
export const MapSettings = ({
  showHistory,
  setShowHistory,
  historySize,
  setHistorySize,
  displayGrid,
  setDisplayGrid,
}: DotBotListProps) => {
  const settings = (
    <>
      <Flex justify="space-around">
        <Checkbox
          isChecked={displayGrid}
          onChange={(e) => setDisplayGrid(e.target.checked)}
        >
          Display grid
        </Checkbox>
        <Checkbox
          isChecked={showHistory}
          onChange={(e) => setShowHistory(e.target.checked)}
        >
          Show history
        </Checkbox>
      </Flex>
      {showHistory && (
        <>
          <Center mt={2} mb={-2}>
            Position history length
          </Center>
          <Slider
            aria-label="slider-ex-1"
            defaultValue={historySize}
            onChange={(val) => setHistorySize(val > 0 ? val : 0)}
          >
            <SliderTrack>
              <SliderFilledTrack />
            </SliderTrack>
            <SliderThumb boxSize={6}>
              <Box color="blue.400" as={AiOutlineHistory} />
            </SliderThumb>
          </Slider>
        </>
      )}
    </>
  );

  return (
    <MenuButton
      label="Map options"
      tooltipPlacement="bottom"
      icon={<AiOutlineSetting />}
      popoverPlacement="bottom"
      popoverContent={settings}
    />
  );
};
