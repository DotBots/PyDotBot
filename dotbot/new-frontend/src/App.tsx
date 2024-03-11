import useDotBots from "./useDotBots";
import { DotBotModel } from "./models";
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
  AiOutlineSetting,
  AiOutlineCompass,
  AiOutlineCaretRight,
  AiOutlinePause,
} from "react-icons/ai";
import { DotBotList } from "./menu/DotBotList";

function App() {
  const { dotBots } = useDotBots();

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
          <InteractiveSVGContainer width={500} height={500} />
        </GridItem>
        <GridItem gridArea="b">
          <HStack h="100%">
            <Tooltip hasArrow label="Map settings">
              <IconButton
                aria-label="Map settings"
                fontSize="25px"
                icon={<AiOutlineSetting />}
              />
            </Tooltip>
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
