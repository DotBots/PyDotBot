Lighthouse calibration tool
===========================

This tool can be used to generate the calibration matrices and constants used
to compute the relative positions from raw lighthouse data.

Workflow
--------

1. Generate a `csv` file containing the positions from camera view using the
  controller in calibration mode:
  ```
  dotbot-controller --calibrate --calibration-dir <output directory>
  ```

2. Wait a few seconds and let the DotBots move in the scene. All camera points
  are stored in a CSV file called `calibration.csv` under `<output directory>`.

3. Once you think you have enougth samples, run this tool:
  ```
  dotbot-generate-lh2-calibration <output directory>
  ```
  This will generate a file called `calibration.out` under `<output directory>`

Use the calibration file
------------------------

Run the dotbot controller and specify the calibration directory, so it can find
the generated calibration data:

```
dotbot-controller --calibration-dir <output directory>
```
