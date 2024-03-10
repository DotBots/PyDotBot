import { useCallback, useState } from "react";
import useWebSocket from "react-use-websocket";
import {
  INACTIVE_ADDRESS,
  LH2_DISTANCE_THRESHOLD,
  WEBSOCKET_URL,
} from "./constants";
import {
  DotBotAddressModel,
  DotBotModel,
  DotBotLH2Position,
  DotBotNotificationCommand,
  DotBotNotificationModel,
} from "./models";
import * as api from "./api";

/**
 * Utility function to calculate cartesian distance between two coordinates.
 */
function lh2_distance(lh21: DotBotLH2Position, lh22: DotBotLH2Position) {
  return Math.sqrt((lh21.x - lh22.x) ** 2 + (lh21.y - lh22.y) ** 2);
}

/**
 * This custom hook is used to fetch the list of dotBots and the active DotBot address.
 */
export default function useDotBots() {
  const [dotBots, setDotBots] = useState<DotBotModel[]>();
  const [activeDotBot, setActiveDotBot] = useState<DotBotAddressModel>({
    address: INACTIVE_ADDRESS,
  });

  // Use the API to fetch the list of dotBots and the active DotBot address.
  const getAllDotBots = useCallback(async () => {
    const data = await api.fetchDotBots().catch((error) => console.log(error));
    if (data) {
      setDotBots(data);
    }
    const active = await api
      .fetchActiveDotBotAddress()
      .catch((error) => console.log(error));
    if (active) {
      setActiveDotBot(active);
    }
  }, [setDotBots, setActiveDotBot]);

  // Process WebSocket messages and act accordingly.
  const onWsMessage = (ev: { data: string }) => {
    const message = JSON.parse(ev.data) as DotBotNotificationModel;
    if (message.cmd === DotBotNotificationCommand.RELOAD) {
      // Update everything
      getAllDotBots().catch((error) => console.log(error));
    }
    if (
      message.cmd === DotBotNotificationCommand.UPDATE &&
      dotBots &&
      dotBots.length > 0
    ) {
      // Update a single DotBot

      // Shallow copy of dotBots to set the new state
      const newDotBots = dotBots.slice();

      // DotBot to update
      const dotBot = newDotBots.find(
        (dotBot) => dotBot.address === message.data?.address,
      );

      if (!dotBot) return;

      // Update message
      if (message.data?.direction) {
        dotBot.direction = message.data?.direction;
      }

      // Update position
      if (message.data?.lh2_position) {
        const newPosition: DotBotLH2Position = {
          x: message.data.lh2_position.x,
          y: message.data.lh2_position.y,
        };
        if (
          dotBot.lh2_position &&
          (dotBot.position_history.length === 0 ||
            lh2_distance(dotBot.lh2_position, newPosition) >
            LH2_DISTANCE_THRESHOLD)
        ) {
          dotBot.position_history.push(newPosition);
        }
        dotBot.lh2_position = newPosition;
      }
      setDotBots(newDotBots);
    }
  };

  console.log("WS URL: ", WEBSOCKET_URL);

  useWebSocket(WEBSOCKET_URL, {
    onOpen: () => {
      getAllDotBots().catch((error) => console.log(error));
    },
    onMessage: (event) => onWsMessage(event),
    shouldReconnect: () => true,
  });

  return { dotBots, activeDotBot };
}
