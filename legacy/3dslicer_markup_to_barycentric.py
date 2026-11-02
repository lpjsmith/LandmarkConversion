import json
import os
import glob
import trimesh
import numpy as np


def load_mrk_json(path):
    """Load a Slicer .mrk.json and return Nx3 array of landmark xyz."""
    with open(path, 'r') as f:
        data = json.load(f)

    control_points = data['markups'][0]['controlPoints']
    pts = np.array([cp['position'] for cp in control_points], dtype=float)
    return pts


def compute_barycentric(point, mesh):
    """Return (triangle_index, u, v) for the closest triangle."""
    closest, distance, tri_id = mesh.nearest.on_surface([point])
    tri_id = int(tri_id[0])

    tri = mesh.triangles[tri_id]
    a, b, c = tri

    v0 = b - a
    v1 = c - a
    v2 = point - a

    d00 = np.dot(v0, v0)
    d01 = np.dot(v0, v1)
    d11 = np.dot(v1, v1)
    d20 = np.dot(v2, v0)
    d21 = np.dot(v2, v1)

    denom = d00 * d11 - d01 * d01

    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1 - v - w

    return tri_id, float(u), float(v)


def main():
    # Use the directory where THIS script is located
    cwd = os.path.dirname(os.path.abspath(__file__))

    obj_path = os.path.join(cwd, "2.obj")

    if not os.path.exists(obj_path):
        raise FileNotFoundError(f"ERROR: Could not find 2.obj in: {cwd}")

    print(f"Loaded mesh: {obj_path}")

    mesh = trimesh.load(obj_path, force='mesh')
    if not isinstance(mesh, trimesh.Trimesh):
        mesh = mesh.dump(concatenate=True)

    mrk_files = glob.glob(os.path.join(cwd, "*.mrk.json"))

    if not mrk_files:
        print("No .mrk.json files found in:", cwd)
        return

    for mrk_path in mrk_files:
        print(f"Processing {os.path.basename(mrk_path)}...")

        pts = load_mrk_json(mrk_path)
        output = []

        for p in pts:
            tri, u, v = compute_barycentric(p, mesh)
            output.append([tri, u, v])

        out_path = mrk_path.replace(".mrk.json", "_bary.txt")

        with open(out_path, "w") as f:
            f.write("[")
            for i, (tri, u, v) in enumerate(output):
                if i > 0:
                    f.write(",")    # add comma between entries
                f.write(f"[{tri},{u},{v}]")
            f.write("]")

        print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
