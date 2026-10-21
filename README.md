# Tree Detection & Counting (Module 7)

Aerial Analytics Platform plugin that detects tree crowns in RGB drone imagery, filters detections
by confidence, maps each tree to WGS84 coordinates, then reports tree count and density.

- **Plugin ID:** `tree-detection-counting`
- **Category:** `tree_detection`
- **Runtime:** Python >= 3.10 (tested on 3.10.11), no Rust
- **Repo:** [Lambdasz/Module-7-Potencial-Men](https://github.com/Lambdasz/Module-7-Potencial-Men)
- **Cross-module contract:** [CONTRACT.md](CONTRACT.md), required reading if you work on Modules 2, 3, 9, 10 or 11

The repo stands alone, separate from the core repo (`Aerial-Analytics-Platform`). Other modules
talk to it through six JSON files, not by importing code. The official schemas (`schemas/`) belong
to the core repo, so validating the contracts below needs a copy of it.

## Status

All eight features run and are covered by tests, the detection model included. The default
detector, `opencv_watershed`, is classical image processing: Excess Green, Otsu threshold,
morphology, distance transform, then a split for touching crowns. The choice comes down to no GPU,
no downloaded weights, and identical output for identical input, which keeps the tests offline.

The agreed deep-learning model, `deeplabv3plus`, is registered and wired: DeepLabV3+ with a
ResNet101 or Xception encoder, built from segmentation-models-pytorch, run tile by tile, and turned
into one box per crown with the mean canopy probability as its confidence. It is an option, not the
default, for one reason only: it needs a checkpoint from training, and no such checkpoint exists yet.
Picking it without `model_path` fails with a message naming the parameter instead of returning zero
trees that look like an empty orchard.

What to know before trusting the numbers:

- Accuracy on dense tropical canopy has not been measured, for either detector. Synthetic images
  prove the wiring, not the accuracy.
- `deeplabv3plus` needs torch and segmentation-models-pytorch, which stay commented out in
  `requirements.txt`. The healthcheck lists them as optional, so a machine without them still
  reports the plugin as healthy for the default detector.
- RGB only. No tree height, volume, biomass or species. The contract states this so Module 3 does
  not wait for fields that are not coming.
- Manual correction (Feature 7) is implemented and tested but not wired to the UI. That needs a new
  Tauri command in core, which is Module 2's call.

## Layout

```text
.
├── manifest.json            # Contract 1: plugin identity and runtime
├── parameters.json          # Contract 2: user-facing parameters (Module 2 form)
├── inputs.json              # Contract 3: inputs it needs (image format, metadata, AOI)
├── outputs.json             # Contract 4: metrics and artifacts it produces
├── execution_payload.json   # Fixture: sample payload from the host
├── execution_result.json    # Fixture: sample result written by the plugin
├── main.py                  # CLI entrypoint (I/O layer)
├── requirements.txt
├── CONTRACT.md              # Module 7 contract for other modules
├── treedet/                 # Core logic (pure functions)
│   ├── models.py            # Shared data models (Pydantic v2, immutable)
│   ├── errors.py            # PluginExecutionError and subclasses
│   ├── detectors.py         # Detection model registry, opencv_watershed and deeplabv3plus
│   ├── detection.py         # Feature 1: detect_trees (+ cross-tile dedup)
│   ├── counting.py          # Feature 2: count_trees
│   ├── filtering.py         # Feature 3: filter_by_confidence
│   ├── location.py          # Feature 4: map_tree_locations
│   ├── area.py              # Feature 5: count_trees_in_area (+ polygon area)
│   ├── density.py           # Feature 6: calculate_tree_density
│   ├── review.py            # Feature 7: apply_review
│   ├── output.py            # Feature 8: build_plugin_output -> execution_result
│   └── pipeline.py          # Wires the payload through the features above
└── tests/                   # Unit tests, detector tests and end-to-end tests (unittest)
```

## Setup

Keep the virtual environment **outside the repo**, so `git status` stays clean and tool caches do not
end up in it.

```powershell
py -3.10 -m venv $HOME\.venvs\aerial-m7
& $HOME\.venvs\aerial-m7\Scripts\Activate.ps1
pip install -r requirements.txt
pip install ruff check-jsonschema   # dev tools, not plugin dependencies
```

On Linux/macOS: `python3.10 -m venv ~/.venvs/aerial-m7 && source ~/.venvs/aerial-m7/bin/activate`.

## Running

```bash
# Healthcheck (Module 2 calls this before showing the plugin as active)
python main.py --healthcheck

# Analysis
python main.py --input <execution_payload.json> --output <result.json>
```

`execution_payload.json` points at a placeholder image path (`/absolute/path/...`), so running it as
it is gives `status: "failure"` with the message `Image not found`. That is deliberate: it shows the
plugin failing cleanly instead of crashing. Point `target.image_path` at a real image to walk the
success path.

## Tests

```bash
python -m unittest discover -s tests -v
```

Coverage spans all eight features plus the edge cases from the spec: no detections (`0`, not an
error), threshold outside 0-1 (rejected by Pydantic), zero area (`ZeroAreaError`), invalid GeoJSON
(`InvalidGeometryError`), missing image (`PluginExecutionError`), unsupported format
(`UnsupportedFormatError`), and unreadable image (`PluginExecutionError`).

Detector tests use synthetic images: green circles on a dark background, with a known count. They
prove the pipeline and the split of touching crowns, not accuracy on real photographs.

## Lint and format

```bash
ruff check .
ruff format --check .
```

## Contract validation

The schemas live in the core repo, so run these from a copy of it, pointing at this repo:

```bash
check-jsonschema --schemafile schemas/plugin.schema.json            <this-repo>/manifest.json
check-jsonschema --schemafile schemas/parameters.schema.json        <this-repo>/parameters.json
check-jsonschema --schemafile schemas/inputs.schema.json            <this-repo>/inputs.json
check-jsonschema --schemafile schemas/outputs.schema.json           <this-repo>/outputs.json
check-jsonschema --schemafile schemas/execution_payload.schema.json <this-repo>/execution_payload.json
check-jsonschema --schemafile schemas/execution_result.schema.json  <this-repo>/execution_result.json
```

## Design (functional style)

- **Pure core, impure shell.** Everything in `treedet/` is pure: same input, same output, no I/O.
  The one exception is `detect_trees`, because the detector has to read the image. File reads and
  writes, the clock and the exit code live in `main.py` only.
- **Immutable data.** Every Pydantic model uses `frozen=True`, and lists are tuples. Functions never
  mutate their input; changes go through `model_copy(update=...)`.
- **Time is a parameter.** `count_trees` and `analyze` take `counted_at` from the caller instead of
  reading the clock, which keeps results testable and repeatable.
- **Detector as a function.** A detection model is a plain function registered in a registry, so
  tests can substitute a fake detector and skip real models.
- **Errors stay contained.** `main.py` catches every `PluginExecutionError` subclass and writes a
  `failure` result. The plugin never dies without writing a result, which Module 2 requires.

## Adding a detection model

1. Write a function `(image_path: str, model_config: Mapping) -> Sequence[tuple[BBox, float]]` in
   `treedet/detectors.py`. It returns crown boxes in pixels with a 0-1 confidence.
2. Register it in `DETECTORS`, for example `"deeplabv3plus": deeplabv3plus_detector`.
3. Add the name to `options` of the `detector` parameter in `parameters.json`.
4. Add the package to `requirements.txt` and to `check_dependencies()` in `main.py`. A package the
   detector needs on top of the default one belongs in `check_optional_dependencies()` instead, so a
   missing torch does not make the whole plugin look broken.
5. If it uses a GPU, adjust `execution.gpu` in `manifest.json`.

The detector handles tiling itself (size comes from `model_config["tile_size"]`) and the inference
step. Cross-tile dedup, confidence filtering, georeferencing and counting are already in the
pipeline. Any new parameter a model needs has to be passed along in `pipeline.model_config_of`,
otherwise the value reaches the form and then gets ignored in silence.

## Known limits

- One image per run (`granularity: single_image`). No mosaics, and no GeoTIFF carrying its own
  transform.
- Georeferencing assumes a nadir image with its centre exactly on the GPS point, offsets it by the
  GSD and rotates it by `rotation_deg`. Error grows on orthomosaics or tilted cameras.
- Crowns closer together than half a radius read as a single tree, because the split relies on
  distance transform peaks.
- A crown sitting exactly on a tile boundary can be reported a few pixels off, since dedup keeps the
  copy with the higher confidence.
- Without `gsd_m` and `rotation_deg` from Module 1, the plugin falls back to the `gsd_cm` parameter
  (default 3 cm/px) and zero rotation.
- `deeplabv3plus` cannot run at all without a checkpoint, and a checkpoint trained with another
  encoder or with two output classes is rejected when the weights are loaded.
- Inference in `deeplabv3plus` runs on CPU when no CUDA device is present. One 24 MP photo is far
  slower than the 300 s timeout in `manifest.json` allows, so measure before pointing it at a full
  flight session.
