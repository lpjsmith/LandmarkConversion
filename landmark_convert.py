# import os
# import re
# import json
# import glob
# import argparse
# import xml.etree.ElementTree as ET
# from dataclasses import dataclass
# from typing import List, Optional, Tuple, Literal

# import numpy as np
# import trimesh


# # ---------------------------
# # Data model
# # ---------------------------

# @dataclass
# class LandmarkSet:
#     # If xyz is available: Nx3 float
#     xyz: Optional[np.ndarray] = None

#     # If barycentric is available: list of (tri_index, u, v) where w = 1-u-v
#     bary: Optional[List[Tuple[int, float, float]]] = None

#     # Optional labels (if found in XML, etc.)
#     labels: Optional[List[str]] = None


# # ---------------------------
# # Utilities
# # ---------------------------

# def _strip_known_suffixes(filename: str) -> str:
#     """
#     For Slicer: 'case.mrk.json' -> 'case'
#     For bary outputs like 'case_bary.json' you may want base 'case' still.
#     """
#     base = os.path.basename(filename)

#     if base.lower().endswith(".mrk.json"):
#         return base[:-len(".mrk.json")]
#     for suf in ["_bary.json", "_bary.txt", ".json", ".txt", ".xml", ".csv"]:
#         if base.lower().endswith(suf):
#             return base[:-len(suf)]
#     return os.path.splitext(base)[0]


# def find_mesh_for_landmarks(landmark_path: str) -> Optional[str]:
#     """
#     Finds a mesh in the same folder with the same base name.
#     Checks common mesh extensions.
#     """
#     folder = os.path.dirname(os.path.abspath(landmark_path))
#     base = _strip_known_suffixes(landmark_path)

#     exts = [".obj", ".ply", ".stl", ".off", ".glb", ".gltf"]
#     candidates = []
#     for ext in exts:
#         p = os.path.join(folder, base + ext)
#         if os.path.exists(p):
#             candidates.append(p)

#     # If not exact match, try glob for base.*
#     if not candidates:
#         for p in glob.glob(os.path.join(folder, base + ".*")):
#             if os.path.splitext(p)[1].lower() in exts:
#                 candidates.append(p)

#     return candidates[0] if candidates else None


# def load_mesh(mesh_path: str) -> trimesh.Trimesh:
#     mesh = trimesh.load(mesh_path, force="mesh")
#     if not isinstance(mesh, trimesh.Trimesh):
#         mesh = mesh.dump(concatenate=True)
#     if mesh.is_empty or mesh.vertices.size == 0 or mesh.faces.size == 0:
#         raise ValueError(f"Mesh loaded but appears empty/invalid: {mesh_path}")
#     return mesh


# # ---------------------------
# # Slicer .mrk.json (XYZ)
# # ---------------------------

# def load_mrk_json(path: str) -> LandmarkSet:
#     with open(path, "r", encoding="utf-8") as f:
#         data = json.load(f)

#     cps = data["markups"][0]["controlPoints"]
#     pts = np.array([cp["position"] for cp in cps], dtype=float)
#     labels = [cp.get("label", "") for cp in cps]
#     return LandmarkSet(xyz=pts, labels=labels)


# def save_mrk_json(path: str, xyz: np.ndarray, labels: Optional[List[str]] = None) -> None:
#     if labels is None or len(labels) != len(xyz):
#         labels = [f"L{i+1}" for i in range(len(xyz))]

#     control_points = []
#     for i, p in enumerate(xyz):
#         control_points.append({
#             "id": str(i + 1),
#             "label": labels[i],
#             "description": "",
#             "associatedNodeID": "",
#             "position": [float(p[0]), float(p[1]), float(p[2])],
#             "orientation": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
#             "selected": True,
#             "locked": False,
#             "visibility": True,
#             "positionStatus": "defined"
#         })

#     out = {
#         "@schema": "https://raw.githubusercontent.com/Slicer/Slicer/master/Modules/Loadable/Markups/Resources/Schema/markups-schema-v1.0.0.json",
#         "markups": [{
#             "type": "Fiducial",
#             "coordinateSystem": "LPS",  # common in Slicer; adjust if you need RAS
#             "locked": False,
#             "labelFormat": "%N-%d",
#             "controlPoints": control_points,
#             "measurements": [],
#             "display": {
#                 "visibility": True,
#                 "opacity": 1.0,
#                 "color": [0.4, 1.0, 0.0],
#                 "selectedColor": [1.0, 0.5, 0.5],
#                 "propertiesLabelVisibility": False,
#                 "pointLabelsVisibility": True,
#                 "textScale": 3.0,
#                 "glyphType": "Sphere3D",
#                 "glyphScale": 1.0,
#                 "glyphSize": 5.0
#             }
#         }]
#     }

#     with open(path, "w", encoding="utf-8") as f:
#         json.dump(out, f, indent=2)


# # ---------------------------
# # Barycentric
# # ---------------------------

# def load_wrap3d_bary_txt(path: str) -> LandmarkSet:
#     # file contains JSON list like [[tri,u,v],[tri,u,v],...], but extension is .txt
#     with open(path, "r", encoding="utf-8") as f:
#         raw = f.read()
#     raw2 = raw.lstrip("\ufeff \t\r\n")
#     data = json.loads(raw2)
#     bary = [(int(t), float(u), float(v)) for (t, u, v) in data]
#     return LandmarkSet(bary=bary)

# def save_wrap3d_bary_txt(path: str, bary: List[Tuple[int, float, float]]) -> None:
#     # write JSON list, but to a .txt file
#     data = [[int(t), float(u), float(v)] for (t, u, v) in bary]
#     with open(path, "w", encoding="utf-8") as f:
#         json.dump(data, f, separators=(",", ":"))

# def compute_barycentric_for_point(point: np.ndarray, mesh: trimesh.Trimesh) -> Tuple[int, float, float]:
#     """
#     Return (triangle_index, u, v) where u and v are the first two
#     barycentric weights. The third = 1 - u - v.
#     """
#     closest, distance, tri_id = mesh.nearest.on_surface([point])
#     tri_id = int(tri_id[0])

