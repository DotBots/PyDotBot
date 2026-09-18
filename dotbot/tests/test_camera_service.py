"""Tests for the camera service: the warp, the two threads and the detector.

No route is exercised here. These drive `CameraService` through the same
`open_source` seam a scripted capture is handed in on, on the synthetic
sheet frame and on a colour variant carrying one robot drawn from the
estimator's own outline. That makes the whole path frame -> warp -> raster
-> detect -> frame millimetres checkable with no camera in the room, and
the accuracy it shows is the plumbing's, not a lens's.
"""

import dataclasses

import cv2
import numpy as np

from dotbot.camera.raster import MM_PER_PX
from dotbot.camera.service import CameraService
from dotbot.tests.camera_fixtures import (
    DEV_CORNER,
    ScriptedCapture,
    delivering,
    looping,
    registration_for,
    synthetic_colour_frame,
    wait_for_detection,
)


class ThrowingCapture(ScriptedCapture):
    """A capture that raises once it has delivered `good` frames."""

    def __init__(self, frame, good=2, fps=0.0):
        super().__init__([], fps=fps)
        self._frame = frame
        self._left = good

    def read(self):
        import time

        time.sleep(0.01)
        if self._left <= 0:
            raise RuntimeError("the device went away mid-read")
        self._left -= 1
        return True, self._frame


# The detector runs on its own thread inside the service, fed the warped
# array before it is encoded. These tests drive it through the same
# `open_source` seam the warp tests use, on a colour variant of the
# synthetic frame: the four sheets as the registration was solved on, plus
# one robot drawn from the estimator's own outline at a known place on the
# floor. That makes the whole path frame -> warp -> raster -> detect ->
# frame millimetres checkable with no camera in the room, and the accuracy
# it shows is the plumbing's, not a lens's.


class StubbornCapture(ScriptedCapture):
    """A device reporting colour controls it will not accept being set to."""

    def __init__(self, frame, reports):
        super().__init__([frame] * 20, fps=0.0)
        self._reports = reports

    def get(self, prop):
        if prop in self._reports:
            return self._reports[prop]
        return super().get(prop)

    def set(self, prop, value):
        return False


class RecordingLogger:
    """A logger that keeps what it was told, so a test can read it back."""

    def __init__(self):
        self.warnings = []

    def bind(self, **kwargs):
        return self

    def warning(self, message, **kwargs):
        self.warnings.append((message, kwargs))

    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def test_the_registered_white_balance_is_set_before_the_first_frame(synthetic_camera):
    """What settles is the light the camera was registered under.

    Exposure is recorded and compared but never set: a manual exposure the
    driver rounds to its own step can blow the image out, which costs every
    detection on the layer.
    """
    frame = cv2.imread(str(synthetic_camera.source))
    opened = []

    def open_source(source):
        capture = ScriptedCapture([frame] * 20, fps=0.0)
        opened.append(capture)
        return capture

    calibration = dataclasses.replace(
        synthetic_camera,
        controls={"auto_wb": 0.0, "wb_temperature": 4780.0, "exposure": 83.0},
    )
    service = CameraService(calibration, DEV_CORNER, open_source=open_source)
    assert service.start()
    try:
        was_set = opened[0].controls_set
        assert was_set[cv2.CAP_PROP_AUTO_WB] == 0.0
        assert was_set[cv2.CAP_PROP_WB_TEMPERATURE] == 4780.0
        assert cv2.CAP_PROP_EXPOSURE not in was_set
    finally:
        service.stop()


def test_colour_controls_that_will_not_take_are_warned_about_and_still_served(
    synthetic_camera,
):
    """A colour drift degrades detection; it does not invalidate the geometry.

    So it is a warning and a layer, where a mode mismatch is a warning and no
    layer at all.
    """
    frame = cv2.imread(str(synthetic_camera.source))
    reports = {cv2.CAP_PROP_AUTO_WB: 1.0, cv2.CAP_PROP_WB_TEMPERATURE: 6500.0}
    calibration = dataclasses.replace(
        synthetic_camera, controls={"auto_wb": 0.0, "wb_temperature": 4780.0}
    )
    logger = RecordingLogger()
    service = CameraService(
        calibration,
        DEV_CORNER,
        open_source=lambda source: StubbornCapture(frame, reports),
        logger=logger,
    )
    assert service.start()
    try:
        assert service.live
        assert any("colour controls" in message for message, _ in logger.warnings)
    finally:
        service.stop()


