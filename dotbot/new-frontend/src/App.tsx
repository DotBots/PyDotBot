import { useState, createContext } from "react";
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
} from "react-icons/ai";
import { DotBotList } from "./menu/DotBotList";
import { MapSettings } from "./menu/MapSettings";
import { MAP_SIZE, MAX_POSITION_HISTORY } from "./constants";


function App() {
  const [displayGrid, setDisplayGrid] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [historySize, setHistorySize] = useState(MAX_POSITION_HISTORY);
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
        <GridItem gridArea="c">
          <InteractiveSVGContainer width={MAP_SIZE} height={MAP_SIZE}>
            {dotBots && (
              <DotBotsMap
                mapSize={MAP_SIZE}
                displayGrid={displayGrid}
                dotBots={dotBots}
                active={activeDotBot}
                showHistory={showHistory}
                historySize={historySize}
                updateActive={updateActiveDotBot}
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
            <Tooltip hasArrow label="Start/stop calibration">
              <IconButton
                aria-label="Start/stop calibration"
                fontSize="25px"
                icon={<AiOutlineCompass />}
              />
            </Tooltip>
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