#     tri = mesh.triangles[tri_id]  # (3,3)
#     a, b, c = tri

#     v0 = b - a
#     v1 = c - a
#     v2 = point - a

#     d00 = float(np.dot(v0, v0))
#     d01 = float(np.dot(v0, v1))
#     d11 = float(np.dot(v1, v1))
#     d20 = float(np.dot(v2, v0))
#     d21 = float(np.dot(v2, v1))

#     denom = d00 * d11 - d01 * d01
#     if abs(denom) < 1e-18:
#         # Degenerate triangle; fall back to something stable
#         return tri_id, 1.0, 0.0

#     v = (d11 * d20 - d01 * d21) / denom
#     w = (d00 * d21 - d01 * d20) / denom
#     u = 1.0 - v - w

#     return tri_id, float(u), float(v)


# def xyz_to_bary(xyz: np.ndarray, mesh: trimesh.Trimesh) -> List[Tuple[int, float, float]]:
#     out = []
#     for p in xyz:
#         tri, u, v = compute_barycentric_for_point(p, mesh)
#         out.append((tri, u, v))
#     return out


# def bary_to_xyz(bary: List[Tuple[int, float, float]], mesh: trimesh.Trimesh) -> np.ndarray:
#     pts = np.zeros((len(bary), 3), dtype=float)
#     tris = mesh.triangles  # (F,3,3)

#     for i, (tri_id, u, v) in enumerate(bary):
#         tri = tris[int(tri_id)]
#         a, b, c = tri
#         w = 1.0 - u - v
#         pts[i] = u * a + v * b + w * c
#     return pts


# def load_bary_json(path: str) -> LandmarkSet:
#     with open(path, "r", encoding="utf-8") as f:
#         raw = f.read()
#     raw2 = raw.lstrip("\ufeff \t\r\n")
#     data = json.loads(raw2)
#     bary = [(int(t), float(u), float(v)) for (t, u, v) in data]
#     return LandmarkSet(bary=bary)


# def save_bary_json(path: str, bary: List[Tuple[int, float, float]]) -> None:
#     data = [[int(t), float(u), float(v)] for (t, u, v) in bary]
#     with open(path, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=2)


# def load_bary_txt(path: str) -> LandmarkSet:
#     bary = []
#     with open(path, "r", encoding="utf-8") as f:
#         for line in f:
#             line = line.strip()
#             if not line or line.startswith("#"):
#                 continue
#             parts = re.split(r"[,\s]+", line)
#             if len(parts) < 3:
#                 continue
#             t = int(float(parts[0]))
#             u = float(parts[1])
#             v = float(parts[2])
#             bary.append((t, u, v))
#     if not bary:
#         raise ValueError("No barycentric rows found in txt.")
#     return LandmarkSet(bary=bary)


# def save_bary_txt(path: str, bary: List[Tuple[int, float, float]]) -> None:
#     with open(path, "w", encoding="utf-8") as f:
#         for (t, u, v) in bary:
#             f.write(f"{int(t)} {u:.10f} {v:.10f}\n")


# # ---------------------------
# # XYZ text (simple)
# # ---------------------------

# def load_xyz_txt(path: str) -> LandmarkSet:
#     pts = []
#     labels = []
#     with open(path, "r", encoding="utf-8") as f:
#         for line in f:
#             s = line.strip()
#             if not s or s.startswith("#"):
#                 continue
#             # allow: "label x y z" or "x y z"
#             parts = re.split(r"[,\s]+", s)
#             if len(parts) == 3:
#                 x, y, z = map(float, parts)
#                 pts.append([x, y, z])
#                 labels.append("")
#             elif len(parts) >= 4:
#                 lbl = parts[0]
#                 x, y, z = map(float, parts[1:4])
#                 pts.append([x, y, z])
#                 labels.append(lbl)
#     if not pts:
#         raise ValueError("No XYZ rows found in txt.")
#     return LandmarkSet(xyz=np.array(pts, dtype=float), labels=labels)


# def save_xyz_txt(path: str, xyz: np.ndarray, labels: Optional[List[str]] = None) -> None:
#     with open(path, "w", encoding="utf-8") as f:
#         if labels is not None and len(labels) == len(xyz):
#             for lbl, p in zip(labels, xyz):
#                 if lbl:
#                     f.write(f"{lbl} {p[0]:.10f} {p[1]:.10f} {p[2]:.10f}\n")
#                 else:
#                     f.write(f"{p[0]:.10f} {p[1]:.10f} {p[2]:.10f}\n")
#         else:
#             for p in xyz:
#                 f.write(f"{p[0]:.10f} {p[1]:.10f} {p[2]:.10f}\n")


# # ---------------------------
# # XML (best-effort)
# # ---------------------------

# def load_landmarks_xml(path: str) -> LandmarkSet:
#     """
#     Supports:
#     - 3-matic style:
#         <Entities xmlns:mat="urn:materialise">
#           <Point>
#             <Name>Point-001</Name>
#             <Coordinate>x y z</Coordinate>
#           </Point>
#         </Entities>

#       (also works if tags are namespaced like <mat:Point>)

#     - plus best-effort fallback patterns from older logic.
#     """
#     tree = ET.parse(path)
#     root = tree.getroot()

#     def local(tag: str) -> str:
#         # '{namespace}Tag' -> 'Tag', 'mat:Tag' -> 'Tag'
#         if "}" in tag:
#             tag = tag.split("}", 1)[1]
#         if ":" in tag:
#             tag = tag.split(":", 1)[1]
#         return tag

#     pts = []
#     labels = []

#     # --- First: explicit 3-matic parse (Point/Name/Coordinate) ---
#     point_elems = []
#     for elem in root.iter():
#         if local(elem.tag).lower() == "point":
#             point_elems.append(elem)

#     for p in point_elems:
#         name = None
#         coord_text = None

#         for child in list(p):
#             t = local(child.tag).lower()
#             if t == "name":
#                 name = (child.text or "").strip()
#             elif t == "coordinate":
#                 coord_text = (child.text or "").strip()

