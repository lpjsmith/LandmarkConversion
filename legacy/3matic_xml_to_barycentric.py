import xml.etree.ElementTree as ET
import trimesh
import numpy as np

# Load files
xml_file = 'Pre-operative mandible.xml'  # XML landmarks file
mesh_file = 'Mandible.stl'  # Mesh file
output_txt = 'landmarks_barycentric.txt'

# Parse XML
tree = ET.parse(xml_file)
root = tree.getroot()

coordinates = []

# Extract XYZ coordinates
for point in root.findall('.//Point'):
    coord_text = point.find('Coordinate').text.strip()
    xyz = list(map(float, coord_text.split()))
    coordinates.append(xyz)

coordinates = np.array(coordinates)

# Load mesh
mesh = trimesh.load(mesh_file)

# Find closest points on mesh
closest_points, distances, triangle_id = trimesh.proximity.closest_point(mesh, coordinates)

# Get triangles
triangles = mesh.triangles[triangle_id]

# Compute barycentric coordinates
barycentric_list = []
for i in range(len(coordinates)):
    tri = triangles[i]
    p = coordinates[i]

    v0 = tri[1] - tri[0]
    v1 = tri[2] - tri[0]
    v2 = p - tri[0]

    d00 = np.dot(v0, v0)
    d01 = np.dot(v0, v1)
    d11 = np.dot(v1, v1)
    d20 = np.dot(v2, v0)
    d21 = np.dot(v2, v1)

    denom = d00 * d11 - d01 * d01
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    # Only save first vertex index, and v, w (u can be calculated as 1 - v - w)
    barycentric_list.append([int(mesh.faces[triangle_id[i]][0]), float(v), float(w)])

# Save to TXT
with open(output_txt, 'w') as f:
    for bary in barycentric_list:
        f.write(f'[{bary[0]}, {bary[1]}, {bary[2]}]\n')

print(f"Extracted {len(barycentric_list)} barycentric coordinates and saved to {output_txt}")
