"""
Blender 5.2 Procedural High-Precision Modeling: Start/Finish '曙光云 (Sugon Cloud)' Logo Gantry.
Exports public/models/start_gantry.glb and renders blender/qa_renders/qa_start_gantry.png.
"""

import os
import sys
import math
import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbr_utils as pu


def create_banner_panel(name: str, width: float, height: float, location, facing_neg_y: bool, mat_banner, parent):
    """Create planar UV-mapped [0,1]x[0,1] billboard mesh facing -Y (front) or +Y (back)."""
    bm = bmesh.new()
    hw, hh = width * 0.5, height * 0.5
    if facing_neg_y:
        # Viewer stands at -Y looking toward +Y: left is -X, right is +X, normal is (0, -1, 0)
        v0 = bm.verts.new((-hw, 0.0, -hh))
        v1 = bm.verts.new((hw, 0.0, -hh))
        v2 = bm.verts.new((hw, 0.0, hh))
        v3 = bm.verts.new((-hw, 0.0, hh))
    else:
        # Viewer stands at +Y looking toward -Y: left is +X, right is -X, normal is (0, +1, 0)
        v0 = bm.verts.new((hw, 0.0, -hh))
        v1 = bm.verts.new((-hw, 0.0, -hh))
        v2 = bm.verts.new((-hw, 0.0, hh))
        v3 = bm.verts.new((hw, 0.0, hh))

    f = bm.faces.new((v0, v1, v2, v3))
    uv_layer = bm.loops.layers.uv.verify()
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for loop, uv in zip(f.loops, uvs):
        loop[uv_layer].uv = uv

    mesh = bpy.data.meshes.new(name + "_Mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = Vector(location)
    obj.data.materials.append(mat_banner)
    obj.parent = parent
    return obj


def build_3d_sugon_cloud_crest(mats, parent):
    """Build 3D extruded Sugon Cloud (Security Shield + Dawn Red Chevron + Volumetric Cloud) crown monument."""
    crest_root = bpy.data.objects.new("Gantry_Crown_Logo", None)
    bpy.context.collection.objects.link(crest_root)
    crest_root.location = (0.0, 0.0, 3.82)
    crest_root.parent = parent

    # 1. Extruded hexagonal security shield body in XZ plane
    bm = bmesh.new()
    s = 0.46
    pts_xz = [
        (0.0, 1.00 * s),
        (0.88 * s, 0.58 * s),
        (0.78 * s, -0.22 * s),
        (0.0, -1.00 * s),
        (-0.78 * s, -0.22 * s),
        (-0.88 * s, 0.58 * s),
    ]
    front_v = [bm.verts.new((x, -0.07, z)) for (x, z) in pts_xz]
    back_v = [bm.verts.new((x, 0.07, z)) for (x, z) in pts_xz]
    bm.faces.new(list(reversed(front_v)))
    bm.faces.new(back_v)
    n = len(pts_xz)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((front_v[i], front_v[j], back_v[j], back_v[i]))
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.015, segments=2, affect="EDGES")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh_sh = bpy.data.meshes.new("Shield_Core_Mesh")
    bm.to_mesh(mesh_sh)
    bm.free()

    sh_obj = bpy.data.objects.new("Crown_Shield_Core", mesh_sh)
    bpy.context.collection.objects.link(sh_obj)
    sh_obj.data.materials.append(mats["shield_blue"])
    sh_obj.parent = crest_root

    # 2. Glowing Cyan outer shield frame bars
    for i in range(n):
        p0 = Vector((pts_xz[i][0] * 1.04, 0.0, pts_xz[i][1] * 1.04))
        p1 = Vector((pts_xz[(i + 1) % n][0] * 1.04, 0.0, pts_xz[(i + 1) % n][1] * 1.04))
        mid = (p0 + p1) * 0.5
        seg = p1 - p0
        ang_y = math.atan2(seg.z, seg.x)
        pu.create_beveled_box(
            f"Crown_Shield_Rim_{i}",
            size=(seg.length + 0.02, 0.16, 0.032),
            location=mid,
            rotation=(0.0, -ang_y, 0.0),
            bevel_width=0.006,
            material=mats["neon_cyan"],
            parent=crest_root,
        )

    # 3. Sugon Red Dawn Chevron bars inside upper shield (both front & back protruding)
    for sx, tag in [(-1, "L"), (1, "R")]:
        pu.create_beveled_box(
            f"Crown_Dawn_Chevron_{tag}",
            size=(0.30, 0.18, 0.065),
            location=(sx * 0.13, 0.0, 0.18),
            rotation=(0.0, sx * math.radians(26), 0.0),
            bevel_width=0.008,
            material=mats["neon_red"],
            parent=crest_root,
        )

    # 4. 3D Volumetric Cloud spheres protruding on front and back of shield
    cloud_spheres = [
        (-0.14, -0.09, 0.095),
        (0.01, -0.02, 0.125),
        (0.15, -0.08, 0.088),
    ]
    for idx, (cx, cz, rad) in enumerate(cloud_spheres):
        bm_c = bmesh.new()
        bmesh.ops.create_uvsphere(bm_c, u_segments=20, v_segments=14, radius=rad)
        bmesh.ops.scale(bm_c, vec=(1.05, 1.15, 0.95), verts=bm_c.verts)
        for f in bm_c.faces:
            f.smooth = True
        m_c = bpy.data.meshes.new(f"Crown_Cloud_{idx}_Mesh")
        bm_c.to_mesh(m_c)
        bm_c.free()
        c_obj = bpy.data.objects.new(f"Crown_Cloud_{idx}", m_c)
        bpy.context.collection.objects.link(c_obj)
        c_obj.location = (cx, 0.0, cz)
        c_obj.data.materials.append(mats["cloud_white"])
        c_obj.parent = crest_root

    pu.create_beveled_box(
        "Crown_Cloud_Base",
        size=(0.34, 0.21, 0.09),
        location=(0.01, 0.0, -0.12),
        bevel_width=0.02,
        material=mats["cloud_white"],
        parent=crest_root,
    )