#         if coord_text:
#             parts = re.split(r"[,\s]+", coord_text.strip())
#             if len(parts) >= 3:
#                 try:
#                     x, y, z = map(float, parts[:3])
#                     pts.append([x, y, z])
#                     labels.append(name or "")
#                 except Exception:
#                     pass

#     if pts:
#         return LandmarkSet(xyz=np.array(pts, dtype=float), labels=labels)

#     # --- Fallback: best-effort older patterns ---
#     candidates = []
#     for tag in ["landmark", "Landmark", "point", "Point", "fiducial", "Fiducial"]:
#         candidates.extend(root.findall(f".//{tag}"))

#     def _try_attrs(elem):
#         keys = {k.lower(): v for k, v in elem.attrib.items()}
#         if all(k in keys for k in ["x", "y", "z"]):
#             x, y, z = float(keys["x"]), float(keys["y"]), float(keys["z"])
#             lbl = keys.get("name") or keys.get("label") or keys.get("id") or ""
#             return (x, y, z, lbl)
#         return None

#     def _try_children(elem):
#         kids = {local(c.tag).lower(): (c.text or "").strip() for c in list(elem)}
#         if all(k in kids for k in ["x", "y", "z"]):
#             x, y, z = float(kids["x"]), float(kids["y"]), float(kids["z"])
#             lbl = kids.get("name") or kids.get("label") or kids.get("id") or ""
#             return (x, y, z, lbl)
#         # also support Coordinate child in fallback
#         if "coordinate" in kids:
#             parts = re.split(r"[,\s]+", kids["coordinate"])
#             if len(parts) >= 3:
#                 x, y, z = map(float, parts[:3])
#                 lbl = kids.get("name") or kids.get("label") or kids.get("id") or ""
#                 return (x, y, z, lbl)
#         return None

#     def _try_text(elem):
#         text = (elem.text or "").strip()
#         if not text:
#             return None
#         parts = re.split(r"[,\s]+", text)
#         if len(parts) >= 3:
#             x, y, z = map(float, parts[:3])
#             return (x, y, z, "")
#         return None

#     used = set()
#     for elem in candidates:
#         if elem in used:
#             continue
#         used.add(elem)

#         got = _try_attrs(elem) or _try_children(elem) or _try_text(elem)
#         if got:
#             x, y, z, lbl = got
#             pts.append([x, y, z])
#             labels.append(lbl)

#     if not pts:
#         raise ValueError("XML parsed but no landmarks found (unsupported schema).")

#     return LandmarkSet(xyz=np.array(pts, dtype=float), labels=labels)


# def save_landmarks_xml(path: str, xyz: np.ndarray, labels: Optional[List[str]] = None) -> None:
#     if labels is None or len(labels) != len(xyz):
#         labels = [f"Point-{i+1:03d}" for i in range(len(xyz))]

#     # 3-matic style root (with namespace declaration like your example)
#     root = ET.Element("Entities", {"xmlns:mat": "urn:materialise"})

#     for lbl, p in zip(labels, xyz):
#         pt = ET.SubElement(root, "Point")
#         nm = ET.SubElement(pt, "Name")
#         nm.text = lbl
#         co = ET.SubElement(pt, "Coordinate")
#         co.text = f"{float(p[0])} {float(p[1])} {float(p[2])}"

#     tree = ET.ElementTree(root)
#     tree.write(path, encoding="utf-8", xml_declaration=True)


# # ---------------------------
# # Format detection
# # ---------------------------

# DetectedFormat = Literal["slicer_mrk_json", "wrap3d_bary", "xyz_txt", "xml"]

# DISPLAY_NAME = {
#     "slicer_mrk_json": "Slicer (.mrk.json) — XYZ",
#     "wrap3d_bary": "Wrap 3D — Barycentric ([[tri,u,v], ...])",
#     "xyz_txt": "XYZ (TXT)",
#     "xml": "3-matic XML",
# }


# def detect_format(path: str) -> DetectedFormat:
#     low = path.lower()

#     if low.endswith(".mrk.json"):
#         return "slicer_mrk_json"
#     if low.endswith(".xml"):
#         return "xml"

#     # --- JSON files ---
#     if low.endswith(".json"):
#         try:
#             with open(path, "r", encoding="utf-8") as f:
#                 data = json.load(f)
#             if isinstance(data, list) and data and isinstance(data[0], (list, tuple)) and len(data[0]) >= 3:
#                 return "bary_json"
#         except Exception:
#             pass
#         return "bary_json"

#     # --- TXT / CSV files ---
#     if low.endswith(".txt") or low.endswith(".csv"):
#         with open(path, "r", encoding="utf-8") as f:
#             raw = f.read()

#         # Strip BOM + whitespace
#         raw2 = raw.lstrip("\ufeff \t\r\n")

#         # If it looks like JSON, try parsing it first (THIS handles your file)
#         if raw2.startswith("[") or raw2.startswith("{"):
#             try:
#                 data = json.loads(raw2)
#                 if isinstance(data, list) and data and isinstance(data[0], (list, tuple)) and len(data[0]) >= 3:
#                     return "bary_json"
#             except Exception:
#                 # If it's bracketed but not valid JSON, it's definitely NOT xyz
#                 # (prevents falling through to xyz parser and crashing)
#                 return "bary_txt"

#         # Line-based sniffing (only for non-JSON-looking txt)
#         for line in raw2.splitlines():
#             s = line.strip()
#             if not s or s.startswith("#"):
#                 continue

#             # If a line starts with '[' it's not xyz; treat as bary-ish
#             if s.startswith("["):
#                 return "bary_json"

#             parts = re.split(r"[,\s]+", s)

#             if len(parts) >= 3:
#                 try:
#                     t0 = float(parts[0])
#                     float(parts[1])
#                     float(parts[2])

#                     # tri u v on one line
#                     if abs(t0 - round(t0)) < 1e-6 and len(parts) == 3:
#                         return "bary_txt"

