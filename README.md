# LandmarkConversion

Convert 3D landmarks between formats, using the matching mesh when going between
XYZ and barycentric (triangle-index + weights) representations.

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

`point = u·A + v·B + (1−u−v)·C`, with `A, B, C` the triangle's vertices in file order and
`tri` the 0-based face index. Meshes are loaded with `process=False` so face order matches
the file exactly. Note `legacy/barycentric_to_3dslicer_markup.py` used a different
convention (`(1−u−v)·A + u·B + v·C`).

## Building the Windows .exe

```bash
pyinstaller landmark_convert.spec   # -> dist/landmark_convert.exe (drag landmark files onto it)
```

## legacy/

Original single-purpose scripts, kept for reference:
`3dslicer_markup_to_barycentric.py`, `3matic_xml_to_barycentric.py`,
`barycentric_to_3dslicer_markup.py`, and `lmk_converter_script.py` (batch Wrap 3D bary `.txt`
+ `.stl` → `.mrk.json` over a hard-coded folder – now covered by
`landmark_convert.py <folder> --pattern "*.txt" --to slicer_mrk_json`).
