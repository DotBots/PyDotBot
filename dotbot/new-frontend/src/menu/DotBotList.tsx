import { DotBotModel } from "../models";
import { MenuButton } from "./MenuButton";
import { AiOutlineRobot } from "react-icons/ai";

interface DotBotListProps {
  dotBots: DotBotModel[] | undefined;
}

/**
 * Component for a botton tab that shows the list of DotBots in a popover.
 */
export const DotBotList = ({ dotBots }: DotBotListProps) => {
  const dotBotList = dotBots ? (
    <>
      {dotBots.map((dotBot: DotBotModel, index: number) => {
        return (
          <div key={index}>
            <div>DotBot {index + 1}</div>
            <div>Address: {dotBot.address}</div>
            <div>
              Position:{" "}
              {dotBot.lh2_position && (
                <b>
                  {dotBot.lh2_position.x}, {dotBot.lh2_position.y}
                </b>
              )}
            </div>
          </div>
        );
      })}
    </>
  ) : (
    <div>No DotBots found</div>
  );

  return (
    <MenuButton
      label="DotBots list"
      tooltipPlacement="left"
      icon={<AiOutlineRobot />}
      popoverPlacement="left-start"
      popoverContent={dotBotList}
    />
  );
};
