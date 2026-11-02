import os
import re
import sys
import json
import glob
import shutil
import argparse
import datetime
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
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

    # LJSON groups / connectivity, carried through so .ljson round-trips losslessly
    ljson_groups: Optional[List[dict]] = None
    ljson_connectivity: Optional[List[List[int]]] = None
    extra: dict = field(default_factory=dict)


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
    for suf in ["_wrap3d_bary.txt", "_wrap3d.txt", "_bary.txt", "_xyz.txt",
                "_converted.ljson", ".ljson", ".xml", ".txt", ".csv"]:
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

    # If not exact match, try glob for base.* (glob.escape: names may contain [ ] etc.)
    if not candidates:
        for p in glob.glob(os.path.join(glob.escape(folder), glob.escape(base) + ".*")):
            if os.path.splitext(p)[1].lower() in exts:
                candidates.append(p)

    return candidates[0] if candidates else None


def load_mesh(mesh_path: str) -> trimesh.Trimesh:
    # process=False keeps the file's vertex/face order untouched, so barycentric
    # face indices stay valid against the same mesh in Wrap 3D / other tools.
    mesh = trimesh.load(mesh_path, force="mesh", process=False)
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

    pts = []
    labels = []

    for cp in cps:
        pts.append(cp["position"])
        labels.append(cp.get("label", ""))

    # Natural sort: skull-1, skull-2, ..., skull-10
    def extract_number(label: str):
        m = re.search(r'\d+', label)
        return int(m.group()) if m else float("inf")

    combined = list(zip(labels, pts))
    combined.sort(key=lambda x: extract_number(x[0]))

    labels_sorted = [c[0] for c in combined]
    pts_sorted = np.array([c[1] for c in combined], dtype=float)

    return LandmarkSet(xyz=pts_sorted, labels=labels_sorted)

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
# Menpo LJSON (XYZ + named groups + connectivity)
# ---------------------------
#
#   {"version": 2,
#    "labels": [{"label": "nose", "mask": [10, 11, ...]}, ...],
#    "landmarks": {"points": [[x, y, z], ...], "connectivity": [[0, 1], ...]}}
#
# Per-point labels are generated as "<group>-<global index, 1-based>", e.g. "nose-11".
# The leading group name lets save_ljson rebuild the groups from any XYZ format that
# keeps labels (Slicer / XYZ txt / XML), and the number keeps load_mrk_json's natural
# sort in the original LJSON order.

LJSON_LABEL_RE = re.compile(r"^(?P<group>.+)-(?P<idx>\d+)$")


