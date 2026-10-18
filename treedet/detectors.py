"""Detection backends.

A detector is any function ``(image_path, model_config) -> Sequence[RawBox]``.
It returns crowns in pixel coordinates with a confidence; ids, de-duplication,
filtering and georeferencing are done by the rest of the pipeline, so a new model
only has to implement this one function and be added to ``DETECTORS``.

``model_config`` keys read here: ``gsd_cm`` (ground sampling distance, needed to
size the crown filters) and ``tile_size``.

numpy and opencv are imported inside the detector, not at module level, so that
``import treedet`` keeps working on a machine where they are not installed yet and
``--healthcheck`` can report them as missing instead of crashing.
"""

import importlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, NamedTuple

from .errors import PluginExecutionError
from .models import BBox

RawBox = tuple[BBox, float]
Detector = Callable[[str, Mapping[str, Any]], Sequence[RawBox]]

DEFAULT_GSD_CM = 3.0
DEFAULT_TILE_SIZE = 1024
OVERLAP_FRACTION = 0.25
MIN_CROWN_M = 1.0
MAX_CROWN_M = 8.0
MIN_PEAK_PX = 2.0
CONFIDENCE_DECIMALS = 3


class CrownLimits(NamedTuple):
    """Crown size limits in pixels, derived from the ground sampling distance."""

    max_px: float
    min_area_px: int


def stub_detector(image_path: str, model_config: Mapping[str, Any]) -> Sequence[RawBox]:
    """Placeholder that detects nothing. Lets the pipeline run end to end
    without a model, and is reported as a warning by the pipeline (Feature 8)."""
    return ()


def _require(module_name: str) -> Any:
    """Import a detector dependency, or fail with a message the user can act on."""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise PluginExecutionError(
            f"The detector needs '{module_name}': run 'pip install -r requirements.txt'"
        ) from exc


def _odd(value: float) -> int:
    """Nearest odd integer >= 3 (an OpenCV kernel needs a centre pixel)."""
    size = max(3, int(round(value)))
    return size if size % 2 else size + 1


def _tiles(width: int, height: int, tile_size: int) -> Iterator[tuple[int, int, int, int]]:
    """Half-open (x_min, y_min, x_max, y_max) windows covering the whole image.

    Neighbouring tiles overlap, so a crown cut by a tile edge is still complete in
    the next tile; the pipeline then removes the duplicate copy with the IoU rule.
    """
    overlap = max(1, int(tile_size * OVERLAP_FRACTION))
    step = max(1, tile_size - overlap)
    y_starts = range(0, max(height - overlap, 1), step)
    x_starts = range(0, max(width - overlap, 1), step)
    for y_min in y_starts:
        for x_min in x_starts:
            yield x_min, y_min, min(x_min + tile_size, width), min(y_min + tile_size, height)