#                     # xyz: 3 floats
#                     if len(parts) == 3:
#                         return "xyz_txt"

#                     # label + xyz
#                     if len(parts) >= 4:
#                         return "xyz_txt"

#                 except Exception:
#                     # label + xyz case
#                     if len(parts) >= 4:
#                         try:
#                             float(parts[1]); float(parts[2]); float(parts[3])
#                             return "xyz_txt"
#                         except Exception:
#                             pass
#             break

#         return "xyz_txt"

#     return "xyz_txt"


# def load_landmarks(path: str) -> Tuple[LandmarkSet, DetectedFormat]:
#     fmt = detect_format(path)
#     if fmt == "slicer_mrk_json":
#         return load_mrk_json(path), fmt
#     if fmt == "bary_json":
#         return load_bary_json(path), fmt
#     if fmt == "bary_txt":
#         return load_bary_txt(path), fmt
#     if fmt == "xml":
#         return load_landmarks_xml(path), fmt
#     if fmt == "xyz_txt":
#         return load_xyz_txt(path), fmt
#     raise ValueError(f"Unsupported format: {fmt}")


# # ---------------------------
# # Mesh conversion (optional)
# # ---------------------------

# def ensure_mesh_extension(mesh_path: str, desired_ext: str) -> str:
#     """
#     If mesh isn't in desired_ext, exports a converted copy next to it and returns that path.
#     Example: desired_ext='.obj'
#     """
#     desired_ext = desired_ext.lower()
#     cur_ext = os.path.splitext(mesh_path)[1].lower()
#     if cur_ext == desired_ext:
#         return mesh_path

#     mesh = load_mesh(mesh_path)
#     out_path = os.path.splitext(mesh_path)[0] + desired_ext
#     mesh.export(out_path)
#     return out_path


# # ---------------------------
# # Conversion orchestration
# # ---------------------------

# Target = Literal["slicer_mrk_json", "wrap3d_bary", "xyz_txt", "xml"]


# def require_mesh_if_needed(src: LandmarkSet, src_fmt: DetectedFormat, tgt: Target) -> bool:
#     # Need mesh when converting between xyz <-> bary
#     if tgt in ("bary_json", "bary_txt") and src.xyz is not None:
#         return True
#     if tgt in ("slicer_mrk_json", "xyz_txt", "xml") and src.bary is not None:
#         return True
#     return False


# def convert(landmarks: LandmarkSet, src_fmt: DetectedFormat, target: Target, mesh_path: Optional[str]) -> LandmarkSet:
#     out = LandmarkSet(labels=landmarks.labels[:] if landmarks.labels else None)

#     # if we already have the needed representation, keep it
#     if target in ("slicer_mrk_json", "xyz_txt", "xml"):
#         if landmarks.xyz is not None:
#             out.xyz = landmarks.xyz
#             return out
#         if landmarks.bary is not None:
#             if not mesh_path:
#                 raise ValueError("Mesh required to convert barycentric -> xyz.")
#             mesh = load_mesh(mesh_path)
#             out.xyz = bary_to_xyz(landmarks.bary, mesh)
#             return out

#     if target in ("bary_json", "bary_txt"):
#         if landmarks.bary is not None:
#             out.bary = landmarks.bary
#             return out
#         if landmarks.xyz is not None:
#             if not mesh_path:
#                 raise ValueError("Mesh required to convert xyz -> barycentric.")
#             mesh = load_mesh(mesh_path)
#             out.bary = xyz_to_bary(landmarks.xyz, mesh)
#             return out

#     raise ValueError(f"Unhandled conversion path: {src_fmt} -> {target}")


# def choose_target_interactive() -> Target:
#     options = [
#         ("slicer_mrk_json", "Slicer (.mrk.json) — XYZ"),
#         ("bary_json",       "Wrap 3D — Barycentric (JSON)  [[tri,u,v], ...]"),
#         ("bary_txt",        "Wrap 3D — Barycentric (TXT)   tri u v per line"),
#         ("xyz_txt",         "XYZ (TXT) — x y z per line"),
#         ("xml",             "3-matic XML"),
#     ]

#     print("\nConvert TO which format?")
#     for i, (_, label) in enumerate(options, start=1):
#         print(f"  {i}) {label}")

#     while True:
#         s = input("Choose 1-5: ").strip()
#         if s.isdigit():
#             idx = int(s)
#             if 1 <= idx <= len(options):
#                 return options[idx - 1][0]  # internal key (Target)
#         print("Invalid choice. Try again.")


# def default_output_path(input_path: str, target: Target) -> str:
#     folder = os.path.dirname(os.path.abspath(input_path))
#     base = _strip_known_suffixes(input_path)

#     if target == "slicer_mrk_json":
#         return os.path.join(folder, base + ".mrk.json")
#     if target == "bary_json":
#         return os.path.join(folder, base + "_bary.json")
#     if target == "bary_txt":
#         return os.path.join(folder, base + "_bary.txt")
#     if target == "xyz_txt":
#         return os.path.join(folder, base + "_xyz.txt")
#     if target == "xml":
#         return os.path.join(folder, base + ".xml")
#     return os.path.join(folder, base + "_out")


# def save_output(path: str, converted: LandmarkSet, target: Target) -> None:
#     if target == "slicer_mrk_json":
#         if converted.xyz is None:
#             raise ValueError("No xyz to save.")
#         save_mrk_json(path, converted.xyz, converted.labels)
#         return
#     if target == "bary_json":
#         if converted.bary is None:
#             raise ValueError("No bary to save.")
#         save_bary_json(path, converted.bary)
#         return
#     if target == "bary_txt":
#         if converted.bary is None:
#             raise ValueError("No bary to save.")
#         save_bary_txt(path, converted.bary)
#         return
#     if target == "xyz_txt":
#         if converted.xyz is None:
#             raise ValueError("No xyz to save.")
#         save_xyz_txt(path, converted.xyz, converted.labels)
#         return
#     if target == "xml":
#         if converted.xyz is None:
#             raise ValueError("No xyz to save.")
#         save_landmarks_xml(path, converted.xyz, converted.labels)
#         return
#     raise ValueError(f"Unknown target: {target}")