def main():
    pu.clear_scene()

    mats = {
        "metal": pu.make_pbr_material(
            "Gantry_Brushed_Aluminum",
            albedo_tex="metal_brushed_albedo.jpg",
            normal_tex="metal_brushed_normal.png",
            roughness_tex="metal_brushed_roughness.jpg",
            metallic=0.92,
            uv_scale=(2.0, 2.0),
        ),
        "carbon": pu.make_pbr_material(
            "Gantry_Dark_Carbon",
            base_color=(0.07, 0.09, 0.13, 1.0),
            metallic=0.65,
            roughness=0.28,
        ),
        "banner": pu.make_pbr_material(
            "Gantry_Sugon_Banner",
            albedo_tex="gantry_banner_albedo.png",
            emissive_tex="gantry_banner_emissive.png",
            emission_strength=2.6,
            roughness=0.24,
            metallic=0.15,
        ),
        "neon_cyan": pu.make_pbr_material(
            "Gantry_Neon_Cyan",
            base_color=(0.0, 0.92, 1.0, 1.0),
            emission_color=(0.0, 0.88, 1.0, 1.0),
            emission_strength=6.5,
        ),
        "neon_red": pu.make_pbr_material(
            "Gantry_Neon_Red",
            base_color=(0.95, 0.02, 0.08, 1.0),
            emission_color=(1.0, 0.04, 0.10, 1.0),
            emission_strength=6.5,
        ),
        "shield_blue": pu.make_pbr_material(
            "Gantry_Shield_Blue",
            base_color=(0.04, 0.14, 0.30, 1.0),
            metallic=0.75,
            roughness=0.18,
            coat_weight=1.0,
        ),
        "cloud_white": pu.make_pbr_material(
            "Gantry_Cloud_Emissive",
            base_color=(0.96, 0.99, 1.0, 1.0),
            emission_color=(0.75, 0.94, 1.0, 1.0),
            emission_strength=3.2,
            roughness=0.15,
        ),
        "holo": pu.make_pbr_material(
            "Gantry_Holo_Placeholder",
            base_color=(0.0, 0.85, 1.0, 0.28),
            emission_color=(0.0, 0.75, 1.0, 1.0),
            emission_strength=2.0,
            alpha=0.28,
        ),
        "light_off": pu.make_pbr_material(
            "Gantry_StartLight_Mat",
            base_color=(0.9, 0.05, 0.08, 1.0),
            emission_color=(0.95, 0.05, 0.08, 1.0),
            emission_strength=4.5,
        ),
    }

    root = bpy.data.objects.new("Start_Gantry_Root", None)
    bpy.context.collection.objects.link(root)

    # Left & Right Twin Truss Towers at X = ±1.86 (clear of ±1.42 track walls)
    for sx, tag in [(-1, "L"), (1, "R")]:
        cx = sx * 1.86
        # Heavy anchored base pad
        pu.create_beveled_box(
            f"Gantry_Base_{tag}",
            size=(0.46, 0.72, 0.10),
            location=(cx, 0.0, 0.05),
            bevel_width=0.018,
            material=mats["carbon"],
            parent=root,
        )
        # Front & Rear brushed-aluminum main columns
        for sy, fb in [(-0.20, "F"), (0.20, "B")]:
            pu.create_beveled_box(
                f"Gantry_Col_{tag}_{fb}",
                size=(0.11, 0.11, 3.22),
                location=(cx, sy, 1.66),
                bevel_width=0.014,
                material=mats["metal"],
                parent=root,
            )
        # Horizontal & diagonal cross-braces between front/back columns
        for hz in (0.55, 1.15, 1.75, 2.35, 2.95):
            pu.create_beveled_box(
                f"Gantry_Brace_{tag}_{hz:.2f}",
                size=(0.06, 0.36, 0.05),
                location=(cx, 0.0, hz),
                bevel_width=0.006,
                material=mats["carbon"],
                parent=root,
            )
        # Inner vertical glowing neon accent blade facing the track
        pu.create_beveled_box(
            f"Gantry_Tower_Neon_{tag}",
            size=(0.028, 0.05, 2.25),
            location=(cx - sx * 0.075, -0.20, 1.22),
            bevel_width=0.004,
            material=mats["neon_cyan"] if sx < 0 else mats["neon_red"],
            parent=root,
        )

    # Main Overhead Billboard Housing spanning X in [-2.08, +2.08], Z in [2.38, 3.36]
    pu.create_beveled_box(
        "Gantry_Header_Housing",
        size=(4.16, 0.56, 0.98),
        location=(0.0, 0.0, 2.87),
        bevel_width=0.025,
        material=mats["carbon"],
        parent=root,
    )
    # Brushed aluminum top & bottom structural beams
    pu.create_beveled_box(
        "Gantry_Top_Beam",
        size=(4.24, 0.62, 0.065),
        location=(0.0, 0.0, 3.38),
        bevel_width=0.012,
        material=mats["metal"],
        parent=root,
    )
    pu.create_beveled_box(
        "Gantry_Bottom_Beam",
        size=(4.20, 0.60, 0.055),
        location=(0.0, 0.0, 2.37),
        bevel_width=0.010,
        material=mats["metal"],
        parent=root,
    )

    # Front (-Y) and Back (+Y) 2K Sugon Cloud Brand Billboards
    create_banner_panel("Gantry_Banner_Front", width=3.92, height=0.88, location=(0.0, -0.285, 2.87), facing_neg_y=True, mat_banner=mats["banner"], parent=root)
    create_banner_panel("Gantry_Banner_Back", width=3.92, height=0.88, location=(0.0, 0.285, 2.87), facing_neg_y=False, mat_banner=mats["banner"], parent=root)

    # 3D Extruded Sugon Cloud Crown Crest atop the Gantry
    build_3d_sugon_cloud_crest(mats, root)

    # 5-Pod F1 Starting Countdown Lights suspended at Z = 2.16 (portal headroom below = 2.02 > 4.3x car height)
    for idx, lx in enumerate((-0.88, -0.44, 0.0, 0.44, 0.88)):
        pu.create_beveled_box(
            f"Gantry_LightPod_Housing_{idx}",
            size=(0.24, 0.14, 0.24),
            location=(lx, -0.22, 2.18),
            bevel_width=0.015,
            material=mats["carbon"],
            parent=root,
        )
        # Named lens node so Three.js can modulate color per countdown second!
        pu.create_cylinder_obj(
            f"Gantry_StartLight_{idx}",
            radius=0.078,
            depth=0.04,
            vertices=24,
            location=(lx, -0.285, 2.18),
            rotation=(math.radians(90), 0.0, 0.0),
            bevel_width=0.005,
            material=mats["light_off"].copy(),
            parent=root,
        )

    # Holographic Laser Curtain Plane (tagged for custom GLSL GantryHoloShader in Three.js)
    create_banner_panel(
        "Gantry_Holo_Curtain",
        width=3.36,
        height=0.52,
        location=(0.0, 0.0, 1.80),
        facing_neg_y=True,
        mat_banner=mats["holo"],
        parent=root,
    )

    # Render QA inspection shot
    pu.create_beveled_box(
        "QA_Road_Preview",
        size=(2.8, 5.0, 0.06),
        location=(0, 0, -0.03),
        material=pu.make_pbr_material("QA_Road", albedo_tex="track_road_albedo.png", roughness=0.5),
    )
    pu.setup_qa_lighting_and_render(
        cam_location=(1.8, -5.6, 2.2),
        cam_target=(0.0, 0.0, 2.15),
        out_filename="qa_start_gantry.png",
        res=(1280, 720),
        lens=36.0,
    )

    for obj in list(bpy.data.objects):
        if obj.name.startswith("QA_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    out_glb = os.path.join(pu.MODEL_DIR, "start_gantry.glb")
    bpy.ops.export_scene.gltf(
        filepath=out_glb,
        export_format="GLB",
        export_yup=True,
        export_apply=False,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
    )
    print(f"Exported start_gantry.glb ({os.path.getsize(out_glb) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