def load_ljson(path: str) -> LandmarkSet:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if int(data.get("version", 2)) != 2:
        raise ValueError(f"Only LJSON version 2 is supported (got {data.get('version')}).")

    lm = data["landmarks"]
    raw_pts = lm["points"]
    if any(p is None or any(c is None for c in p) for p in raw_pts):
        raise ValueError("LJSON contains null (missing) points; fill or remove them first.")
    pts = np.array(raw_pts, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(f"Expected 3D LJSON points (Nx3), got shape {pts.shape}.")

    groups = data.get("labels") or []
    labels = [f"L-{i+1}" for i in range(len(pts))]
    for g in groups:
        for i in g["mask"]:
            labels[int(i)] = f"{g['label']}-{int(i)+1}"

    return LandmarkSet(
        xyz=pts,
        labels=labels,
        ljson_groups=[{"label": g["label"], "mask": [int(i) for i in g["mask"]]} for g in groups],
        ljson_connectivity=[[int(a), int(b)] for a, b in lm.get("connectivity", [])],
    )


def _groups_from_labels(labels: Optional[List[str]], n: int) -> Optional[List[dict]]:
    """Rebuild LJSON groups from '<group>-<n>' labels (as written by load_ljson). None if not that style."""
    if not labels or len(labels) != n:
        return None
    groups: dict = {}
    for i, lbl in enumerate(labels):
        m = LJSON_LABEL_RE.match(lbl or "")
        if not m:
            return None
        groups.setdefault(m.group("group"), []).append(i)
    return [{"label": k, "mask": v} for k, v in groups.items()]


def save_ljson(path: str, lms: LandmarkSet, template: Optional[LandmarkSet] = None) -> None:
    """
    Group/connectivity source, in priority order:
      1) --template LJSON (must have the same number of points)
      2) groups carried on the landmark set (LJSON input)
      3) '<group>-<n>' style labels (e.g. a Slicer file that came from an LJSON)
      4) a single 'all' group, no connectivity
    """
    xyz = lms.xyz
    n = len(xyz)
    groups, conn = lms.ljson_groups, lms.ljson_connectivity

    if template is not None:
        if len(template.xyz) != n:
            raise ValueError(f"Template LJSON has {len(template.xyz)} points but landmarks have {n}.")
        groups, conn = template.ljson_groups, template.ljson_connectivity
    if not groups:
        groups = _groups_from_labels(lms.labels, n) or [{"label": "all", "mask": list(range(n))}]

    out = {
        "labels": groups,
        "landmarks": {
            "connectivity": conn or [],
            "points": [[float(p[0]), float(p[1]), float(p[2])] for p in xyz],
        },
        "version": 2,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=4)


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
    raw2 = raw.lstrip("﻿ \t\r\n")
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
# [tri, u, v] with w = 1-u-v; A, B, C are the triangle's vertices in file order.
#   standard: point = u*A + v*B + w*C   (landmark_convert.py / lmk_converter_script.py)
#   legacy:   point = w*A + u*B + v*C   (legacy/barycentric_to_3dslicer_markup.py)

BaryConvention = Literal["standard", "legacy"]
BARY_CONVENTIONS = {
    "standard": "standard — u·A + v·B + (1−u−v)·C",
    "legacy": "legacy — (1−u−v)·A + u·B + v·C",
}


def xyz_to_bary(xyz: np.ndarray, mesh: trimesh.Trimesh, warn_dist: Optional[float] = None,
                convention: BaryConvention = "standard") -> List[Tuple[int, float, float]]:
    """
    Project each point onto the closest mesh triangle and return (triangle_index, u, v).
    Points further than warn_dist from the surface are reported (they get snapped).
    """
    xyz = np.asarray(xyz, dtype=float)
    closest, distance, tri_ids = mesh.nearest.on_surface(xyz)

    if warn_dist is not None:
        for i in np.where(distance > warn_dist)[0]:
            print(f"   ⚠️ Landmark {i+1} is {distance[i]:.4g} from the mesh surface (snapped onto it).")

    # Barycentrics of the projected point, so bary -> xyz reproduces it exactly
    w = trimesh.triangles.points_to_barycentric(mesh.triangles[tri_ids], closest)  # weights on A, B, C
    uv = w[:, :2] if convention == "standard" else w[:, 1:]
    return [(int(t), float(u), float(v)) for t, (u, v) in zip(tri_ids, uv)]


def bary_to_xyz(bary: List[Tuple[int, float, float]], mesh: trimesh.Trimesh,
                convention: BaryConvention = "standard") -> np.ndarray:
    tri_ids = np.array([int(t) for t, _, _ in bary])
    if len(tri_ids) and tri_ids.max() >= len(mesh.faces):
        raise ValueError(
            f"Face ID {tri_ids.max()} is out of bounds for mesh (max face ID {len(mesh.faces)-1}). "
            "Is this the right mesh?"
        )
    uv = np.array([(u, v) for _, u, v in bary], dtype=float).reshape(-1, 2)
    rest = 1.0 - uv.sum(axis=1)
    if convention == "standard":
        weights = np.column_stack([uv, rest])  # (N,3) weights on A, B, C
    else:
        weights = np.column_stack([rest, uv])
    return np.einsum("ij,ijk->ik", weights, mesh.triangles[tri_ids])


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

DetectedFormat = Literal["slicer_mrk_json", "wrap3d_bary_txt", "xyz_txt", "xml", "ljson"]
Target = Literal["slicer_mrk_json", "wrap3d_bary_txt", "xyz_txt", "xml", "ljson"]

XYZ_TARGETS = ("slicer_mrk_json", "xyz_txt", "xml", "ljson")

DISPLAY_NAME = {
    "slicer_mrk_json": "Slicer (.mrk.json) — XYZ",
    "wrap3d_bary_txt": "Wrap 3D — Barycentric (.txt) [[tri,u,v], ...]",
    "xyz_txt": "XYZ (TXT)",
    "xml": "3-matic XML",
    "ljson": "Menpo LJSON (.ljson) — XYZ + groups",
}


def detect_format(path: str) -> DetectedFormat:
    low = path.lower()

    if low.endswith(".mrk.json"):
        return "slicer_mrk_json"
    if low.endswith(".ljson"):
        return "ljson"
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
        raw2 = raw.lstrip("﻿ \t\r\n")

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
    if fmt == "ljson":
        return load_ljson(path), fmt
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
    if tgt in XYZ_TARGETS and src.bary is not None:
        return True
    return False


def convert(landmarks: LandmarkSet, src_fmt: DetectedFormat, target: Target, mesh_path: Optional[str],
            warn_dist: Optional[float] = None, convention: BaryConvention = "standard") -> LandmarkSet:
    out = LandmarkSet(
        labels=landmarks.labels[:] if landmarks.labels else None,
        ljson_groups=landmarks.ljson_groups,
        ljson_connectivity=landmarks.ljson_connectivity,
    )

    # Targets that need XYZ
    if target in XYZ_TARGETS:
        if landmarks.xyz is not None:
            out.xyz = landmarks.xyz
            return out
        if landmarks.bary is not None:
            if not mesh_path:
                raise ValueError("Mesh required to convert barycentric -> xyz.")
            mesh = load_mesh(mesh_path)
            out.xyz = bary_to_xyz(landmarks.bary, mesh, convention)
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
            out.bary = xyz_to_bary(landmarks.xyz, mesh, warn_dist=warn_dist, convention=convention)
            # Round-trip check: how far the stored bary lands from the input point
            err = np.linalg.norm(bary_to_xyz(out.bary, mesh, convention) - landmarks.xyz, axis=1)
            print(f"   Round-trip xyz -> bary -> xyz error: max {err.max():.3g}, mean {err.mean():.3g}")
            return out

    raise ValueError(f"Unhandled conversion path: {src_fmt} -> {target}")


def choose_target_interactive() -> Target:
    options = [
        ("wrap3d_bary_txt", "Wrap 3D — Barycentric (.txt) [[tri,u,v], ...]"),
        ("slicer_mrk_json", "Slicer (.mrk.json) — XYZ"),
        ("xyz_txt", "XYZ (TXT) — x y z per line"),
        ("xml", "3-matic XML"),
        ("ljson", "Menpo LJSON (.ljson) — XYZ + groups"),
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


def default_output_path(input_path: str, target: Target, out_dir: Optional[str] = None) -> str:
    folder = out_dir or os.path.dirname(os.path.abspath(input_path))
    base = _strip_known_suffixes(input_path)

    if target == "slicer_mrk_json":
        return os.path.join(folder, base + ".mrk.json")
    if target == "wrap3d_bary_txt":
        return os.path.join(folder, base + "_wrap3d_bary.txt")
    if target == "xyz_txt":
        return os.path.join(folder, base + "_xyz.txt")
    if target == "xml":
        return os.path.join(folder, base + ".xml")
    if target == "ljson":
        return os.path.join(folder, base + ".ljson")
    return os.path.join(folder, base + "_out")


def save_output(path: str, converted: LandmarkSet, target: Target,
                ljson_template: Optional[LandmarkSet] = None) -> None:
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

    if target == "ljson":
        if converted.xyz is None:
            raise ValueError("No xyz to save.")
        save_ljson(path, converted, ljson_template)
        return

    raise ValueError(f"Unknown target: {target}")


# ---------------------------
# Provenance
# ---------------------------

def quote_arg(a: str) -> str:
    return f'"{a}"' if any(ch in a for ch in " *?[") else a


def record_provenance(out_dirs: List[str], cmd: Optional[str] = None) -> None:
    """Append date + exact command to run_command.txt and drop a copy of this script in each output folder."""
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    frozen = getattr(sys, "frozen", False)
    if cmd is None:
        cmd = " ".join(quote_arg(a) for a in sys.argv)
    for d in sorted(set(out_dirs)):
        with open(os.path.join(d, "run_command.txt"), "a", encoding="utf-8") as f:
            f.write(f"{stamp}  {'[app] ' if frozen else ''}{cmd}\n")
        if not frozen:
            dst = os.path.join(d, os.path.basename(__file__))
            if os.path.abspath(dst) != os.path.abspath(__file__):
                shutil.copy2(__file__, dst)


# ---------------------------
# Main
# ---------------------------

LANDMARK_EXTS = (".mrk.json", ".ljson", ".xml", ".txt", ".csv")
TARGETS = ["wrap3d_bary_txt", "slicer_mrk_json", "xyz_txt", "xml", "ljson"]


def expand_inputs(inputs: List[str], pattern: str) -> List[str]:
    files = []
    for p in inputs:
        p = os.path.abspath(p)
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(glob.escape(p), pattern))))
        elif os.path.exists(p):
            files.append(p)
        else:
            raise FileNotFoundError(p)
    return [f for f in files
            if f.lower().endswith(LANDMARK_EXTS) and os.path.basename(f) != "run_command.txt"]