# # ---------------------------
# # Main
# # ---------------------------

# def main():
#     parser = argparse.ArgumentParser(description="Drag/drop landmark converter (Slicer / barycentric / XML / XYZ).")
#     parser.add_argument("input", help="Landmark file (drag/drop onto .bat or run directly).")
#     parser.add_argument("--to", dest="to", default=None,
#                         choices=["slicer_mrk_json", "bary_json", "bary_txt", "xyz_txt", "xml"],
#                         help="Target format. If omitted, asks interactively.")
#     parser.add_argument("--mesh", default=None, help="Optional mesh path (otherwise auto-find by basename).")
#     parser.add_argument("--force-mesh-obj", action="store_true",
#                         help="If set and a mesh is needed, ensure the mesh is exported as .obj too.")
#     args = parser.parse_args()

#     in_path = os.path.abspath(args.input)
#     if not os.path.exists(in_path):
#         raise FileNotFoundError(in_path)

#     landmarks, src_fmt = load_landmarks(in_path)
#     print(f"Loaded: {os.path.basename(in_path)}  (detected: {DISPLAY_NAME.get(src_fmt, src_fmt)})")

#     target: Target = args.to if args.to else choose_target_interactive()  # type: ignore

#     mesh_path = args.mesh
#     if mesh_path is None:
#         mesh_path = find_mesh_for_landmarks(in_path)

#     # Only require mesh for xyz<->bary conversion
#     need_mesh = require_mesh_if_needed(landmarks, src_fmt, target)
#     if need_mesh:
#         if not mesh_path:
#             raise FileNotFoundError(
#                 "A mesh is required for this conversion, but none was found.\n"
#                 "Put a mesh with the same basename in the same folder (e.g. case.obj / case.ply / case.stl),\n"
#                 "or run with --mesh path/to/mesh."
#             )
#         mesh_path = os.path.abspath(mesh_path)
#         print(f"Using mesh: {os.path.basename(mesh_path)}")
#         if args.force_mesh_obj:
#             obj_path = ensure_mesh_extension(mesh_path, ".obj")
#             if obj_path != mesh_path:
#                 print(f"Exported mesh copy as OBJ: {os.path.basename(obj_path)}")
#             mesh_path = obj_path

#     converted = convert(landmarks, src_fmt, target, mesh_path)

#     out_path = default_output_path(in_path, target)
#     # avoid overwriting input when "convert to same format"
#     if os.path.abspath(out_path) == os.path.abspath(in_path):
#         out_path = os.path.splitext(out_path)[0] + "_converted" + os.path.splitext(out_path)[1]

#     save_output(out_path, converted, target)
#     print(f"Saved: {out_path}")


# if __name__ == "__main__":
#     main()


import os
import re
import json
import glob
import argparse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Tuple, Literal

import numpy as np
import trimesh


# ---------------------------
# Data model
# ---------------------------

@dataclass
class LandmarkSet:
    # If xyz is available: Nx3 float
    xyz: Optional[np.ndarray] = None

    # If barycentric is available: list of (tri_index, u, v) where w = 1-u-v
    bary: Optional[List[Tuple[int, float, float]]] = None

    # Optional labels (if found in XML, etc.)
    labels: Optional[List[str]] = None


# ---------------------------
# Utilities
# ---------------------------

def _strip_known_suffixes(filename: str) -> str:
    """
    For Slicer: 'case.mrk.json' -> 'case'
    For Wrap 3D bary outputs like 'case_wrap3d_bary.txt' -> 'case'
    """
    base = os.path.basename(filename)
    low = base.lower()

    if low.endswith(".mrk.json"):
        return base[:-len(".mrk.json")]

    # Common output suffixes we may generate
    for suf in ["_wrap3d_bary.txt", "_wrap3d.txt", "_bary.txt", "_xyz.txt", ".xml", ".txt", ".csv"]:
        if low.endswith(suf):
            return base[:-len(suf)]

    return os.path.splitext(base)[0]


def find_mesh_for_landmarks(landmark_path: str) -> Optional[str]:
    """
    Finds a mesh in the same folder with the same base name.
    Checks common mesh extensions.
    """
    folder = os.path.dirname(os.path.abspath(landmark_path))
    base = _strip_known_suffixes(landmark_path)

    exts = [".obj", ".ply", ".stl", ".off", ".glb", ".gltf"]
    candidates = []
    for ext in exts:
        p = os.path.join(folder, base + ext)
        if os.path.exists(p):
            candidates.append(p)

    # If not exact match, try glob for base.*
    if not candidates:
        for p in glob.glob(os.path.join(folder, base + ".*")):
            if os.path.splitext(p)[1].lower() in exts:
                candidates.append(p)

    return candidates[0] if candidates else None


