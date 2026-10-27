"""
Blender 5.2 Procedural High-Precision Modeling: Red-Gray-White Works GT Race Car.
Exports public/models/race_car.glb and renders blender/qa_renders/qa_race_car.png.
"""

import os
import sys
import math
import bpy
import bmesh
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbr_utils as pu


def build_lofted_body(mat_livery, parent):
    """Build sleek multi-station aerodynamic GT/LMP monocoque with planar top-down UV."""
    # Longitudinal stations: (y, half_width, z_floor, z_skirt, z_shoulder, z_deck, center_dip)
    # +Y is Front Nose, -Y is Rear Diffuser
    stations = [
        (-0.83, 0.35, 0.11, 0.16, 0.25, 0.26, 0.00),
        (-0.72, 0.39, 0.08, 0.14, 0.28, 0.28, -0.01),
        (-0.54, 0.42, 0.07, 0.15, 0.31, 0.29, -0.02),  # Rear wheel arch peak
        (-0.34, 0.40, 0.06, 0.13, 0.29, 0.28, 0.01),
        (-0.10, 0.41, 0.06, 0.13, 0.28, 0.29, 0.02),   # Sidepod widest
        (0.16,  0.39, 0.06, 0.13, 0.27, 0.28, 0.01),
        (0.36,  0.40, 0.06, 0.14, 0.27, 0.25, -0.01),
        (0.52,  0.41, 0.07, 0.15, 0.26, 0.23, -0.02),  # Front wheel arch peak
        (0.68,  0.38, 0.06, 0.12, 0.21, 0.18, -0.01),
        (0.80,  0.33, 0.06, 0.10, 0.15, 0.13, 0.00),
        (0.85,  0.24, 0.065, 0.085, 0.11, 0.10, 0.00), # Nose tip
    ]

    bm = bmesh.new()
    rings = []
    for (y, hw, zf, zs, zsh, zd, dip) in stations:
        # 12-vertex closed cross-section counter-clockwise in XZ plane
        pts_xz = [
            (0.0, zf),                           # 0 bottom center
            (hw * 0.78, zf),                     # 1 bottom right
            (hw * 0.96, zs),                     # 2 lower skirt right
            (hw * 1.00, (zs + zsh) * 0.52),      # 3 outer flank right
            (hw * 0.90, zsh),                    # 4 fender crest right
            (hw * 0.48, zd),                     # 5 hood shoulder right
            (0.0, zd + dip),                     # 6 top spine center
            (-hw * 0.48, zd),                    # 7 hood shoulder left
            (-hw * 0.90, zsh),                   # 8 fender crest left
            (-hw * 1.00, (zs + zsh) * 0.52),     # 9 outer flank left
            (-hw * 0.96, zs),                    # 10 lower skirt left
            (-hw * 0.78, zf),                    # 11 bottom left
        ]
        ring = [bm.verts.new((x, y, z)) for (x, z) in pts_xz]
        rings.append(ring)

    n_prof = len(rings[0])
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for j in range(n_prof):
            jn = (j + 1) % n_prof
            bm.faces.new((r0[j], r0[jn], r1[jn], r1[j]))

    # Cap rear and front ends
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])

    # Subtle subdivision smooth via bmesh bevel on sharp longitudinal creases? Keep crisp aero lines + smooth shading
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    uv_layer = bm.loops.layers.uv.verify()
    for f in bm.faces:
        f.smooth = True
        for loop in f.loops:
            co = loop.vert.co
            u = max(0.002, min(0.998, co.x / 0.88 + 0.5))
            v = max(0.002, min(0.998, co.y / 1.72 + 0.5))
            loop[uv_layer].uv = (u, v)

    mesh = bpy.data.meshes.new("Car_Body_Shell_Mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("Car_Body_Shell", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat_livery)
    obj.parent = parent
    return obj


def build_teardrop_canopy(mat_glass, mat_trim, parent):
    """Build sleek teardrop fighter-style cockpit glass dome."""
    bm = bmesh.new()
    # Ellipsoidal dome sliced above z = 0.24
    bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=16, radius=1.0)
    for v in list(bm.verts):
        if v.co.z < -0.05:
            bm.verts.remove(v)
        else:
            # Asymmetric teardrop: steeper windshield in front (+Y), longer taper to rear (-Y)
            sy = 0.31 if v.co.y >= 0 else 0.40
            v.co.x *= 0.225
            v.co.y = v.co.y * sy + 0.02
            v.co.z = 0.265 + max(0.0, v.co.z) * 0.165

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True

    mesh = bpy.data.meshes.new("Car_Canopy_Mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("Car_Canopy", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat_glass)
    obj.parent = parent

    # Roof air scoop intake atop canopy rear
    pu.create_beveled_box(
        "Car_Roof_Scoop",
        size=(0.09, 0.22, 0.055),
        location=(0.0, -0.08, 0.425),
        bevel_width=0.012,
        material=mat_trim,
        parent=parent,
    )
    return obj


def build_aero_package(mat_carbon, mat_red, mat_livery, mat_led_front, mat_led_rear, mat_chrome, parent):
    """Build front splitter, side skirts, shark fin, GT rear wing, diffuser, exhausts, and LED lights."""
    # Front ground-effect carbon splitter
    pu.create_beveled_box(
        "Car_Front_Splitter",
        size=(0.80, 0.24, 0.024),
        location=(0.0, 0.77, 0.052),
        bevel_width=0.006,
        material=mat_carbon,
        parent=parent,
    )
    # Front red lip accent
    pu.create_beveled_box(
        "Car_Front_Lip_Red",
        size=(0.76, 0.035, 0.016),
        location=(0.0, 0.885, 0.054),
        bevel_width=0.004,
        material=mat_red,
        parent=parent,
    )
    # Side carbon aero skirts
    for sx, tag in [(-1, "L"), (1, "R")]:
        pu.create_beveled_box(
            f"Car_Side_Skirt_{tag}",
            size=(0.045, 0.72, 0.022),
            location=(sx * 0.415, 0.0, 0.055),
            bevel_width=0.005,
            material=mat_carbon,
            parent=parent,
        )
        # Sidepod intake dark louver
        pu.create_beveled_box(
            f"Car_Side_Intake_{tag}",
            size=(0.05, 0.24, 0.09),
            location=(sx * 0.375, 0.08, 0.19),
            rotation=(0.0, 0.0, sx * math.radians(8)),
            bevel_width=0.008,
            material=mat_carbon,
            parent=parent,
        )

    # Dorsal aero shark fin
    pu.create_beveled_box(
        "Car_Shark_Fin",
        size=(0.016, 0.44, 0.11),
        location=(0.0, -0.46, 0.34),
        bevel_width=0.004,
        material=mat_red,
        parent=parent,
    )

    # Swan-neck rear wing pylons
    for sx, tag in [(-1, "L"), (1, "R")]:
        pu.create_beveled_box(
            f"Car_Wing_Pylon_{tag}",
            size=(0.018, 0.14, 0.18),
            location=(sx * 0.16, -0.71, 0.36),
            rotation=(math.radians(-16), 0.0, 0.0),
            bevel_width=0.004,
            material=mat_carbon,
            parent=parent,
        )
        # Sculpted crimson rear wing endplates
        pu.create_beveled_box(
            f"Car_Wing_Endplate_{tag}",
            size=(0.016, 0.24, 0.15),
            location=(sx * 0.42, -0.77, 0.43),
            bevel_width=0.005,
            material=mat_red,
            parent=parent,
        )

    # Main GT Wing Airfoil
    pu.create_beveled_box(
        "Car_Rear_Wing_Main",
        size=(0.83, 0.19, 0.022),
        location=(0.0, -0.77, 0.45),
        rotation=(math.radians(8), 0.0, 0.0),
        bevel_width=0.006,
        material=mat_carbon,
        parent=parent,
    )
    # Upper DRS flap in Sugon Red
    pu.create_beveled_box(
        "Car_Rear_Wing_Flap",
        size=(0.81, 0.075, 0.016),
        location=(0.0, -0.835, 0.478),
        rotation=(math.radians(18), 0.0, 0.0),
        bevel_width=0.004,
        material=mat_red,
        parent=parent,
    )

    # Rear carbon diffuser + vertical strakes
    pu.create_beveled_box(
        "Car_Rear_Diffuser",
        size=(0.70, 0.14, 0.075),
        location=(0.0, -0.81, 0.085),
        bevel_width=0.008,
        material=mat_carbon,
        parent=parent,
    )
    for sx in (-0.24, -0.08, 0.08, 0.24):
        pu.create_beveled_box(
            f"Car_Diffuser_Strake_{sx:+.2f}",
            size=(0.012, 0.15, 0.085),
            location=(sx, -0.825, 0.082),
            bevel_width=0.002,
            material=mat_red if abs(sx) > 0.2 else mat_carbon,
            parent=parent,
        )

    # Twin titanium exhaust nozzles
    for sx, tag in [(-1, "L"), (1, "R")]:
        pu.create_cylinder_obj(
            f"Car_Exhaust_{tag}",
            radius=0.032,
            depth=0.09,
            vertices=24,
            location=(sx * 0.13, -0.845, 0.155),
            rotation=(math.radians(90), 0.0, 0.0),
            bevel_width=0.004,
            material=mat_chrome,
            parent=parent,
        )

    # Angled LED Matrix Headlights (+Y front)
    for sx, tag in [(-1, "L"), (1, "R")]:
        pu.create_beveled_box(
            f"Car_Headlight_{tag}",
            size=(0.15, 0.06, 0.022),
            location=(sx * 0.255, 0.755, 0.172),
            rotation=(math.radians(14), sx * math.radians(-10), sx * math.radians(-18)),
            bevel_width=0.004,
            material=mat_led_front,
            parent=parent,
        )

    # Full-width Cyber Crimson Taillight Bar (-Y rear) + FIA Rain Light
    pu.create_beveled_box(
        "Car_Taillight_Bar",
        size=(0.68, 0.025, 0.026),
        location=(0.0, -0.835, 0.235),
        bevel_width=0.005,
        material=mat_led_rear,
        parent=parent,
    )
    pu.create_beveled_box(
        "Car_Rain_Light",
        size=(0.045, 0.025, 0.045),
        location=(0.0, -0.848, 0.135),
        bevel_width=0.005,
        material=mat_led_rear,
        parent=parent,
    )


def build_wheel_assembly(name: str, location, radius: float, width: float, is_right: bool, mats, parent):
    """
    Build single joined multi-material wheel mesh centered strictly at `location`
    so rotating around local X axis in Three.js spins with zero eccentricity.
    """
    parts = []
    sx = 1.0 if is_right else -1.0

    # 1. Semi-slick rubber tire (cylinder along X axis -> rotate Y by 90 deg)
    tire = pu.create_cylinder_obj(
        f"{name}_Tire",
        radius=radius,
        depth=width,
        vertices=36,
        location=(0, 0, 0),
        rotation=(0.0, math.radians(90), 0.0),
        bevel_width=0.016,
        material=mats["rubber"],
    )
    parts.append(tire)

    # 2. Recessed dark alloy rim barrel (set slightly inward so 5 chrome spokes stand proud in 3D relief!)
    rim = pu.create_cylinder_obj(
        f"{name}_Rim",
        radius=radius * 0.72,
        depth=width * 0.76,
        vertices=32,
        location=(0, 0, 0),
        rotation=(0.0, math.radians(90), 0.0),
        bevel_width=0.005,
        material=mats["rim"],
    )
    parts.append(rim)

    # 3. Glowing/anodized crimson brake caliper & rotor ring behind spokes
    ring = pu.create_cylinder_obj(
        f"{name}_RedRing",
        radius=radius * 0.54,
        depth=0.012,
        vertices=28,
        location=(sx * (width * 0.39), 0, 0),
        rotation=(0.0, math.radians(90), 0.0),
        bevel_width=0.002,
        material=mats["red"],
    )
    parts.append(ring)

    # 4. 5-twin-spoke machined alloy star blades proud on outer wheel face
    for k in range(5):
        ang = k * (2.0 * math.pi / 5.0)
        for off in (-0.09, 0.09):
            a2 = ang + off
            cy = math.cos(a2) * (radius * 0.36)
            cz = math.sin(a2) * (radius * 0.36)
            spoke = pu.create_beveled_box(
                f"{name}_Spoke_{k}_{off:+.2f}",
                size=(0.022, 0.016, radius * 0.66),
                location=(sx * (width * 0.44), cy, cz),
                rotation=(a2 - math.pi * 0.5, 0.0, 0.0),
                bevel_width=0.003,
                material=mats["chrome"],
            )
            parts.append(spoke)

    # 5. Center-lock anodized red hub nut
    hub = pu.create_cylinder_obj(
        f"{name}_Hub",
        radius=radius * 0.18,
        depth=0.026,
        vertices=18,
        location=(sx * (width * 0.465), 0, 0),
        rotation=(0.0, math.radians(90), 0.0),
        bevel_width=0.004,
        material=mats["red"],
    )
    parts.append(hub)

    # Join all wheel subparts into a single clean mesh with origin at (0,0,0), then move to `location`
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = tire
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()

    wheel_obj = bpy.context.active_object
    wheel_obj.name = name
    wheel_obj.location = Vector(location)
    wheel_obj.parent = parent
    return wheel_obj


def main():
    pu.clear_scene()

    # Create automotive PBR materials
    mat_livery = pu.make_pbr_material(
        "Car_Livery_PBR",
        coat_weight=1.0,
        coat_roughness=0.04,
        albedo_tex="car_livery_albedo.png",
        metallic_tex="car_livery_metallic.jpg",
        roughness_tex="car_livery_roughness.jpg",
        emissive_tex="car_livery_emissive.png",
        emission_strength=2.2,
    )
    mat_glass = pu.make_pbr_material(
        "Car_Canopy_Glass",
        base_color=(0.03, 0.05, 0.09, 1.0),
        metallic=0.82,
        roughness=0.05,
        coat_weight=1.0,
        coat_roughness=0.02,
    )
    mat_carbon = pu.make_pbr_material(
        "Car_Carbon_Gray",
        base_color=(0.09, 0.10, 0.12, 1.0),
        metallic=0.45,
        roughness=0.32,
        coat_weight=0.5,
    )
    mat_red = pu.make_pbr_material(
        "Car_Sugon_Red",
        base_color=(0.82, 0.01, 0.05, 1.0),
        metallic=0.25,
        roughness=0.18,
        coat_weight=1.0,
        coat_roughness=0.04,
    )
    mat_rubber = pu.make_pbr_material(
        "Car_Tire_Rubber",
        base_color=(0.045, 0.048, 0.055, 1.0),
        metallic=0.0,
        roughness=0.76,
    )
    mat_rim = pu.make_pbr_material(
        "Car_Alloy_Rim",
        base_color=(0.24, 0.27, 0.31, 1.0),
        metallic=0.92,
        roughness=0.22,
    )
    mat_chrome = pu.make_pbr_material(
        "Car_Titanium_Chrome",
        base_color=(0.82, 0.85, 0.90, 1.0),
        metallic=0.98,
        roughness=0.12,
    )
    mat_led_front = pu.make_pbr_material(
        "Car_LED_Headlight",
        base_color=(0.85, 0.98, 1.0, 1.0),
        emission_color=(0.45, 0.92, 1.0, 1.0),
        emission_strength=8.0,
    )
    mat_led_rear = pu.make_pbr_material(
        "Car_LED_Taillight",
        base_color=(1.0, 0.05, 0.10, 1.0),
        emission_color=(1.0, 0.04, 0.10, 1.0),
        emission_strength=9.0,
    )

    car_root = bpy.data.objects.new("Car_Root", None)
    bpy.context.collection.objects.link(car_root)

    chassis = bpy.data.objects.new("Car_Chassis", None)
    bpy.context.collection.objects.link(chassis)
    chassis.parent = car_root

    build_lofted_body(mat_livery, chassis)
    build_teardrop_canopy(mat_glass, mat_carbon, chassis)
    build_aero_package(mat_carbon, mat_red, mat_livery, mat_led_front, mat_led_rear, mat_chrome, chassis)

    wheel_mats = {
        "rubber": mat_rubber,
        "red": mat_red,
        "rim": mat_rim,
        "chrome": mat_chrome,
    }
    build_wheel_assembly("Wheel_FL", (-0.375, 0.52, 0.17), radius=0.17, width=0.145, is_right=False, mats=wheel_mats, parent=car_root)
    build_wheel_assembly("Wheel_FR", (0.375, 0.52, 0.17), radius=0.17, width=0.145, is_right=True, mats=wheel_mats, parent=car_root)
    build_wheel_assembly("Wheel_RL", (-0.385, -0.52, 0.178), radius=0.178, width=0.165, is_right=False, mats=wheel_mats, parent=car_root)
    build_wheel_assembly("Wheel_RR", (0.385, -0.52, 0.178), radius=0.178, width=0.165, is_right=True, mats=wheel_mats, parent=car_root)

    # Render studio QA 3/4 view BEFORE exporting GLB (QA objects are stripped automatically by export_glb)
    floor = pu.create_beveled_box(
        "QA_Studio_Floor",
        size=(4.5, 4.5, 0.04),
        location=(0, 0, -0.02),
        bevel_width=0.0,
        material=pu.make_pbr_material("QA_Floor_Mat", base_color=(0.12, 0.14, 0.18, 1.0), roughness=0.35, metallic=0.2),
    )
    pu.setup_qa_lighting_and_render(
        cam_location=(1.65, 1.85, 0.95),
        cam_target=(0.0, 0.05, 0.22),
        out_filename="qa_race_car_front.png",
        res=(1280, 720),
        lens=42.0,
    )
    pu.setup_qa_lighting_and_render(
        cam_location=(-1.65, -1.85, 0.98),
        cam_target=(0.0, -0.05, 0.24),
        out_filename="qa_race_car_rear.png",
        res=(1280, 720),
        lens=42.0,
    )

    # Note: export_apply=False on wheel parent transforms? Let's keep wheel local origins preserved!
    for obj in list(bpy.data.objects):
        if obj.name.startswith("QA_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    out_glb = os.path.join(pu.MODEL_DIR, "race_car.glb")
    bpy.ops.export_scene.gltf(
        filepath=out_glb,
        export_format="GLB",
        export_yup=True,
        export_apply=False,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
    )
    print(f"Exported race_car.glb ({os.path.getsize(out_glb) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