def test_a_registration_without_controls_warns_about_nothing(synthetic_camera):
    """An older registration holds the camera to nothing, and says nothing."""
    frame = cv2.imread(str(synthetic_camera.source))
    reports = {cv2.CAP_PROP_AUTO_WB: 1.0, cv2.CAP_PROP_WB_TEMPERATURE: 6500.0}
    assert synthetic_camera.controls == {}
    logger = RecordingLogger()
    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=lambda source: StubbornCapture(frame, reports),
        logger=logger,
    )
    assert service.start()
    try:
        assert logger.warnings == []
    finally:
        service.stop()


class RecordingDetector:
    """A detector that keeps what it was handed and finds nothing."""

    def __init__(self):
        self.frames = []

    def detect(self, bgr):
        from dotbot.camera.detection import Detection

        self.frames.append(bgr)
        return Detection("none", 0, None, 0.0)


def test_the_detector_sees_the_uncompressed_warp(synthetic_camera):
    """What the detector reads is the warp itself, never the served JPEG.

    JPEG chroma subsampling destroys the red-connector evidence the 180
    degree decision turns on, so the detector is fed before the encode.
    """

    frame = cv2.imread(str(synthetic_camera.source))
    detector = RecordingDetector()
    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=delivering(*([frame] * 20), fps=0.0),
        detector=detector,
    )
    assert service.start()
    try:
        assert wait_for_detection(service) is not None
    finally:
        service.stop()

    assert detector.frames
    seen = detector.frames[0]
    assert isinstance(seen, np.ndarray)
    expected = cv2.warpPerspective(frame, service.transform, service.raster)
    assert np.array_equal(seen, expected)


def test_a_colour_frame_with_a_robot_is_detected_in_frame_millimetres():
    """One robot on the floor, reported where it was drawn.

    The truth is in frame millimetres, so this exercises the whole path
    from the source frame through the warp and the raster back to
    millimetres, including the origin of the area.
    """

    from dotbot.camera.detection.pose import axes

    truth_mm = (1500.0, 500.0)
    heading = 37.0
    frame = synthetic_colour_frame(DEV_CORNER, [(truth_mm, heading)])
    calibration = registration_for(frame)
    service = CameraService(
        calibration,
        DEV_CORNER,
        open_source=delivering(*([frame] * 20), fps=0.0),
    )
    assert service.start()
    try:
        record = wait_for_detection(service)
    finally:
        service.stop()

    assert record is not None
    assert record["status"] == "found"
    assert record["area"] == "dev-corner"
    assert record["camera_id"] == calibration.id
    # The four sheets are in plain view and none of them is a robot.
    assert record["candidates"] == 1
    pose = record["pose"]
    assert np.allclose(pose["centre_mm"], truth_mm, atol=4.0)
    assert abs(((pose["heading_atan2_deg"] - heading) + 180) % 360 - 180) < 3.0
    assert abs(((pose["heading_deg"] - (heading - 90)) + 180) % 360 - 180) < 3.0
    _, forward = axes(pose["heading_atan2_deg"])
    centre = np.asarray(pose["centre_mm"])
    assert np.allclose(pose["photodiode_mm"], centre + forward * 29.0, atol=0.1)


def test_no_robot_reports_none_not_nothing(synthetic_camera):
    """An empty floor produces records saying so, not an absence of records."""

    frame = cv2.imread(str(synthetic_camera.source))
    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=delivering(*([frame] * 20), fps=0.0),
    )
    assert service.start()
    try:
        record = wait_for_detection(service)
    finally:
        service.stop()

    assert record is not None
    assert record["status"] == "none"
    assert "pose" not in record
    assert record["candidates"] == 0


def test_on_detection_is_called_off_the_warp_thread_and_survives_an_exception(
    synthetic_camera,
):
    """A callback that raises costs one record, never the stream."""
    import time

    frame = cv2.imread(str(synthetic_camera.source))
    seen = []

    def on_detection(record):
        seen.append(record)
        if len(seen) == 1:
            raise RuntimeError("the consumer fell over")

    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=looping(frame),
        on_detection=on_detection,
    )
    assert service.start()
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and len(seen) < 3:
            time.sleep(0.02)
        warps = service.held()[1]
        while time.monotonic() < deadline and service.held()[1] <= warps:
            time.sleep(0.02)
        assert len(seen) >= 3
        assert service.held()[1] > warps
    finally:
        service.stop()


