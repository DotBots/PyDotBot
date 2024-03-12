import { useCallback, useState } from "react";
import useDotBots from "./useDotBots";
import { DotBotsMap } from "./DotBotsMap";
import { InteractiveSVGContainer } from "./InteractiveSVGContainer";
import {
  IconButton,
  Grid,
  GridItem,
  Center,
  HStack,
  VStack,
  Tooltip,
} from "@chakra-ui/react";
import {
  AiOutlineCompass,
  AiOutlineCaretRight,
  AiOutlinePause,
  AiOutlineCamera,
} from "react-icons/ai";
import { DotBotList } from "./menu/DotBotList";
import { MapSettings } from "./menu/MapSettings";
import { CalibrationMenu } from "./menu/CalibrationMenu";
import { MAP_SIZE, MAX_POSITION_HISTORY } from "./constants";
import { CalibrationState } from "./models";

function App() {
  // Transformation state (pan, zoom, rotate)
  const [translationX, setTranslationX] = useState<number>(0);
  const [translationY, setTranslationY] = useState<number>(0);
  const [scale, setScale] = useState<number>(1);
  const [rotation, setRotation] = useState<number>(0);
  const resetCameraView = useCallback(() => {
    setTranslationX(0);
    setTranslationY(0);
    setScale(1);
    setRotation(0);
  }, [setTranslationX, setTranslationY, setScale, setRotation]);

  // Map settings
  const [displayGrid, setDisplayGrid] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [historySize, setHistorySize] = useState(MAX_POSITION_HISTORY);

  // Calibration states
  const [calibrationState, setCalibrationState] =
    useState<CalibrationState>("unknown");
  const [pointsChecked, setPointsChecked] = useState([
    false,
    false,
    false,
    false,
  ]);

  // DotBots data
  const { dotBots, activeDotBot, updateActiveDotBot } = useDotBots();

  return (
    <Center>
      <Grid
        // Map positions of the grid. t = top, l = left, c = center, r = right, b = bottom
        templateAreas={`"tl t tr"
                        "l  c r"
                        "bl b br"`}
        gridTemplateColumns="auto 1fr auto"
        gridTemplateRows="auto 1fr auto"
        gap="1"
      >
        <GridItem gridArea="l">
          <VStack>
            <DotBotList dotBots={dotBots} />
          </VStack>
        </GridItem>
        <GridItem gridArea="r">
          <VStack>
            <Tooltip hasArrow label="Reset camera view">
              <IconButton
                aria-label="Reset camera view"
                fontSize="25px"
                icon={<AiOutlineCamera />}
                onClick={resetCameraView}
              />
            </Tooltip>
          </VStack>
        </GridItem>
        <GridItem gridArea="c">
          <InteractiveSVGContainer
            translationX={translationX}
            setTranslationX={setTranslationX}
            translationY={translationY}
            setTranslationY={setTranslationY}
            scale={scale}
            setScale={setScale}
            rotation={rotation}
            setRotation={setRotation}
            width={MAP_SIZE}
            height={MAP_SIZE}
          >
            {dotBots && (
              <DotBotsMap
                mapSize={MAP_SIZE}
                displayGrid={displayGrid}
                dotBots={dotBots}
                active={activeDotBot}
                showHistory={showHistory}
                historySize={historySize}
                updateActive={updateActiveDotBot}
                pointsChecked={pointsChecked}
                setPointsChecked={setPointsChecked}
                calibrationState={calibrationState}
              />
            )}
          </InteractiveSVGContainer>
        </GridItem>
        <GridItem gridArea="b">
          <HStack h="100%">
            <MapSettings
              showHistory={showHistory}
              setShowHistory={setShowHistory}
              historySize={historySize}
              setHistorySize={setHistorySize}
              displayGrid={displayGrid}
              setDisplayGrid={setDisplayGrid}
            />
            <CalibrationMenu
              calibrationState={calibrationState}
              setCalibrationState={setCalibrationState}
              pointsChecked={pointsChecked}
              setPointsChecked={setPointsChecked}
            />
            <Tooltip hasArrow label="Start DotBot movement">
              <IconButton
                aria-label="Start DotBot movement"
                fontSize="25px"
                icon={<AiOutlineCaretRight />}
              />
            </Tooltip>
            <Tooltip hasArrow label="Stop DotBot movement">
              <IconButton
                aria-label="Stop DotBot movement"
                fontSize="25px"
                icon={<AiOutlinePause />}
              />
            </Tooltip>
          </HStack>
        </GridItem>
      </Grid>
    </Center>
  );
}

export default App;