def load_mesh(mesh_path: str) -> trimesh.Trimesh:
    mesh = trimesh.load(mesh_path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        mesh = mesh.dump(concatenate=True)
    if mesh.is_empty or mesh.vertices.size == 0 or mesh.faces.size == 0:
        raise ValueError(f"Mesh loaded but appears empty/invalid: {mesh_path}")
    return mesh


# ---------------------------
# Slicer .mrk.json (XYZ)
# ---------------------------

def load_mrk_json(path: str) -> LandmarkSet:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cps = data["markups"][0]["controlPoints"]
    pts = np.array([cp["position"] for cp in cps], dtype=float)
    labels = [cp.get("label", "") for cp in cps]
    return LandmarkSet(xyz=pts, labels=labels)


def save_mrk_json(path: str, xyz: np.ndarray, labels: Optional[List[str]] = None) -> None:
    """
    Writes a Slicer Markups Fiducial .mrk.json (simple)
    """
    if labels is None or len(labels) != len(xyz):
        labels = [f"L{i+1}" for i in range(len(xyz))]

    control_points = []
    for i, p in enumerate(xyz):
        control_points.append({
            "id": str(i + 1),
            "label": labels[i],
            "description": "",
            "associatedNodeID": "",
            "position": [float(p[0]), float(p[1]), float(p[2])],
            "orientation": [1.0, 0.0, 0.0,
                            0.0, 1.0, 0.0,
                            0.0, 0.0, 1.0],
            "selected": True,
            "locked": False,
            "visibility": True,
            "positionStatus": "defined"
        })

    out = {
        "@schema": "https://raw.githubusercontent.com/Slicer/Slicer/master/Modules/Loadable/Markups/Resources/Schema/markups-schema-v1.0.0.json",
        "markups": [{
            "type": "Fiducial",
            "coordinateSystem": "LPS",
            "locked": False,
            "labelFormat": "%N-%d",
            "controlPoints": control_points,
            "measurements": [],
            "display": {
                "visibility": True,
                "opacity": 1.0,
                "color": [0.4, 1.0, 0.0],
                "selectedColor": [1.0, 0.5, 0.5],
                "propertiesLabelVisibility": False,
                "pointLabelsVisibility": True,
                "textScale": 3.0,
                "glyphType": "Sphere3D",
                "glyphScale": 1.0,
                "glyphSize": 5.0
            }
        }]
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


# ---------------------------
# Wrap 3D barycentric (.txt containing JSON list)
# ---------------------------

def load_wrap3d_bary_txt(path: str) -> LandmarkSet:
    """
    Wrap 3D barycentric is ONLY supported as .txt with JSON-list content:
      [[tri,u,v],[tri,u,v],...]
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    raw2 = raw.lstrip("\ufeff \t\r\n")
    data = json.loads(raw2)
    bary = [(int(t), float(u), float(v)) for (t, u, v) in data]
    return LandmarkSet(bary=bary)


def save_wrap3d_bary_txt(path: str, bary: List[Tuple[int, float, float]]) -> None:
    """
    Writes JSON-list content to a .txt file:
      [[tri,u,v],[tri,u,v],...]
    """
    data = [[int(t), float(u), float(v)] for (t, u, v) in bary]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))  # compact


# ---------------------------
# Barycentric math
# ---------------------------

def compute_barycentric_for_point(point: np.ndarray, mesh: trimesh.Trimesh) -> Tuple[int, float, float]:
    """
    Return (triangle_index, u, v) where u and v are the first two
    barycentric weights. The third = 1 - u - v.
    """
    closest, distance, tri_id = mesh.nearest.on_surface([point])
    tri_id = int(tri_id[0])

    tri = mesh.triangles[tri_id]  # (3,3)
    a, b, c = tri

    v0 = b - a
    v1 = c - a
    v2 = point - a

    d00 = float(np.dot(v0, v0))
    d01 = float(np.dot(v0, v1))
    d11 = float(np.dot(v1, v1))
    d20 = float(np.dot(v2, v0))
    d21 = float(np.dot(v2, v1))

    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-18:
        return tri_id, 1.0, 0.0

    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w

    return tri_id, float(u), float(v)


def xyz_to_bary(xyz: np.ndarray, mesh: trimesh.Trimesh) -> List[Tuple[int, float, float]]:
    out: List[Tuple[int, float, float]] = []
    for p in xyz:
        tri, u, v = compute_barycentric_for_point(p, mesh)
        out.append((tri, u, v))
    return out


def bary_to_xyz(bary: List[Tuple[int, float, float]], mesh: trimesh.Trimesh) -> np.ndarray:
    pts = np.zeros((len(bary), 3), dtype=float)
    tris = mesh.triangles  # (F,3,3)

    for i, (tri_id, u, v) in enumerate(bary):
        tri = tris[int(tri_id)]
        a, b, c = tri
        w = 1.0 - u - v
        pts[i] = u * a + v * b + w * c
    return pts


# ---------------------------
# XYZ text (simple)
# ---------------------------

def load_xyz_txt(path: str) -> LandmarkSet:
    pts = []
    labels = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            # allow: "label x y z" or "x y z"
            parts = re.split(r"[,\s]+", s)
            if len(parts) == 3:
                x, y, z = map(float, parts)
                pts.append([x, y, z])
                labels.append("")
            elif len(parts) >= 4:
                lbl = parts[0]
                x, y, z = map(float, parts[1:4])
                pts.append([x, y, z])
                labels.append(lbl)
    if not pts:
        raise ValueError("No XYZ rows found in txt.")
    return LandmarkSet(xyz=np.array(pts, dtype=float), labels=labels)


def save_xyz_txt(path: str, xyz: np.ndarray, labels: Optional[List[str]] = None) -> None:
    with open(path, "w", encoding="utf-8") as f:
        if labels is not None and len(labels) == len(xyz):
            for lbl, p in zip(labels, xyz):
                if lbl:
                    f.write(f"{lbl} {p[0]:.10f} {p[1]:.10f} {p[2]:.10f}\n")
                else:
                    f.write(f"{p[0]:.10f} {p[1]:.10f} {p[2]:.10f}\n")
        else:
            for p in xyz:
                f.write(f"{p[0]:.10f} {p[1]:.10f} {p[2]:.10f}\n")


# ---------------------------
# XML (3-matic + fallback)
# ---------------------------

def load_landmarks_xml(path: str) -> LandmarkSet:
    """
    Supports 3-matic style:
        <Entities xmlns:mat="urn:materialise">
          <Point>
            <Name>Point-001</Name>
            <Coordinate>x y z</Coordinate>
          </Point>
        </Entities>
    (also works if tags are namespaced like <mat:Point>)

    Plus best-effort fallback patterns.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    def local(tag: str) -> str:
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        if ":" in tag:
            tag = tag.split(":", 1)[1]
        return tag

    pts = []
    labels = []

    # Explicit 3-matic parse
    point_elems = [e for e in root.iter() if local(e.tag).lower() == "point"]

    for p in point_elems:
        name = None
        coord_text = None
        for child in list(p):
            t = local(child.tag).lower()
            if t == "name":
                name = (child.text or "").strip()
            elif t == "coordinate":
                coord_text = (child.text or "").strip()

        if coord_text:
            parts = re.split(r"[,\s]+", coord_text.strip())
            if len(parts) >= 3:
                try:
                    x, y, z = map(float, parts[:3])
                    pts.append([x, y, z])
                    labels.append(name or "")
                except Exception:
                    pass

    if pts:
        return LandmarkSet(xyz=np.array(pts, dtype=float), labels=labels)

    # Fallback
    candidates = []
    for tag in ["landmark", "Landmark", "point", "Point", "fiducial", "Fiducial"]:
        candidates.extend(root.findall(f".//{tag}"))

    def _try_attrs(elem):
        keys = {k.lower(): v for k, v in elem.attrib.items()}
        if all(k in keys for k in ["x", "y", "z"]):
            x, y, z = float(keys["x"]), float(keys["y"]), float(keys["z"])
            lbl = keys.get("name") or keys.get("label") or keys.get("id") or ""
            return (x, y, z, lbl)
        return None

    def _try_children(elem):
        kids = {local(c.tag).lower(): (c.text or "").strip() for c in list(elem)}
        if all(k in kids for k in ["x", "y", "z"]):
            x, y, z = float(kids["x"]), float(kids["y"]), float(kids["z"])
            lbl = kids.get("name") or kids.get("label") or kids.get("id") or ""
            return (x, y, z, lbl)
        if "coordinate" in kids:
            parts = re.split(r"[,\s]+", kids["coordinate"])
            if len(parts) >= 3:
                x, y, z = map(float, parts[:3])
                lbl = kids.get("name") or kids.get("label") or kids.get("id") or ""
                return (x, y, z, lbl)
        return None

    def _try_text(elem):
        text = (elem.text or "").strip()
        if not text:
            return None
        parts = re.split(r"[,\s]+", text)
        if len(parts) >= 3:
            x, y, z = map(float, parts[:3])
            return (x, y, z, "")
        return None

    used = set()
    for elem in candidates:
        if elem in used:
            continue
        used.add(elem)
        got = _try_attrs(elem) or _try_children(elem) or _try_text(elem)
        if got:
            x, y, z, lbl = got
            pts.append([x, y, z])
            labels.append(lbl)

    if not pts:
        raise ValueError("XML parsed but no landmarks found (unsupported schema).")

    return LandmarkSet(xyz=np.array(pts, dtype=float), labels=labels)


def save_landmarks_xml(path: str, xyz: np.ndarray, labels: Optional[List[str]] = None) -> None:
    if labels is None or len(labels) != len(xyz):
        labels = [f"Point-{i+1:03d}" for i in range(len(xyz))]

    root = ET.Element("Entities", {"xmlns:mat": "urn:materialise"})
    for lbl, p in zip(labels, xyz):
        pt = ET.SubElement(root, "Point")
        nm = ET.SubElement(pt, "Name")
        nm.text = lbl
        co = ET.SubElement(pt, "Coordinate")
        co.text = f"{float(p[0])} {float(p[1])} {float(p[2])}"

    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


# ---------------------------
# Format detection
# ---------------------------

DetectedFormat = Literal["slicer_mrk_json", "wrap3d_bary_txt", "xyz_txt", "xml"]
Target = Literal["slicer_mrk_json", "wrap3d_bary_txt", "xyz_txt", "xml"]

DISPLAY_NAME = {
    "slicer_mrk_json": "Slicer (.mrk.json) — XYZ",
    "wrap3d_bary_txt": "Wrap 3D — Barycentric (.txt) [[tri,u,v], ...]",
    "xyz_txt": "XYZ (TXT)",
    "xml": "3-matic XML",
}


def detect_format(path: str) -> DetectedFormat:
    low = path.lower()

    if low.endswith(".mrk.json"):
        return "slicer_mrk_json"
    if low.endswith(".xml"):
        return "xml"

    # We are intentionally NOT supporting generic .json landmark inputs here.
    if low.endswith(".json"):
        raise ValueError(
            "Unsupported .json landmark file (only Slicer .mrk.json is supported).\n"
            "If this is Wrap 3D barycentric, save it as .txt containing [[tri,u,v], ...]."
        )

    if low.endswith(".txt") or low.endswith(".csv"):
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        raw2 = raw.lstrip("\ufeff \t\r\n")

        # Wrap3D barycentric txt: JSON list
        if raw2.startswith("["):
            try:
                data = json.loads(raw2)
                if (
                    isinstance(data, list) and data and
                    isinstance(data[0], (list, tuple)) and len(data[0]) >= 3
                ):
                    return "wrap3d_bary_txt"
            except Exception:
                pass

        # Otherwise treat as XYZ text
        return "xyz_txt"

    return "xyz_txt"


def load_landmarks(path: str) -> Tuple[LandmarkSet, DetectedFormat]:
    fmt = detect_format(path)
    if fmt == "slicer_mrk_json":
        return load_mrk_json(path), fmt
    if fmt == "wrap3d_bary_txt":
        return load_wrap3d_bary_txt(path), fmt
    if fmt == "xml":
        return load_landmarks_xml(path), fmt
    if fmt == "xyz_txt":
        return load_xyz_txt(path), fmt
    raise ValueError(f"Unsupported format: {fmt}")


# ---------------------------
# Mesh conversion (optional)
# ---------------------------

def ensure_mesh_extension(mesh_path: str, desired_ext: str) -> str:
    desired_ext = desired_ext.lower()
    cur_ext = os.path.splitext(mesh_path)[1].lower()
    if cur_ext == desired_ext:
        return mesh_path

    mesh = load_mesh(mesh_path)
    out_path = os.path.splitext(mesh_path)[0] + desired_ext
    mesh.export(out_path)
    return out_path


# ---------------------------
# Conversion orchestration
# ---------------------------

def require_mesh_if_needed(src: LandmarkSet, src_fmt: DetectedFormat, tgt: Target) -> bool:
    # Need mesh when converting between xyz <-> bary
    if tgt == "wrap3d_bary_txt" and src.xyz is not None:
        return True
    if tgt in ("slicer_mrk_json", "xyz_txt", "xml") and src.bary is not None:
        return True
    return False


def convert(landmarks: LandmarkSet, src_fmt: DetectedFormat, target: Target, mesh_path: Optional[str]) -> LandmarkSet:
    out = LandmarkSet(labels=landmarks.labels[:] if landmarks.labels else None)

    # Targets that need XYZ
    if target in ("slicer_mrk_json", "xyz_txt", "xml"):
        if landmarks.xyz is not None:
            out.xyz = landmarks.xyz
            return out
        if landmarks.bary is not None:
            if not mesh_path:
                raise ValueError("Mesh required to convert barycentric -> xyz.")
            mesh = load_mesh(mesh_path)
            out.xyz = bary_to_xyz(landmarks.bary, mesh)
            return out

    # Wrap3D target needs bary
    if target == "wrap3d_bary_txt":
        if landmarks.bary is not None:
            out.bary = landmarks.bary
            return out
        if landmarks.xyz is not None:
            if not mesh_path:
                raise ValueError("Mesh required to convert xyz -> barycentric.")
            mesh = load_mesh(mesh_path)
            out.bary = xyz_to_bary(landmarks.xyz, mesh)
            return out

    raise ValueError(f"Unhandled conversion path: {src_fmt} -> {target}")


def choose_target_interactive() -> Target:
    options = [
        ("wrap3d_bary_txt", "Wrap 3D — Barycentric (.txt) [[tri,u,v], ...]"),
        ("slicer_mrk_json", "Slicer (.mrk.json) — XYZ"),
        ("xyz_txt", "XYZ (TXT) — x y z per line"),
        ("xml", "3-matic XML"),
    ]

    print("\nConvert TO which format?")
    for i, (_, label) in enumerate(options, start=1):
        print(f"  {i}) {label}")

    while True:
        s = input(f"Choose 1-{len(options)}: ").strip()
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        print("Invalid choice. Try again.")


def default_output_path(input_path: str, target: Target) -> str:
    folder = os.path.dirname(os.path.abspath(input_path))
    base = _strip_known_suffixes(input_path)

    if target == "slicer_mrk_json":
        return os.path.join(folder, base + ".mrk.json")
    if target == "wrap3d_bary_txt":
        return os.path.join(folder, base + "_wrap3d_bary.txt")
    if target == "xyz_txt":
        return os.path.join(folder, base + "_xyz.txt")
    if target == "xml":
        return os.path.join(folder, base + ".xml")
    return os.path.join(folder, base + "_out")


def save_output(path: str, converted: LandmarkSet, target: Target) -> None:
    if target == "slicer_mrk_json":
        if converted.xyz is None:
            raise ValueError("No xyz to save.")
        save_mrk_json(path, converted.xyz, converted.labels)
        return

    if target == "wrap3d_bary_txt":
        if converted.bary is None:
            raise ValueError("No bary to save.")
        save_wrap3d_bary_txt(path, converted.bary)
        return

    if target == "xyz_txt":
        if converted.xyz is None:
            raise ValueError("No xyz to save.")
        save_xyz_txt(path, converted.xyz, converted.labels)
        return

    if target == "xml":
        if converted.xyz is None:
            raise ValueError("No xyz to save.")
        save_landmarks_xml(path, converted.xyz, converted.labels)
        return

    raise ValueError(f"Unknown target: {target}")


# ---------------------------
# Main
# ---------------------------

def main():
    parser = argparse.ArgumentParser(description="Drag/drop landmark converter (Slicer / Wrap 3D bary / 3-matic XML / XYZ).")
    parser.add_argument("input", help="Landmark file (drag/drop onto the .exe or run directly).")
    parser.add_argument("--to", dest="to", default=None,
                        choices=["wrap3d_bary_txt", "slicer_mrk_json", "xyz_txt", "xml"],
                        help="Target format. If omitted, asks interactively.")
    parser.add_argument("--mesh", default=None, help="Optional mesh path (otherwise auto-find by basename).")
    parser.add_argument("--force-mesh-obj", action="store_true",
                        help="If set and a mesh is needed, ensure the mesh is exported as .obj too.")
    args = parser.parse_args()

    in_path = os.path.abspath(args.input)
    if not os.path.exists(in_path):
        raise FileNotFoundError(in_path)

    landmarks, src_fmt = load_landmarks(in_path)
    print(f"Loaded: {os.path.basename(in_path)}  (detected: {DISPLAY_NAME.get(src_fmt, src_fmt)})")

    target: Target = args.to if args.to else choose_target_interactive()  # type: ignore
    print(f"Target: {DISPLAY_NAME.get(target, target)} ({target})")

    mesh_path = args.mesh
    if mesh_path is None:
        mesh_path = find_mesh_for_landmarks(in_path)

    # Only require mesh for xyz<->bary conversion
    need_mesh = require_mesh_if_needed(landmarks, src_fmt, target)
    if need_mesh:
        if not mesh_path:
            raise FileNotFoundError(
                "A mesh is required for this conversion, but none was found.\n"
                "Put a mesh with the same basename in the same folder (e.g. case.obj / case.ply / case.stl),\n"
                "or run with --mesh path/to/mesh."
            )
        mesh_path = os.path.abspath(mesh_path)
        print(f"Using mesh: {os.path.basename(mesh_path)}")
        if args.force_mesh_obj:
            obj_path = ensure_mesh_extension(mesh_path, ".obj")
            if obj_path != mesh_path:
                print(f"Exported mesh copy as OBJ: {os.path.basename(obj_path)}")
            mesh_path = obj_path

    converted = convert(landmarks, src_fmt, target, mesh_path)

    out_path = default_output_path(in_path, target)
    # avoid overwriting input when "convert to same format"
    if os.path.abspath(out_path) == os.path.abspath(in_path):
        out_path = os.path.splitext(out_path)[0] + "_converted" + os.path.splitext(out_path)[1]

    save_output(out_path, converted, target)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
