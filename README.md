# LandmarkConversion

Convert 3D landmarks between formats, using the matching mesh when going between
XYZ and barycentric (triangle-index + weights) representations.

> **Which format should I use?**
>
> * **3D Slicer (`.mrk.json`) is the favoured format for viewing.** It opens directly in
>   [3D Slicer](https://www.slicer.org/) with labelled, nicely rendered points on top of the mesh,
>   so use it to look at, check and hand-edit landmarks.
> * **Barycentric (Wrap 3D `[[tri,u,v], ...]`) is the format for correspondence.** It stores each
>   landmark as *which triangle + where inside it* instead of a fixed position. Meshes that share
>   the same topology (same vertex/face order, e.g. all registered/wrapped to one template) can
>   therefore reuse one barycentric file: **landmark a single mesh, and every other mesh in the
>   same correspondence gets the equivalent landmarks for free** – just convert the barycentric
>   file against each mesh (`--to slicer_mrk_json --mesh other_case.obj`).
>
> This only works for meshes in correspondence; for an arbitrary scan with its own triangulation
> the triangle indices mean nothing, so landmark it (or register it to the template) first.

| Key (`--to`)      | Format                                   | Kind        |
|-------------------|------------------------------------------|-------------|
| `ljson`           | Menpo LJSON v2 (`.ljson`) – points + named groups + connectivity | XYZ |
| `slicer_mrk_json` | 3D Slicer markups (`.mrk.json`)          | XYZ         |
| `xml`             | 3-matic XML (`<Point><Name/><Coordinate/>`) | XYZ      |
| `xyz_txt`         | `[label] x y z` per line                 | XYZ         |
| `wrap3d_bary_txt` | Wrap 3D `[[tri,u,v], ...]` in a `.txt`   | Barycentric |

XYZ ↔ XYZ conversions don't need a mesh. XYZ ↔ barycentric needs the mesh the landmarks
belong to: by default the converter looks for a mesh with the same base name next to the
landmark file (`case.ljson` → `case.obj/.ply/.stl/...`; `case_wrap3d_bary.txt` → `case.obj`),
or pass `--mesh`.

## Usage

```bash
pip install -r requirements.txt

# LJSON -> Wrap 3D barycentric (mesh auto-found: "case01.obj")
python -u landmark_convert.py "case01.ljson" --to wrap3d_bary_txt

# ...and back to LJSON, restoring the group names + connectivity from a reference LJSON
python -u landmark_convert.py "case01_wrap3d_bary.txt" --to ljson --template "case01.ljson"

# Whole folder, outputs in their own folder
python -u landmark_convert.py path/to/cases --pattern "*.ljson" --to wrap3d_bary_txt --out-dir out/bary

# No --to: pick the target interactively (also how the drag-and-drop .exe works)
python -u landmark_convert.py case.ljson
```

Each run appends the date + exact command to `run_command.txt` in the output folder and
drops a copy of `landmark_convert.py` there (`--no-provenance` to skip).

### LJSON notes

* Point labels are written as `<group>-<index>` (e.g. `nose-11`), so LJSON → Slicer/XML/XYZ
  → LJSON rebuilds the groups automatically. Connectivity can't be stored in those formats, so
  pass `--template` to get it back.
* Barycentric files carry no labels at all – use `--template` when converting bary → LJSON,
  otherwise all points go into a single `all` group.
* xyz → bary snaps each point onto the closest triangle and prints the round-trip error
  (`--warn-dist D` flags any landmark further than `D` from the surface).

### Barycentric convention

`[tri, u, v]` with `tri` the 0-based face index, `w = 1−u−v`, and `A, B, C` the triangle's
vertices in file order. Two conventions are supported – pick with `--bary-convention`
(or the radio buttons in the app):

| `--bary-convention` | point                  | used by |
|---------------------|------------------------|---------|
| `standard` (default)| `u·A + v·B + w·C`      | `landmark_convert.py`, `legacy/lmk_converter_script.py` |
| `legacy`            | `w·A + u·B + v·C`      | `legacy/barycentric_to_3dslicer_markup.py` |

Use the same convention in both directions. If a bary file converts to points that sit on
the mesh but in the wrong places, it was written with the other convention.
Meshes are loaded with `process=False` so face order matches the file exactly.

## Drag-and-drop app (Windows + Linux)

`landmark_convert_gui.py` is a small window: drop landmark files or folders onto it (or onto
the app icon), choose the target format, barycentric convention and optional mesh / LJSON
template / output folder, then **Convert**. It runs the same code as the CLI and records the
equivalent command in `run_command.txt`.

```bash
python landmark_convert_gui.py            # run from source
```

Build standalone apps (PyInstaller can't cross-compile, so build each on its own OS):

```bash
# Linux  -> dist/linux/landmark-converter (GUI) + dist/linux/landmark-convert (CLI)
bash build_linux.sh             # add --install to put it in ~/.local/bin + your app menu

# Windows (cmd, in a Windows Python env) -> dist\windows\LandmarkConverter.exe + landmark_convert.exe
build_windows.bat
```

## legacy/

Original single-purpose scripts, kept for reference:
`3dslicer_markup_to_barycentric.py`, `3matic_xml_to_barycentric.py`,
`barycentric_to_3dslicer_markup.py`, and `lmk_converter_script.py` (batch Wrap 3D bary `.txt`
+ `.stl` → `.mrk.json` over a hard-coded folder – now covered by
`landmark_convert.py <folder> --pattern "*.txt" --to slicer_mrk_json`).
