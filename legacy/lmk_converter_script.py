import os
import json
import glob
import ast
import numpy as np
import trimesh

def batch_convert_barycentric_to_slicer():
    # 1. Dynamically resolve path depending on WSL/Linux vs Windows environment
    if os.name == 'posix':  # WSL or Linux
        target_dir = "/mnt/c/klay/Templates 20250630"
    else:  # Native Windows
        target_dir = r"C:\klay\Templates 20250630"
    
    if not os.path.exists(target_dir):
        print(f"❌ Target directory does not exist: {target_dir}")
        return
        
    txt_files = glob.glob(os.path.join(target_dir, "*.txt"))
    
    if not txt_files:
        print(f"❌ No .txt files found in: {target_dir}")
        return

    print(f"🚀 Found {len(txt_files)} text files. Starting processing via Trimesh...\n")
    
    for txt_path in txt_files:
        base_path, _ = os.path.splitext(txt_path)
        stl_path = base_path + ".stl"
        output_json_path = base_path + ".mrk.json"
        
        file_name = os.path.basename(base_path)
        
        if not os.path.exists(stl_path):
            print(f"⚠️ Skipping: No matching STL found for '{file_name}.txt'")
            continue
            
        print(f"🔄 Processing: {file_name}")
        
        try:
            # 2. Load the STL mesh
            mesh = trimesh.load(stl_path)
            
            # 3. Safely read and parse the bracketed nested array structure
            with open(txt_path, 'r') as f:
                raw_content = f.read().strip()
            
            # Use abstract syntax tree parsing to load Python list of lists formatting cleanly
            landmarks_data = ast.literal_eval(raw_content)
            
            control_points = []
            
            # 4. Map the coordinates explicitly using the provided Face IDs
            for idx, item in enumerate(landmarks_data):
                face_id = int(item[0])
                w1 = float(item[1])
                w2 = float(item[2])
                w3 = 1.0 - w1 - w2  # Compute the missing 3rd barycentric weight
                
                weights = np.array([w1, w2, w3])
                
                # Check bounding boundaries of the mesh face index array
                if face_id >= len(mesh.faces):
                    print(f"   ❌ Error: Face ID {face_id} is out of bounds for STL (Max Face ID: {len(mesh.faces)-1}).")
                    continue
                
                # Extract the 3D positions of the face vertices
                face_vertex_indices = mesh.faces[face_id]
                triangle_vertices = mesh.vertices[face_vertex_indices]
                
                # Math formula conversion matrix multiplication
                cartesian_pos = np.dot(weights, triangle_vertices)
                
                # Pull values via index slicing safely into base floats
                pos_list = [float(cartesian_pos[0]), float(cartesian_pos[1]), float(cartesian_pos[2])]
                
                control_points.append({
                    "id": str(idx + 1),
                    "label": f"L-{idx+1}",
                    "description": f"Mapped to Face {face_id}",
                    "position": pos_list,
                    "orientation": [-1.0, -0.0, -0.0, -0.0, -1.0, -0.0, 0.0, 0.0, 1.0],
                    "selected": True,
                    "locked": False,
                    "visibility": True
                })
                
            # 5. Pack everything inside the 3D Slicer schema format
            slicer_markup = {
                "@schema": "https://githubusercontent.com",
                "markups": [
                    {
                        "type": "Fiducial",
                        "coordinateSystem": "LPS",  
                        "coordinateUnits": "mm",
                        "controlPoints": control_points
                    }
                ]
            }
            
            with open(output_json_path, "w") as json_file:
                json.dump(slicer_markup, json_file, indent=4)
                
            print(f"   ✅ Saved markup to: {os.path.basename(output_json_path)}")
            
        except Exception as e:
            print(f"   ❌ Error handling file pair '{file_name}': {str(e)}")

    print("\n🎉 Batch conversion completed successfully.")

if __name__ == "__main__":
    batch_convert_barycentric_to_slicer()