def test_the_keep_mask_is_the_floor_the_camera_can_see(synthetic_camera):
    """Every pixel the warp had a source for, the printed sheets included.

    A sheet is not cut out: it carries no saturated colour, so the verifier
    throws it out on its own, and the sheets are lifted once the camera is
    registered anyway. Cutting them would blind an A4 of floor per corner
    for the rest of the run.
    """

    frame = cv2.imread(str(synthetic_camera.source))
    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=delivering(frame, fps=0.0),
    )
    assert service.start()
    try:
        mask = service.keep_mask
    finally:
        service.stop()

    width, height = service.raster
    assert mask.shape == (height, width)
    assert mask[height // 2, width // 2] == 255
    for marker in synthetic_camera.markers:
        x = int((marker.centre_mm[0] - DEV_CORNER.x) / MM_PER_PX)
        y = int((marker.centre_mm[1] - DEV_CORNER.y) / MM_PER_PX)
        assert mask[y, x] == 255


def test_the_keep_mask_stops_where_the_camera_stops_seeing_floor(synthetic_camera):
    """The same crop the coverage test uses: no source, so not floor."""

    columns = 900
    frame = cv2.imread(str(synthetic_camera.source))[:, :columns]
    cropped = dataclasses.replace(synthetic_camera, width=columns)
    service = CameraService(cropped, DEV_CORNER, open_source=delivering(frame, fps=0.0))
    assert service.start()
    try:
        mask = service.keep_mask
    finally:
        service.stop()

    edge = max(x for x, _ in service.coverage_mm)
    inside = int((edge - 40 - DEV_CORNER.x) / MM_PER_PX)
    outside = int((edge + 40 - DEV_CORNER.x) / MM_PER_PX)
    assert mask[250, inside] == 255
    assert mask[250, outside] == 0


def test_a_read_that_raises_ends_the_stream_rather_than_freezing_it(
    synthetic_camera,
):
    """A reader that died still holds a frame, and re-serving it is a lie."""
    import asyncio
    import threading
    import time

    frame = cv2.imread(str(synthetic_camera.source))
    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=lambda source: ThrowingCapture(frame),
    )
    assert service.start()
    try:
        name = f"Camera {DEV_CORNER.name}"
        alive = lambda: any(  # noqa: E731
            t.name == name and t.is_alive() for t in threading.enumerate()
        )
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and alive():
            time.sleep(0.02)
        assert not alive()
        assert service.held()[0] is not None

        async def drain():
            return [part async for part in service.parts()]

        assert asyncio.run(asyncio.wait_for(drain(), timeout=5.0))
    finally:
        service.stop()


def test_a_pose_that_will_not_convert_costs_one_record_not_the_detector(
    synthetic_camera,
):
    """Building the record is inside the per-frame guard, not beside it."""

    class BadPoseOnce:
        """Found on the first frame, with a pose `frame_pose` cannot read."""

        def __init__(self):
            self.calls = 0

        def detect(self, bgr):
            from dotbot.camera.detection import Detection

            self.calls += 1
            if self.calls == 1:
                return Detection("found", 1, object(), 0.0)
            return Detection("none", 0, None, 0.0)

    frame = cv2.imread(str(synthetic_camera.source))
    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=looping(frame),
        detector=BadPoseOnce(),
    )
    assert service.start()
    try:
        record = wait_for_detection(service)
    finally:
        service.stop()

    assert record is not None
    assert record["status"] == "none"


def test_stop_joins_the_detector_thread(synthetic_camera):
    import threading

    frame = cv2.imread(str(synthetic_camera.source))
    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=delivering(*([frame] * 20), fps=0.0),
    )
    assert service.start()
    assert wait_for_detection(service) is not None
    service.stop()

    name = f"Camera {DEV_CORNER.name} detect"
    assert not any(t.name == name and t.is_alive() for t in threading.enumerate())
    assert service.held_detection() == (None, 0)


class BlockingDetector:
    """A detector held inside `detect` until the test lets it out."""

    def __init__(self):
        import threading

        self.release = threading.Event()
        self.entered = threading.Event()

    def detect(self, bgr):
        from dotbot.camera.detection import Detection

        self.entered.set()
        self.release.wait(timeout=5.0)
        return Detection("none", 0, None, 0.0)


def test_a_stuck_detector_does_not_stall_the_warp(synthetic_camera):
    """The warp and the stream never wait on the detector.

    The slot between the threads holds one frame, so a detector slower than
    the warp costs frames it never sees and nothing else. Measured against a
    detector that does not return at all, which is the limit of slow.
    """
    import time

    frame = cv2.imread(str(synthetic_camera.source))
    detector = BlockingDetector()
    service = CameraService(
        synthetic_camera,
        DEV_CORNER,
        open_source=looping(frame),
        detector=detector,
    )
    assert service.start()
    try:
        assert detector.entered.wait(timeout=5.0)
        start = service.held()[1]
        time.sleep(0.8)
        warps = service.held()[1] - start
        # The cap is 10 warps a second; a warp thread waiting on this
        # detector would have managed one, and then stopped.
        assert warps >= 4, warps
        assert service.held()[0] is not None
        # Nothing was ever reported, because nothing ever came back.
        assert service.held_detection() == (None, 0)
    finally:
        detector.release.set()
        service.stop()
