import { MenuButton } from "./MenuButton";
import { AiOutlineCompass } from "react-icons/ai";
import { Button, Text } from "@chakra-ui/react";
import { CalibrationState } from "../models";
import * as api from "../api";
import { useCallback, useEffect, useState } from "react";

interface CalibrationMenuProps {
  calibrationState: CalibrationState;
  setCalibrationState: (state: CalibrationState) => void;
  pointsChecked: boolean[];
  setPointsChecked: (points: boolean[]) => void;
}

/**
 * Component for a botton tab that shows the list of DotBots in a popover.
 */
export const CalibrationMenu = ({
  calibrationState,
  setCalibrationState,
  pointsChecked,
  setPointsChecked,
}: CalibrationMenuProps) => {
  const calibrateClicked = useCallback(() => {
    if (["unknown", "done"].includes(calibrationState)) {
      setPointsChecked([false, false, false, false]);
      setCalibrationState("running");
    } else if (calibrationState === "ready") {
      setCalibrationState("done");
      api.applyLH2Calibration().catch((error) => console.error(error));
    }
  }, [calibrationState, setCalibrationState, setPointsChecked]);

  let calibButtonText;
  if (calibrationState == "running") {
    calibButtonText = "Calibration in progress...";
  } else if (calibrationState == "ready") {
    calibButtonText = "Apply calibration";
  } else if (calibrationState == "done") {
    calibButtonText = "Update calibration";
  } else {
    calibButtonText = "Calibrate";
  }

  const [calibrationFetched, setCalibrationFetched] = useState(false);

  const fetchCalibrationState = useCallback(async () => {
    const data = await api
      .fetchLH2CalibrationState()
      .catch((error) => console.error(error));
    if (data) {
      setCalibrationState(data.state);
      setCalibrationFetched(true);
    }
  }, [setCalibrationFetched, setCalibrationState]);

  useEffect(() => {
    if (!calibrationFetched) {
      fetchCalibrationState().catch((error) => console.error(error));
    }
    if (pointsChecked.every((v) => v === true)) {
      setCalibrationState("ready");
    }
  }, [
    calibrationFetched,
    fetchCalibrationState,
    pointsChecked,
    setCalibrationState,
  ]);

  const menu = (
    <>
      <Button
        isLoading={calibrationState == "running"}
        loadingText="Calibration in progress"
        onClick={calibrateClicked}
      >
        {calibButtonText}
      </Button>
      {calibrationState == "running" && (
        <Text fontSize='xs' mt={1}>
          Place a DotBot on the marks on the ground and once done, click the
          corresponding rectangle on the grid. Repeat the operation for each
          mark. Once all rectangles are green, click "Apply calibration".
        </Text>
      )}
    </>
  );

  return (
    <MenuButton
      label="Calibration"
      tooltipPlacement="bottom"
      icon={<AiOutlineCompass />}
      popoverPlacement="left"
      popoverContent={menu}
    />
  );
};
