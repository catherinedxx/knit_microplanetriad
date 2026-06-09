# Post-Processing ODB Results with Python

`Postprocess.py` — batch-generates **deformed contour plots + force-displacement curves** and animations from Abaqus ODB files.

---

## Features

1. Iterates all steps / frames, rendering **3D deformed contour plots** (matplotlib Poly3DCollection) with a fixed global legend range
2. Extracts history output, generates **cumulative force-displacement curves** (past trajectory in grey, last two segments in blue, current point highlighted in red)
3. **Left-right composite** of curve + contour (curve on the left, contour on the right)
4. **ffmpeg MP4 encoding** — outputs 3 independent videos (contour / curve / composite) with identical frame rate and duration for synchronized playback
5. **Batch processing**: multiple ODBs × multiple field components → automatic Cartesian product

---

## Dependencies

| Dependency | Purpose | Installation |
|------------|---------|--------------|
| Abaqus | ODB reading (odbAccess) | Pre-installed; locate the `abq2022` binary |
| matplotlib | 3D contour + curve rendering | Bundled with Abaqus Python |
| numpy | Numerical computation | Bundled with Abaqus Python |
| Pillow | Image stitching | Bundled with Abaqus Python |
| ffmpeg | MP4 video encoding | Download from [ffmpeg.org](https://ffmpeg.org) and add to PATH |

---

## How to Run

The script runs under the **Abaqus Python interpreter** (`abq2022 python`). No CAE license required — only a Solver license is needed to read ODB files.

### Step 1: Locate the `abq2022` Binary

Abaqus installation paths vary by machine. Common methods to find it:

```bash
# Method 1: locate the executable directly
which abq2022
# Typical output: /usr/local/DassaultSystemes/SIMULIA/Commands/abq2022

# Method 2: list Abaqus command directory
ls /usr/local/DassaultSystemes/SIMULIA/Commands/abq*
# On Windows:
dir "C:\SIMULIA\Commands\abq*.bat"

# Method 3: check common install locations
# Linux / macOS typical paths:
#   /usr/local/DassaultSystemes/SIMULIA/Commands/abq2022
#   /opt/abaqus/Commands/abq2022
# Windows typical paths:
#   C:\SIMULIA\Commands\abq2022.bat
#   C:\Program Files\Dassault Systemes\SIMULIA\Commands\abq2022.bat
```

Verify it works:

```bash
abq2022 python -c "print('Abaqus Python OK')"
# Output: Abaqus Python OK
```

> **Note**: If `abq2022` is not in your PATH, use the **full path** in place of `abq2022` in the commands below:
> ```bash
> /usr/local/DassaultSystemes/SIMULIA/Commands/abq2022 python code/Postprocess.py ...
> ```

### Step 2: Run the Script

```bash
# Single ODB, single component (auto legend range)
abq2022 python code/Postprocess.py \
    --odb results/Job-4.odb \
    --components S11 \
    --output results/postprocess

# Fixed legend range
abq2022 python code/Postprocess.py \
    --odb results/Job-4.odb \
    --components S11 \
    --legend-min 0 --legend-max 300000

# Batch: 3 ODBs × 2 components = 6 output sets
abq2022 python code/Postprocess.py \
    --odb results/Job-4.odb results/Job-5.odb results/Job-6.odb \
    --components S11 S22 \
    --output results/postprocess
```

---

## Command-Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--odb` | multi | `Job-4.odb` | ODB file path(s), space-separated |
| `--components` | multi | `S11` | Stress / field component name(s) (S11, S22, S33, S12, S13, S23) |
| `--output` | string | `postprocess_output` | Output root directory |
| `--field` | string | `S` | Field variable name (S / SDV1 / U, etc.) |
| `--legend-min` | float | auto | Legend lower bound; auto-computed from 2nd percentile if omitted |
| `--legend-max` | float | auto | Legend upper bound; auto-computed from 98th percentile if omitted |
| `--frame-step` | int | `1` | Take every N-th frame (1 = all frames) |
| `--fps` | int | `10` | Video frame rate (consistent across all 3 videos) |
| `--no-video` | flag | false | Generate frame images only, skip video encoding |
| `--dpi` | int | `150` | Output image DPI |
| `--deform-scale` | float | `1.0` | Deformation scale factor (>1 to amplify displacement) |
| `--view-elev` | float | `20.0` | 3D view elevation angle (degrees) |
| `--view-azim` | float | `-60.0` | 3D view azimuth angle (degrees) |
| `--step` | multi | all | Filter steps by index (1-based) or name, e.g. `--step 1 2` or `--step Step-1` |

### Auto Legend Range

When `--legend-min` / `--legend-max` are not specified, the script **pre-scans all frames** and uses the 2nd–98th percentile as the legend range, automatically excluding stress-concentration outliers for consistent animation coloring.

Manual override examples:

```bash
# Stress component S11 — symmetric range recommended
--legend-min -200000 --legend-max 200000

# Mises stress — one-sided range recommended
--field S --components "" --legend-min 0 --legend-max 300000
```

---

## Output Structure

Each (ODB, component) combination produces an independent subdirectory with **3 MP4 videos**:

```
postprocess/
└── Job-4/
    ├── S11/
    │   ├── contour/                              ← contour PNG sequence
    │   │   contour_00000.png
    │   │   contour_00001.png
    │   │   ...
    │   ├── curve/                                ← curve PNG sequence
    │   │   curve_00000.png
    │   │   curve_00001.png
    │   │   ...
    │   ├── composite/                            ← composite PNG sequence
    │   │   composite_00000.png
    │   │   ...
    │   ├── contour_Job-4_S11_animation.mp4       ← contour-only animation
    │   ├── curve_Job-4_S11_animation.mp4         ← curve-only animation
    │   └── Job-4_S11_animation.mp4               ← composite animation
    └── S22/
        ├── contour_Job-4_S22_animation.mp4
        ├── curve_Job-4_S22_animation.mp4
        └── Job-4_S22_animation.mp4
```

All three videos share the same frame rate (`--fps`) and frame count, so they can be played side-by-side in perfect sync.

---

## Configuring History Output

The script uses `Config.history_queries` to define which X-Y data to extract. The default is a Y-direction force-displacement curve:

```python
self.history_queries = kw.get("history_queries", [
    {"name": "RF2", "region": "ASSEMBLY.6", "variable": "RF2"},
    {"name": "U2",  "region": "ASSEMBLY.6", "variable": "U2"},
])
```

- `name` — label used in the curve plot
- `region` — Abaqus history region name (set name or node/element set, e.g. `ASSEMBLY.6`)
- `variable` — history output variable name (e.g. `RF2`, `U2`)

**If history extraction fails**, inspect the ODB manually in Abaqus/CAE to identify the correct history region names and variable names, then update the `history_queries` list in the `Config` class accordingly.

---

## Troubleshooting

### `abq2022` not found

```bash
# Try these paths one by one
ls /usr/local/DassaultSystemes/SIMULIA/Commands/abq*
ls /opt/abaqus/Commands/abq*
dir "C:\SIMULIA\Commands\abq*"

# Once found, use the full path
/usr/local/DassaultSystemes/SIMULIA/Commands/abq2022 python code/Postprocess.py ...
```

### ODB version too old

```
OdbError: The database is from a previous release of Abaqus.
```

Upgrade the ODB:

```bash
abq2022 -upgrade -job results/Job-4_upgraded -odb results/Job-4.odb
```

Then run the script with the upgraded `.odb` file.

### ffmpeg not found

```
[WARN] ffmpeg not found, skip video.
```

Download [ffmpeg](https://ffmpeg.org) and add it to PATH, or use `--no-video` to skip video encoding.

---

## Customizing Curve Appearance

Curve font sizes, colors, and marker sizes can be adjusted in the `Config` class and `plot_curve` function:

| Parameter | Location | Description |
|-----------|----------|-------------|
| `highlight_marker_size` | `Config.__init__` | Current-point marker size (default 80) |
| `highlight_color` | `Config.__init__` | Current-point marker color (default red) |
| `figure_width_inch` | `Config.__init__` | Curve figure width in inches (default 18) |
| `figure_height_inch` | `Config.__init__` | Curve figure height in inches (default 6) |
| xlabel / ylabel fontsize | inside `plot_curve` | Axis label font size (default 28) |
| title fontsize | inside `plot_curve` | Title font size (default 26) |
| tick labelsize | inside `plot_curve` | Tick label font size (default 24) |
| legend fontsize | inside `plot_curve` | Legend font size (default 24) |