def _exg_scaled(bgr: Any, np: Any, cv2: Any) -> Any:
    """Excess Green (2G - R - B) smoothed and stretched to 0-255 for Otsu."""
    blue, green, red = (channel.astype(np.float32) for channel in cv2.split(bgr))
    excess_green = 2.0 * green - red - blue
    smoothed = cv2.GaussianBlur(excess_green, (5, 5), 0)
    return cv2.normalize(smoothed, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def _crown_regions(mask: Any, distance: Any, np: Any, cv2: Any, smooth_px: float) -> Any | None:
    """Split touching crowns by growing every distance-transform peak outwards.

    Each crown pixel joins its nearest peak, so two touching crowns meet along the
    bisector between their peaks: the same marker-based region growing as a
    watershed on the distance transform, without ``cv2.watershed`` itself. That call
    was measured to shrink each crown to its core (a 5021 px synthetic disk came back
    as 5 px), because the background marker floods the low ramp around the crown.
    The transform is blurred before the peaks are taken, so that pixel noise does not
    create peaks of its own.

    Returns ``None`` when no peak was found, otherwise an int32 label image where 1
    is background and each crown is a label >= 2.
    """
    smoothed = cv2.GaussianBlur(distance, (0, 0), smooth_px)
    peaks = cv2.dilate(smoothed, np.ones((3, 3), np.uint8))
    strong = ((smoothed >= peaks - 1e-4) & (distance > MIN_PEAK_PX)).astype(np.uint8)

    peak_count, peak_image = cv2.connectedComponents(strong * 255, connectivity=8)
    if peak_count <= 1:
        return None

    _, nearest_peak = cv2.distanceTransformWithLabels(
        (peak_image == 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
    )
    return np.where(mask > 0, nearest_peak + 2, 1).astype(np.int32)


def _region_boxes(
    np: Any,
    cv2: Any,
    scaled: Any,
    distance: Any,
    regions: Any,
    limits: CrownLimits,
) -> Iterator[RawBox]:
    """One RawBox per crown region.

    Confidence blends three signals that do not depend on the image size: how green
    the region is (mean Excess Green), how much of its bounding box it fills, and how
    close the peak is to the centre (1.0 for a round crown).
    """
    for label in range(2, int(regions.max()) + 1):
        region = regions == label
        area = int(np.count_nonzero(region))
        if area < limits.min_area_px:
            continue

        ys, xs = np.nonzero(region)
        x_min, x_max = float(xs.min()), float(xs.max()) + 1
        y_min, y_max = float(ys.min()), float(ys.max()) + 1
        width, height = x_max - x_min, y_max - y_min
        if max(width, height) > 2 * limits.max_px:
            continue  # too large for a single crown, e.g. grass or a shadow

        greenness = float(scaled[region].mean()) / 255.0
        fill = min(1.0, area / (0.785 * width * height))
        roundness = min(1.0, 2.0 * float(distance[region].max()) / max(min(width, height), 1.0))
        confidence = 0.45 * greenness + 0.30 * fill + 0.25 * roundness
        yield (
            BBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max),
            round(min(1.0, confidence), CONFIDENCE_DECIMALS),
        )


def _detect_tile(
    tile: Any, np: Any, cv2: Any, open_px: int, limits: CrownLimits, smooth_px: float
) -> Iterator[RawBox]:
    """Crown regions of one tile, in tile coordinates."""
    scaled = _exg_scaled(tile, np, cv2)
    _, mask = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_px, open_px))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)  # drop specks
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # close holes in a crown

    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    if float(distance.max()) <= MIN_PEAK_PX:
        return
    regions = _crown_regions(mask, distance, np, cv2, smooth_px)
    if regions is None:
        return
    yield from _region_boxes(np, cv2, scaled, distance, regions, limits)


def opencv_watershed_detector(image_path: str, model_config: Mapping[str, Any]) -> Sequence[RawBox]:
    """Classic (not deep learning) crown detection: ExG, Otsu, morphology, distance peaks.

    The default detector: it needs no GPU, no model weights and no training data, and
    returns the same answer for the same image, which keeps the tests offline and
    repeatable. The image is processed in ``tile_size`` tiles.

    Raises ``PluginExecutionError`` when the image cannot be read or when numpy or
    opencv-python-headless is missing.
    """
    np = _require("numpy")
    cv2 = _require("cv2")

    bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if bgr is None:
        raise PluginExecutionError(f"Cannot read image: {image_path}")

    gsd_cm = float(model_config.get("gsd_cm") or DEFAULT_GSD_CM)
    tile_size = int(model_config.get("tile_size") or DEFAULT_TILE_SIZE)
    gsd_m = max(gsd_cm, 0.01) / 100.0

    min_crown_px = max(3.0, MIN_CROWN_M / gsd_m)
    limits = CrownLimits(
        max_px=max(2 * min_crown_px, MAX_CROWN_M / gsd_m),
        min_area_px=max(4, int(0.25 * min_crown_px**2)),
    )
    open_px = _odd(min_crown_px / 4)
    smooth_px = max(1.0, min_crown_px / 10)

    height, width = bgr.shape[:2]
    boxes: list[RawBox] = []
    for x_min, y_min, x_max, y_max in _tiles(width, height, tile_size):
        for bbox, confidence in _detect_tile(
            bgr[y_min:y_max, x_min:x_max], np, cv2, open_px, limits, smooth_px
        ):
            boxes.append(
                (
                    BBox(
                        x_min=bbox.x_min + x_min,
                        y_min=bbox.y_min + y_min,
                        x_max=bbox.x_max + x_min,
                        y_max=bbox.y_max + y_min,
                    ),
                    confidence,
                )
            )
    return tuple(boxes)


# A new model is one function with this signature, registered here and in the
# "detector" options of parameters.json.
DETECTORS: Mapping[str, Detector] = {
    "opencv_watershed": opencv_watershed_detector,
    "stub": stub_detector,
}