def convert_one(in_path: str, target: Target, mesh: Optional[str] = None, out_dir: Optional[str] = None,
                ljson_template: Optional[LandmarkSet] = None, warn_dist: Optional[float] = None,
                convention: BaryConvention = "standard", force_mesh_obj: bool = False) -> str:
    landmarks, src_fmt = load_landmarks(in_path)
    print(f"Loaded: {os.path.basename(in_path)}  (detected: {DISPLAY_NAME.get(src_fmt, src_fmt)})")

    mesh_path = mesh
    if mesh_path is None:
        mesh_path = find_mesh_for_landmarks(in_path)

    # Only require mesh for xyz<->bary conversion
    need_mesh = require_mesh_if_needed(landmarks, src_fmt, target)
    if need_mesh:
        if not mesh_path:
            raise FileNotFoundError(
                "A mesh is required for this conversion, but none was found.\n"
                "Put a mesh with the same basename in the same folder (e.g. case.obj / case.ply / case.stl),\n"
                "or pick one with --mesh path/to/mesh."
            )
        mesh_path = os.path.abspath(mesh_path)
        print(f"Using mesh: {os.path.basename(mesh_path)}  (barycentric convention: {convention})")
        if force_mesh_obj:
            obj_path = ensure_mesh_extension(mesh_path, ".obj")
            if obj_path != mesh_path:
                print(f"Exported mesh copy as OBJ: {os.path.basename(obj_path)}")
            mesh_path = obj_path

    converted = convert(landmarks, src_fmt, target, mesh_path, warn_dist=warn_dist, convention=convention)

    out_path = default_output_path(in_path, target, out_dir)
    # avoid overwriting input when "convert to same format"
    if os.path.abspath(out_path) == os.path.abspath(in_path):
        root, ext = os.path.splitext(out_path)
        if out_path.lower().endswith(".mrk.json"):
            root, ext = out_path[:-len(".mrk.json")], ".mrk.json"
        out_path = root + "_converted" + ext

    save_output(out_path, converted, target, ljson_template)
    print(f"Saved: {out_path}")
    return out_path


