# Module 7 Contract: Tree Detection & Counting

> Audience: the Module 2 (Plugin Manager), 3 (Map Explorer), 9 (Area & Plot), 10 (Temporal) and 11
> (Dashboard) teams.
> Status: **draft v0.2.0, not final**. The [Open questions](#6-open-questions) section is waiting on
> answers from the teams involved. Field names in this document match the code exactly.

This document describes what Module 7 **takes in** and **gives back**. Other modules do not need to
read Module 7's Python to use it.

## 1. How Module 7 is invoked

Module 7 exposes no functions that Rust or React calls directly. Module 2 runs it as a **separate
process**, following the `plugins/template` pattern:

```text
python main.py --healthcheck                                  → exit 0 healthy / 1 unhealthy
python main.py --input <payload.json> --output <result.json>  → exit 0 done / 1 failed
```

All data moves through JSON files validated against the schemas in `schemas/`:

```text
M1 (image + metadata) ─┐
M3 (AOI) ──────────────┼─► M2 builds execution_payload.json ─► Module 7 ─► execution_result.json
                       │                                               ├─► <id>_tree_points.geojson
                       │                                               └─► <id>_plugin_output.json
                       └──────────────────── M3 / M9 / M10 / M11 read results through M2
```

When the plugin fails (missing image, broken GeoJSON, and so on) it **still** writes `result.json`
with `status: "failure"` and a message in `error`, then exits with code 1.

## 2. Input (from Modules 1, 2 and 3)

Follows `schemas/execution_payload.schema.json`. Fields Module 7 reads:

| Payload field                         | Required | Source     | Used for                                                                       |
| :------------------------------------ | :------: | :--------- | :----------------------------------------------------------------------------- |
| `execution_id`                        |   yes    | M2         | artifact file names and the `execution_id` in the result                       |
| `session_id`                          |   no     | M1/M2      | `project_id` in the result metadata                                            |
| `output_dir`                          |   yes    | M2         | directory the artifacts are written to                                         |
| `target.image_path`                   |   yes    | M1         | RGB image (`.jpg` `.jpeg` `.png` `.tif` `.tiff`)                               |
| `target.metadata.gps` `{lat, lon}`    | **yes**  | M1         | centre of the image (WGS84)                                                    |
| `target.metadata.resolution` `[w, h]` | **yes**  | M1         | image size in pixels                                                           |
| `target.metadata.gsd_m`               |   no*    | M1         | metres per pixel                                                               |
| `target.metadata.rotation_deg`        |   no     | M1         | clockwise rotation from north to the top edge of the image, default `0`         |
| `target.metadata.image_id`            |   no     | M1         | image id; defaults to the file name without extension                          |
| `aoi.geometry`                        |   no     | M3         | WGS84 GeoJSON `Polygon`/`MultiPolygon`; only trees inside it are counted       |
| `parameters.*`                        |   yes    | M2 (form)  | see the parameter table below                                                  |

\* When `gsd_m` is absent, the `gsd_cm` parameter is used instead (default 3 cm/px).

**Parameters** (`parameters.json`, rendered by Module 2 as a form):

| `name`                 | Type        | Default            | Description                                      |
| :--------------------- | :---------- | :----------------- | :----------------------------------------------- |
| `confidence_threshold` | number 0-1  | `0.5`              | detections below this are dropped                |
| `density_unit`         | select      | `per_ha`           | `per_ha` or `per_m2`                             |
| `detector`             | select      | `opencv_watershed` | detection model; `stub` = placeholder (0 trees)  |
| `iou_threshold`        | number 0-1  | `0.5`              | overlap limit for cross-tile dedup               |
| `tile_size`            | number (px) | `1024`             | inference tile size                              |
| `gsd_cm`               | number      | `3.0`              | fallback when the metadata carries no `gsd_m`    |

## 3. Output

### 3.1 `execution_result.json` (read by Module 2, then passed on to other modules)

`status`: `success`, `warning` (finished with a note, for instance when the `stub` detector ran), or
`failure`.

**Metrics** (`metrics`):

| Key                      | Type    | Meaning                                                                        |
| :----------------------- | :------ | :----------------------------------------------------------------------------- |
| `tree_count`             | integer | trees after confidence filtering, **inside the AOI** when one is given         |
| `avg_confidence`         | float   | mean confidence of the trees counted (0-1)                                     |
| `removed_low_confidence` | integer | detections dropped for falling under the threshold                             |
| `trees_outside_aoi`      | integer | detections outside the AOI (`0` when there is no AOI)                          |
| `analysis_area_m2`       | float   | AOI area, or the image footprint area when there is no AOI                     |
| `tree_density`           | float   | `tree_count / analysis_area_m2` in `tree_density_unit`                         |
| `tree_density_unit`      | string  | `per_ha` or `per_m2`                                                           |

**Artifacts** (`artifacts`):

| Key             | Format                 | Contents                                  |
| :-------------- | :--------------------- | :---------------------------------------- |
| `tree_points`   | `application/geo+json` | one point per tree (see 3.2)              |
| `plugin_output` | `application/json`     | the full `PluginOutput` (see 3.3)         |

### 3.2 `tree_points`: GeoJSON FeatureCollection

One `Feature` per counted tree. Coordinates are `[longitude, latitude]` in EPSG:4326 (RFC 7946).

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "DJI_0042-deepforest-0001",
      "geometry": { "type": "Point", "coordinates": [116.8535, -1.2445] },
      "properties": {
        "detection_id": "DJI_0042-deepforest-0001",
        "confidence": 0.93,
        "area_m2": 18.4,
        "bbox_px": [1990.0, 1490.0, 2010.0, 1510.0]
      }
    }
  ]
}
```

- `detection_id` is shaped `{image_id}-{model_name}-{4 digit number}`. Detections added by hand
  through Detection Review start with `manual-`.
- `area_m2` is the estimated crown box area (`pixel bbox area × gsd_m²`).
- `bbox_px` is `[x_min, y_min, x_max, y_max]` in original image pixels, for drawing boxes over the
  photo.

### 3.3 `plugin_output`: full structure

Matches the `PluginOutput` model in Module 7's progress report (`treedet/models.py`):

```json
{
  "status": "success",
  "detections": [
    {
      "detection_id": "...",
      "bbox": { "x_min": 0, "y_min": 0, "x_max": 0, "y_max": 0 },
      "confidence": 0.93,
      "center": { "latitude": -1.2445, "longitude": 116.8535 },
      "area_m2": 18.4
    }
  ],
  "statistics": {
    "total_trees": 42,
    "avg_confidence": 0.81,
    "counted_at": "2026-09-21T09:15:00+00:00",
    "density_value": 5.03,
    "density_unit": "per_ha",
    "area_m2": 83470.2,
    "removed_low_confidence": 7,
    "threshold_used": 0.5,
    "plot_id": "aoi",
    "trees_outside_area": 5
  },
  "geojson": "<string holding the tree_points above>",
  "metadata": {
    "plugin_version": "0.1.0",
    "model_name": "deepforest",
    "model_version": null,
    "executed_at": "2026-09-21T09:15:00+00:00",
    "device": "cpu",
    "image_id": "DJI_0042",
    "project_id": "session_20260921_01",
    "processing_time_s": 2.1,
    "warnings": []
  }
}
```

`PluginOutput` status maps onto the official schema: `success → success`, `partial → warning`,
`failed → failure`.

## 4. Per consuming module

| Module                | What it uses                                                                       | Notes                                                                                                                                                                                                                                                                                                                                                                            |
| :-------------------- | :--------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **M2** Plugin Manager | the CLI in section 1; `manifest.json`, `parameters.json`, `inputs.json`, `outputs.json` | all pass `check-jsonschema` against `schemas/`                                                                                                                                                                                                                                                                                                                                  |
| **M3** Map Explorer   | the `tree_points` artifact                                                         | layer_hint `point_marker`. M3's example in `docs/examples/spatial-result.example.json` uses the `spatial_results` shape; M3 only needs to turn each `Feature` into `{source, geometry, properties}` with `source = "tree-detection-counting"`. `height_est_m` is **not** available, since a single RGB image says nothing about height |
| **M9** Area & Plot    | `tree_points` or `plugin_output.detections[].center`                               | count per plot with point-in-polygon against M9's `Plot.rings`. Alternative: M2 runs Module 7 with `aoi` set to one plot, then `tree_count` is the count for that plot                                                                                                                                                                                                            |
| **M10** Temporal      | the `tree_count` metric from two runs (different dates)                            | only compare when `confidence_threshold`, `detector` and the AOI match                                                                                                                                                                                                                                                                                                           |
| **M11** Dashboard     | every `metrics` entry plus `plugin_output.statistics`                              | labels and units live in `outputs.json`                                                                                                                                                                                                                                                                                                                                          |

## 5. Public functions inside the plugin

For fellow Python developers and testers, the `treedet` package exports the functions from Module
7's progress report. All of them are pure except `detect_trees`.

| Feature                 | Function                                                                                   |
| :---------------------- | :----------------------------------------------------------------------------------------- |
| 1 Tree Detection        | `detect_trees(input_data, model_config) -> DetectionOutput`                                |
| 2 Tree Counting         | `count_trees(detections, image_id, counted_at) -> CountOutput`                             |
| 3 Confidence Filtering  | `filter_by_confidence(detections, threshold) -> FilteredOutput`                            |
| 4 Tree Location Mapping | `map_tree_locations(detections, image_metadata) -> LocationOutput`                         |
| 5 Area-Based Counting   | `count_trees_in_area(tree_points, plot_boundary) -> AreaCountOutput`                       |
| 6 Tree Density          | `calculate_tree_density(tree_count, area_m2, unit="per_ha") -> DensityOutput`              |
| 7 Detection Review      | `apply_review(detections, corrections) -> ReviewOutput`                                    |
| 8 Plugin Output         | `build_plugin_output(detections, count, density, locations, run_metadata) -> PluginOutput` |

Where this differs from the progress report, and why:

- `manifest.json` uses the official `schemas/plugin.schema.json` shape. That schema rejects the
  `input_schema`, `output_schema` and `config` fields from the report's appendix, so their contents
  moved to `inputs.json`, `outputs.json` and `parameters.json`.
- `count_trees` takes `image_id` and `counted_at` as arguments. Without them, `image_id` is unknown
  when nothing was detected, and reading the clock inside the function would make it impure.
- `TreeDetection.center` and `area_m2` are `null` before Feature 4 runs, because the detector only
  knows pixel positions.
- `image_id` and `project_id` are not part of the official payload schema, so they come from
  `target.metadata.image_id` (or the file name) and `session_id`.
- The `partial`/`failed` statuses map to `warning`/`failure` in the official result schema.

## 6. Open questions

|  #  | Question                                                                                                                                                                                                                                            | With       | Module 7 proposal                                                                              |
| :-: | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------- | :--------------------------------------------------------------------------------------------- |
|  1  | Can M1 fill in `gsd_m`, `rotation_deg` and `image_id` under `target.metadata`? GSD can be derived from relative altitude, focal length and sensor size; rotation from `gimbal_yaw_degree`                                                             | M1, M2     | yes, with the exact field names from the input table                                           |
|  2  | Counting per plot: aggregate points in M9, or have M2 run Module 7 once per plot?                                                                                                                                                                   | M2, M9     | aggregate in M9 (one run for all plots)                                                        |
|  3  | Detection Review needs somewhere to store user corrections and a way to hand them to the plugin. That needs a new Tauri command in core                                                                                                             | M2         | M2 adds a command to save corrections; Module 7 takes the correction file path as a parameter  |
|  4  | Who converts the GeoJSON into M3's `spatial_results` shape?                                                                                                                                                                                         | M3         | M3 (the plugin keeps emitting standard GeoJSON)                                                |
|  5  | Which detection model gets used, classical OpenCV or something deep learning based such as DeepForest?                                                                                                                                              | lecturer/team | Module 7 decides this; it does not change this contract                                     |
|  6  | The plugin now lives in its own repo (`Module-7-Potencial-Men`). Should the copy in the core repo's `plugins/tree_detection/` be deleted?                                                                                                           | M2         | delete it after the new repo is pushed, so there is no second source of truth                   |

## 7. Version history

| Version | Date       | Change                                                                                          |
| :------ | :--------- | :---------------------------------------------------------------------------------------------- |
| 0.2.0   | 2026-10-18 | `opencv_watershed` becomes the default detector; plugin moves to its own repo `Module-7-Potencial-Men` |
| 0.1.0   | 2026-09-21 | First draft: plugin skeleton, input/output contract, `stub` detector                            |
