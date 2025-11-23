import json
import trimesh
import numpy as np

# Paths
obj_path = "/mnt/data/Soft Tissue - CT.obj"
bary_path = "/mnt/data/Soft Tissue - CT.txt"
out_path = "/mnt/data/Soft Tissue - CT_reconstructed.mrk.json"

# Load mesh
mesh = trimesh.load(obj_path, force='mesh')
if not isinstance(mesh, trimesh.Trimesh):
    mesh = mesh.dump(concatenate=True)

# Load barycentric data
with open(bary_path, "r") as f:
    bary_data = json.loads(f.read())

def bary_to_xyz(entry, mesh):
    tri_id, u, v = entry
    tri = mesh.triangles[int(tri_id)]
    a, b, c = tri
    w = 1.0 - u - v
    return a * w + b * u + c * v

xyz_points = np.array([bary_to_xyz(entry, mesh) for entry in bary_data])

# Build mrk.json
markups = {
    "markups": [{
        "type": "Fiducial",
        "coordinateSystem": "LPS",
        "controlPoints": []
    }]
}

for i, p in enumerate(xyz_points):
    markups["markups"][0]["controlPoints"].append({
        "id": f"F{i}",
        "label": f"F-{i}",
        "position": [float(p[0]), float(p[1]), float(p[2])]
    })

with open(out_path, "w") as f:
    json.dump(markups, f, indent=2)

out_path