def convert_many(files: List[str], target: Target, mesh: Optional[str] = None, out_dir: Optional[str] = None,
                 template: Optional[str] = None, warn_dist: Optional[float] = None,
                 convention: BaryConvention = "standard", force_mesh_obj: bool = False,
                 provenance_cmd: Optional[str] = None, provenance: bool = True) -> Tuple[List[str], List[str]]:
    """Convert every file; returns (outputs, failed inputs). Shared by the CLI and the GUI."""
    if out_dir:
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)
    print(f"Target: {DISPLAY_NAME.get(target, target)} ({target})")
    ljson_template = load_ljson(template) if template else None

    out_paths, failed = [], []
    for i, in_path in enumerate(files, start=1):
        if len(files) > 1:
            print(f"\n[{i}/{len(files)}]")
        try:
            out_paths.append(convert_one(in_path, target, mesh, out_dir, ljson_template,
                                         warn_dist, convention, force_mesh_obj))
        except Exception as e:
            print(f"   ❌ {os.path.basename(in_path)}: {e}")
            failed.append(in_path)

    if out_paths and provenance:
        record_provenance([os.path.dirname(p) for p in out_paths], provenance_cmd)

    print(f"\nDone: {len(out_paths)} converted, {len(failed)} failed.")
    return out_paths, failed


def main():
    parser = argparse.ArgumentParser(
        description="Drag/drop landmark converter (Slicer / Wrap 3D bary / 3-matic XML / XYZ / Menpo LJSON).")
    parser.add_argument("inputs", nargs="+",
                        help="Landmark file(s) or folder(s) (drag/drop onto the .exe or run directly).")
    parser.add_argument("--to", dest="to", default=None, choices=TARGETS,
                        help="Target format. If omitted, asks interactively.")
    parser.add_argument("--mesh", default=None,
                        help="Optional mesh path (otherwise auto-find by basename). Applies to every input.")
    parser.add_argument("--template", default=None,
                        help="LJSON whose groups/connectivity are copied when writing .ljson "
                             "(e.g. when converting Wrap 3D bary back to LJSON).")
    parser.add_argument("--bary-convention", default="standard", choices=list(BARY_CONVENTIONS),
                        help="How [tri,u,v] maps onto the triangle: "
                             + "; ".join(BARY_CONVENTIONS.values()) + " (default: standard).")
    parser.add_argument("--pattern", default="*.ljson",
                        help="Glob used when an input is a folder (default: *.ljson).")
    parser.add_argument("--out-dir", default=None,
                        help="Write outputs here instead of next to each input.")
    parser.add_argument("--warn-dist", type=float, default=None,
                        help="Warn when a landmark is further than this from the mesh surface (xyz -> bary).")
    parser.add_argument("--force-mesh-obj", action="store_true",
                        help="If set and a mesh is needed, ensure the mesh is exported as .obj too.")
    parser.add_argument("--no-provenance", action="store_true",
                        help="Don't write run_command.txt / a copy of this script next to the outputs.")
    args = parser.parse_args()

    files = expand_inputs(args.inputs, args.pattern)
    if not files:
        raise FileNotFoundError("No landmark files found in the given inputs.")

    target: Target = args.to if args.to else choose_target_interactive()  # type: ignore

    _, failed = convert_many(files, target, args.mesh, args.out_dir, args.template, args.warn_dist,
                             args.bary_convention, args.force_mesh_obj, provenance=not args.no_provenance)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
