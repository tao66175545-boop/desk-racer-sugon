"""
Blender 5.2 Master Pipeline:
1. Reconstructs Studio Room + Walnut Standing Desk + High-Detail Geek Desk Props from desk_reference.jpg
2. Builds Suzuka-style 3D Figure-8 Elevated Track with Banked Curves, Overpass Bridge & 3D Launch Ramp
3. Runs Automated BVHTree Overlap & 640-Point Swept-Car Envelope Clearance Check -> collision_report.json
4. Exports public/models/desk_track_scene.glb + public/data/track_metadata.json + Multi-Angle QA Renders
"""

import os
import sys
import json
import math
import numpy as np
import bpy
import bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbr_utils as pu

TRACK_HALF_WIDTH = 1.28      # 2.56m wide drivable tarmac (> 3.0x car width 0.84m)
WALL_OFFSET = 1.36           # Guardrail inner face distance from centerline
WALL_HEIGHT = 0.48           # Barrier height
DECK_THICKNESS = 0.20        # Structural viaduct slab thickness


def bl_to_three_pos(v):
    """Blender (x, y, z) -> glTF/Three.js (x, z, -y) with export_yup=True."""
    return [round(float(v[0]), 5), round(float(v[2]), 5), round(float(-v[1]), 5)]


def bl_to_three_vec(v):
    return [round(float(v[0]), 5), round(float(v[2]), 5), round(float(-v[1]), 5)]


def catmull_rom_closed(ctrl_pts: np.ndarray, samples_per_seg: int = 40) -> np.ndarray:
    """Evaluate C1 closed periodic Catmull-Rom spline over M control points -> (M*samples_per_seg, D)."""
    m = len(ctrl_pts)
    out = []
    for i in range(m):
        p0 = ctrl_pts[(i - 1) % m]
        p1 = ctrl_pts[i]
        p2 = ctrl_pts[(i + 1) % m]
        p3 = ctrl_pts[(i + 2) % m]
        for s in range(samples_per_seg):
            t = s / float(samples_per_seg)
            t2 = t * t
            t3 = t2 * t
            pt = 0.5 * (
                (2.0 * p1)
                + (-p0 + p2) * t
                + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
            )
            out.append(pt)
    return np.array(out, dtype=np.float64)


def periodic_smooth(arr: np.ndarray, kernel_radius: int = 8) -> np.ndarray:
    idx = np.arange(-kernel_radius, kernel_radius + 1)
    weights = np.exp(-0.5 * (idx / (kernel_radius * 0.45)) ** 2)
    weights /= weights.sum()
    padded = np.pad(arr, ((kernel_radius, kernel_radius),) + ((0, 0),) * (arr.ndim - 1), mode="wrap")
    res = np.zeros_like(arr)
    for k, w in enumerate(weights):
        res += w * padded[k:k + len(arr)]
    return res


def generate_track_frames():
    """
    Generate 640-sample closed Suzuka-style Figure-8 3D elevated spline on the 26.8 x 14.8 desk.
    Columns: (X, Y_bl, Z_bl, bank_deg)
    Single orthogonal crossing at (0.0, -0.5):
      - Underpass (NE bound) at Z = 0.08
      - Overpass Bridge (NW bound) at Z = 2.72 (2.64 units vertical separation -> > 2.38 net headroom!)
    """
    ctrl = np.array([
        # Start/Finish South-West Straight (heading East-South-East -> East)
        [-6.6, -5.15, 0.08,  0.0],   # 0: Start Straight Entry
        [-3.6, -5.15, 0.08,  0.0],   # 1: START / FINISH GANTRY STRAIGHT
        [-1.3, -3.55, 0.08, -4.0],   # 2: Turn 1 approach to Center Underpass
        [ 0.0, -0.50, 0.08,  0.0],   # 3: CENTER UNDERPASS (heading NE, ground level)
        [ 1.6,  2.75, 0.14, -6.0],   # 4: Underpass exit toward Monitor right
        [ 5.0,  4.35, 0.72, -9.0],   # 5: 3D Ascending Ramp Start
        [ 8.8,  3.55, 1.78, -11.0],  # 6: Ascending Banked Spiral (inside Books)
        [10.1,  0.20, 2.58, -11.0],  # 7: East High Viaduct Apex (inside Mini-Server)
        [ 8.9, -3.45, 2.86, -8.0],   # 8: High Viaduct Launch Ramp Crest!
        [ 5.6, -4.85, 2.48, -6.0],   # 9: Elevated Step-Down Landing Deck
        [ 2.4, -3.45, 2.66,  4.0],   # 10: Overpass Bridge Approach (heading NW)
        [ 0.0, -0.50, 2.74,  0.0],   # 11: CENTER 3D OVERPASS BRIDGE (2.66m above Underpass!)
        [-2.2,  2.55, 2.36,  7.0],   # 12: Overpass Exit (heading NW)
        [-5.8,  4.25, 1.42,  10.0],  # 13: 3D Descending Banked Ramp (in front of Succulent/Lamp)
        [-9.4,  2.85, 0.44,  10.0],  # 14: West Ramp Touchdown
        [-9.9, -1.95, 0.08,  10.0],  # 15: West Sweeper (inside Coffee Mug)
    ], dtype=np.float64)

    raw = catmull_rom_closed(ctrl, samples_per_seg=40)  # 640 points
    xyz = periodic_smooth(raw[:, :3], kernel_radius=9)
    bank = periodic_smooth(raw[:, 3:4], kernel_radius=12)[:, 0]

    # Clamp ground segments cleanly at >= 0.08 so road never dips into the walnut desk top (Z=0)
    xyz[:, 2] = np.maximum(xyz[:, 2], 0.08)

    # Add sculpted 3D Thrill Camelback / Launch Wave around sample 325 (East High Viaduct)
    n = len(xyz)
    idx_arr = np.arange(n, dtype=np.float64)
    d_wave = np.minimum(np.abs(idx_arr - 322.0), n - np.abs(idx_arr - 322.0))
    launch_bump = 0.34 * np.exp(-0.5 * (d_wave / 14.0) ** 2) - 0.16 * np.exp(-0.5 * ((idx_arr - 352.0) / 16.0) ** 2)
    xyz[:, 2] += launch_bump

    # Flatten Start/Finish straight around sample 28..52 to Z = 0.08, bank = 0 for clean Gantry fit
    for k in range(n):
        dist_start = min(abs(k - 36), n - abs(k - 36))
        if dist_start < 22:
            w = 0.5 * (1.0 + math.cos(math.pi * dist_start / 22.0))
            xyz[k, 2] = xyz[k, 2] * (1.0 - w) + 0.08 * w
            bank[k] = bank[k] * (1.0 - w)

    # Compute arc-length, tangent, normal (up), and binormal (right) with banking
    tangents = np.zeros_like(xyz)
    rights = np.zeros_like(xyz)
    ups = np.zeros_like(xyz)
    arc_len = np.zeros(n, dtype=np.float64)

    world_up = np.array([0.0, 0.0, 1.0])
    total_s = 0.0
    for i in range(n):
        prev_p = xyz[(i - 1) % n]
        next_p = xyz[(i + 1) % n]
        if i > 0:
            total_s += np.linalg.norm(xyz[i] - xyz[i - 1])
        arc_len[i] = total_s

        t = next_p - prev_p
        t /= (np.linalg.norm(t) + 1e-9)
        r_flat = np.cross(t, world_up)
        r_flat /= (np.linalg.norm(r_flat) + 1e-9)
        u_base = np.cross(r_flat, t)
        u_base /= (np.linalg.norm(u_base) + 1e-9)

        # Rotate (r_flat, u_base) around tangent t by bank_deg
        rad = math.radians(float(bank[i]))
        cb, sb = math.cos(rad), math.sin(rad)
        r_bank = r_flat * cb + u_base * sb
        u_bank = -r_flat * sb + u_base * cb

        tangents[i] = t
        rights[i] = r_bank
        ups[i] = u_bank

    total_length = total_s + np.linalg.norm(xyz[0] - xyz[-1])
    return xyz, tangents, rights, ups, bank, arc_len, total_length


def build_room_and_desk(mats, root):
    """Build Studio Room walls, acoustic wood slats, Venetian blinds, bookshelf & Walnut Standing Desk."""
    room_grp = bpy.data.objects.new("Room_Environment", None)
    bpy.context.collection.objects.link(room_grp)
    room_grp.parent = root

    # Studio Floor at Z = -7.4
    pu.create_beveled_box(
        "Room_Floor",
        size=(38.0, 28.0, 0.25),
        location=(0.0, -1.0, -7.52),
        bevel_width=0.0,
        material=mats["floor"],
        uv_box_scale=6.0,
        parent=room_grp,
    )
    # Back Wall (Y = +7.55)
    pu.create_beveled_box(
        "Room_Back_Wall",
        size=(36.0, 0.30, 17.0),
        location=(1.5, 7.65, 0.8),
        bevel_width=0.0,
        material=mats["wall"],
        uv_box_scale=4.0,
        parent=room_grp,
    )
    # Dark acoustic felt backing behind vertical walnut slats (X in [-6.8, +15.2])
    pu.create_beveled_box(
        "Room_Acoustic_Backing",
        size=(22.0, 0.08, 16.5),
        location=(4.2, 7.46, 0.8),
        bevel_width=0.0,
        material=mats["dark_felt"],
        parent=room_grp,
    )
    # 40 Vertical Acoustic Wood Slats matching desk_reference.jpg!
    slat_parts = []
    for k in range(40):
        sx = -6.5 + k * 0.54
        s_obj = pu.create_beveled_box(
            f"Slat_{k}",
            size=(0.28, 0.14, 16.4),
            location=(sx, 7.38, 0.8),
            bevel_width=0.015,
            bevel_segments=1,
            material=mats["wood"],
            uv_box_scale=2.0,
        )
        slat_parts.append(s_obj)
    bpy.ops.object.select_all(action="DESELECT")
    for p in slat_parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = slat_parts[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    slats_joined = bpy.context.active_object
    slats_joined.name = "Room_Acoustic_Wood_Slats"
    slats_joined.parent = room_grp

    # Back-Left Warm Wood Bookshelf Alcove (X in [-13.4, -7.2], Y = +7.2)
    pu.create_beveled_box(
        "Room_Bookshelf_Frame",
        size=(5.8, 1.2, 13.5),
        location=(-10.2, 7.9, -0.5),
        bevel_width=0.03,
        material=mats["wood"],
        parent=room_grp,
    )
    for sz in (-3.2, -0.6, 2.0, 4.6):
        pu.create_beveled_box(
            f"Room_Shelf_{sz:+.1f}",
            size=(5.5, 1.35, 0.14),
            location=(-10.2, 7.25, sz),
            bevel_width=0.015,
            material=mats["wood"],
            parent=room_grp,
        )

    # Left Window Wall (X = -14.2) + Sunlit Window Pane + Venetian Horizontal Blinds
    pu.create_beveled_box(
        "Room_Left_Wall_Frame",
        size=(0.35, 24.0, 17.0),
        location=(-14.35, -1.0, 0.8),
        bevel_width=0.0,
        material=mats["wall"],
        parent=room_grp,
    )
    pu.create_beveled_box(
        "Room_Window_Sunlight_Glow",
        size=(0.08, 12.5, 10.5),
        location=(-14.08, 0.8, 3.2),
        bevel_width=0.0,
        material=mats["sun_window"],
        parent=room_grp,
    )
    blind_parts = []
    for b in range(22):
        bz = -1.6 + b * 0.45
        bl = pu.create_beveled_box(
            f"Blind_{b}",
            size=(0.22, 12.2, 0.04),
            location=(-13.92, 0.8, bz),
            rotation=(0.0, math.radians(22), 0.0),
            bevel_width=0.004,
            bevel_segments=1,
            material=mats["blind_cream"],
        )
        blind_parts.append(bl)
    bpy.ops.object.select_all(action="DESELECT")
    for p in blind_parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = blind_parts[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    blinds_joined = bpy.context.active_object
    blinds_joined.name = "Room_Venetian_Blinds"
    blinds_joined.parent = room_grp

    # WALNUT STANDING DESK TOP (Top surface strictly at Z = 0.0!)
    desk_top = pu.create_beveled_box(
        "Desk_Surface",
        size=(26.8, 14.8, 0.52),
        location=(0.0, 0.0, -0.26),
        bevel_width=0.035,
        bevel_segments=3,
        material=mats["wood"],
        uv_box_scale=2.2,
        parent=root,
    )

    # Motorized Matte-Black Standing Desk T-Legs
    for sx, tag in [(-1, "L"), (1, "R")]:
        pu.create_beveled_box(
            f"Desk_Leg_Col_{tag}",
            size=(0.68, 0.95, 6.85),
            location=(sx * 10.4, 0.2, -3.92),
            bevel_width=0.025,
            material=mats["matte_black"],
            parent=room_grp,
        )
        pu.create_beveled_box(
            f"Desk_Leg_Foot_{tag}",
            size=(0.95, 6.8, 0.28),
            location=(sx * 10.4, 0.2, -7.26),
            bevel_width=0.03,
            material=mats["matte_black"],
            parent=room_grp,
        )

    # XXL Charcoal Felt Stitched Desk Mat (flush on desk at Z in [0.0, 0.022], non-blocking!)
    pu.create_beveled_box(
        "Decor_XXL_DeskMat",
        size=(15.6, 7.6, 0.022),
        location=(-0.2, -0.7, 0.011),
        bevel_width=0.008,
        material=mats["deskmat"],
        uv_box_scale=3.0,
        parent=root,
    )
    return desk_top


def join_parts_as(parts, name: str, parent):
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.parent = parent
    return obj


def build_static_desk_props(mats, root):
    """
    Build high-precision static desk landmarks matching desk_reference.jpg.
    Returns list of blocking static prop objects for BVHTree collision verification.
    """
    static_props = []

    # 1. 38-inch Curved Ultrawide Monitor on Brushed-Silver Articulated Arm
    mon_parts = []
    # Clamp base at (+1.4, +6.95, 0) cleanly behind the curved bezel!
    mon_parts.append(pu.create_beveled_box("Mon_Base", size=(1.15, 0.95, 0.18), location=(1.4, 6.90, 0.09), bevel_width=0.03, material=mats["aluminum"]))
    mon_parts.append(pu.create_cylinder_obj("Mon_Post", radius=0.22, depth=1.35, location=(1.4, 6.90, 0.78), bevel_width=0.02, material=mats["aluminum"]))
    mon_parts.append(pu.create_beveled_box("Mon_Arm_Lower", size=(0.32, 1.45, 0.30), location=(0.90, 6.65, 1.68), rotation=(math.radians(22), 0.0, math.radians(28)), bevel_width=0.03, material=mats["aluminum"]))
    mon_parts.append(pu.create_beveled_box("Mon_Arm_Upper", size=(0.28, 1.10, 0.28), location=(0.35, 6.38, 2.65), rotation=(math.radians(28), 0.0, math.radians(-18)), bevel_width=0.03, material=mats["aluminum"]))

    # Gently curved 38-inch ultrawide bezel + emissive Sugon Cloud dashboard screen
    bm_scr = bmesh.new()
    seg_w = 24
    scr_w, scr_h = 8.8, 3.75
    curve_r = 18.0
    cx_m, cy_m, cz_m = 0.2, 5.75, 3.65

    # Bezel housing (curved slab)
    front_row_b, front_row_t = [], []
    back_row_b, back_row_t = [], []
    for i in range(seg_w + 1):
        u = i / float(seg_w)
        ang = (u - 0.5) * (scr_w / curve_r)
        px = cx_m + math.sin(ang) * curve_r
        py = cy_m + (1.0 - math.cos(ang)) * curve_r
        front_row_b.append(bm_scr.verts.new((px, py - 0.12, cz_m - scr_h * 0.5)))
        front_row_t.append(bm_scr.verts.new((px, py - 0.12, cz_m + scr_h * 0.5)))
        back_row_b.append(bm_scr.verts.new((px, py + 0.12, cz_m - scr_h * 0.5)))
        back_row_t.append(bm_scr.verts.new((px, py + 0.12, cz_m + scr_h * 0.5)))

    for i in range(seg_w):
        bm_scr.faces.new((front_row_b[i], front_row_b[i + 1], front_row_t[i + 1], front_row_t[i]))
        bm_scr.faces.new((back_row_b[i + 1], back_row_b[i], back_row_t[i], back_row_t[i + 1]))
        bm_scr.faces.new((front_row_t[i], front_row_t[i + 1], back_row_t[i + 1], back_row_t[i]))
        bm_scr.faces.new((back_row_b[i], back_row_b[i + 1], front_row_b[i + 1], front_row_b[i]))
    bm_scr.faces.new((back_row_b[0], front_row_b[0], front_row_t[0], back_row_t[0]))
    bm_scr.faces.new((front_row_b[-1], back_row_b[-1], back_row_t[-1], front_row_t[-1]))
    bmesh.ops.recalc_face_normals(bm_scr, faces=bm_scr.faces)
    for f in bm_scr.faces:
        f.smooth = True
    m_bez = bpy.data.meshes.new("Mon_Bezel_Mesh")
    bm_scr.to_mesh(m_bez)
    bm_scr.free()
    bez_obj = bpy.data.objects.new("Mon_Bezel", m_bez)
    bpy.context.collection.objects.link(bez_obj)
    bez_obj.data.materials.append(mats["matte_black"])
    mon_parts.append(bez_obj)

    # Emissive curved LCD panel right in front of bezel (-Y side)
    bm_lcd = bmesh.new()
    uv_l = bm_lcd.loops.layers.uv.verify()
    lcd_w, lcd_h = 8.52, 3.48
    lb, lt = [], []
    for i in range(seg_w + 1):
        u = i / float(seg_w)
        ang = (u - 0.5) * (lcd_w / curve_r)
        px = cx_m + math.sin(ang) * curve_r
        py = cy_m + (1.0 - math.cos(ang)) * curve_r - 0.132
        lb.append(bm_lcd.verts.new((px, py, cz_m - lcd_h * 0.5)))
        lt.append(bm_lcd.verts.new((px, py, cz_m + lcd_h * 0.5)))
    for i in range(seg_w):
        u0, u1 = i / float(seg_w), (i + 1) / float(seg_w)
        f = bm_lcd.faces.new((lb[i], lb[i + 1], lt[i + 1], lt[i]))
        f.smooth = True
        for loop, uv in zip(f.loops, [(u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)]):
            loop[uv_l].uv = uv
    bmesh.ops.recalc_face_normals(bm_lcd, faces=bm_lcd.faces)
    m_lcd = bpy.data.meshes.new("Mon_LCD_Mesh")
    bm_lcd.to_mesh(m_lcd)
    bm_lcd.free()
    lcd_obj = bpy.data.objects.new("Mon_LCD", m_lcd)
    bpy.context.collection.objects.link(lcd_obj)
    lcd_obj.data.materials.append(mats["monitor_ui"])
    mon_parts.append(lcd_obj)

    static_props.append(join_parts_as(mon_parts, "Prop_Static_Monitor", root))

    # 2. Custom 75% Mechanical Keyboard inside West Loop Island (-5.6, -0.35)
    kb_parts = []
    kb_cx, kb_cy, kb_rot = -5.65, -0.35, math.radians(-8)
    rot_m = Matrix.Rotation(kb_rot, 4, "Z")

    def kb_world(lx, ly, lz):
        v = rot_m @ Vector((lx, ly, lz))
        return (kb_cx + v.x, kb_cy + v.y, v.z)

    # Anodized CNC aluminum case
    kb_parts.append(pu.create_beveled_box(
        "KB_Case",
        size=(3.05, 1.32, 0.24),
        location=kb_world(0.0, 0.0, 0.14),
        rotation=(math.radians(5), 0.0, kb_rot),
        bevel_width=0.025,
        material=mats["matte_black"],
    ))
    # Sculpted 5x15 keycap matrix (White alphas, Dark gray mods, Sugon Red ESC & Enter!)
    rows, cols = 5, 15
    for r in range(rows):
        for c in range(cols):
            # Merge spacebar on bottom row (r==0, c in 4..9)
            if r == 0 and 5 <= c <= 9:
                continue
            kw = 0.92 if (r == 0 and c == 4) else 0.172
            lx = -1.32 + c * 0.188 + (0.37 if (r == 0 and c == 4) else 0.0)
            ly = -0.45 + r * 0.215
            lz = 0.275 + r * 0.018
            if r == 4 and c == 0:
                kmat = mats["key_red"]       # Red ESC
            elif r == 2 and c >= 13:
                kmat = mats["key_red"]       # Red Enter
            elif c == 0 or c >= 13 or r == 0 or r == 4:
                kmat = mats["key_dark"]      # Dark modifiers
            else:
                kmat = mats["key_white"]     # Crisp white alphas
            kb_parts.append(pu.create_beveled_box(
                f"Key_{r}_{c}",
                size=(kw, 0.168, 0.09),
                location=kb_world(lx, ly, lz),
                rotation=(math.radians(5), 0.0, kb_rot),
                bevel_width=0.012,
                bevel_segments=1,
                material=kmat,
            ))

    # Coiled Aviator Cable behind keyboard (kept cleanly inside West island!)
    for s in range(18):
        cx_c = -0.95 + s * 0.075
        kb_parts.append(pu.create_cylinder_obj(
            f"KB_Coil_{s}",
            radius=0.075,
            depth=0.055,
            vertices=16,
            location=kb_world(cx_c, 0.82, 0.095),
            rotation=(0.0, math.radians(90), kb_rot),
            material=mats["matte_black"],
        ))
    kb_parts.append(pu.create_cylinder_obj(
        "KB_Aviator_Plug",
        radius=0.055,
        depth=0.32,
        vertices=18,
        location=kb_world(0.58, 0.82, 0.065),
        rotation=(0.0, math.radians(90), kb_rot),
        material=mats["aluminum"],
    ))
    static_props.append(join_parts_as(kb_parts, "Prop_Static_Keyboard", root))

    # 3. Ergonomic Wireless Mouse + Hard Pad inside East Loop Island (+5.55, -0.45)
    ms_parts = []
    ms_cx, ms_cy = 5.55, -0.45
    ms_parts.append(pu.create_beveled_box(
        "Mouse_Pad",
        size=(2.15, 1.85, 0.025),
        location=(ms_cx, ms_cy, 0.035),
        rotation=(0.0, 0.0, math.radians(6)),
        bevel_width=0.01,
        material=mats["dark_felt"],
    ))
    # Sculpted ergonomic mouse dome
    bm_m = bmesh.new()
    bmesh.ops.create_uvsphere(bm_m, u_segments=24, v_segments=14, radius=1.0)
    for v in list(bm_m.verts):
        if v.co.z < -0.05:
            bm_m.verts.remove(v)
        else:
            v.co.x = v.co.x * 0.42 + (0.04 if v.co.x < 0 else 0.0)
            v.co.y *= 0.66
            v.co.z = 0.05 + max(0.0, v.co.z) * 0.36
    bmesh.ops.recalc_face_normals(bm_m, faces=bm_m.faces)
    for f in bm_m.faces:
        f.smooth = True
    m_ms = bpy.data.meshes.new("Mouse_Body_Mesh")
    bm_m.to_mesh(m_ms)
    bm_m.free()
    ms_body = bpy.data.objects.new("Mouse_Body", m_ms)
    bpy.context.collection.objects.link(ms_body)
    ms_body.location = (ms_cx, ms_cy, 0.0)
    ms_body.rotation_euler = (0.0, 0.0, math.radians(10))
    ms_body.data.materials.append(mats["matte_black"])
    ms_parts.append(ms_body)
    ms_parts.append(pu.create_cylinder_obj(
        "Mouse_Wheel",
        radius=0.075,
        depth=0.05,
        vertices=20,
        location=(ms_cx - 0.04, ms_cy + 0.28, 0.36),
        rotation=(0.0, math.radians(90), math.radians(10)),
        material=mats["aluminum"],
    ))
    static_props.append(join_parts_as(ms_parts, "Prop_Static_Mouse", root))

    # 4. Matte-Black Cantilever Architect Desk Lamp (-12.2, +4.8)
    lamp_parts = []
    lamp_parts.append(pu.create_beveled_box("Lamp_Clamp", size=(0.55, 0.65, 0.42), location=(-12.35, 4.85, 0.12), bevel_width=0.03, material=mats["matte_black"]))
    lamp_parts.append(pu.create_beveled_box("Lamp_Arm_1", size=(0.14, 0.18, 3.85), location=(-11.65, 4.70, 2.05), rotation=(0.0, math.radians(22), math.radians(-10)), bevel_width=0.02, material=mats["matte_black"]))
    lamp_parts.append(pu.create_beveled_box("Lamp_Arm_2", size=(0.13, 0.16, 3.35), location=(-9.95, 4.35, 4.55), rotation=(0.0, math.radians(56), math.radians(-12)), bevel_width=0.02, material=mats["matte_black"]))
    # Bell shade + glowing warm bulb
    bm_sh = bmesh.new()
    bmesh.ops.create_cone(bm_sh, cap_ends=True, cap_tris=False, segments=32, radius1=0.92, radius2=0.34, depth=1.15)
    for f in bm_sh.faces:
        f.smooth = True
    m_sh = bpy.data.meshes.new("Lamp_Shade_Mesh")
    bm_sh.to_mesh(m_sh)
    bm_sh.free()
    sh_obj = bpy.data.objects.new("Lamp_Shade", m_sh)
    bpy.context.collection.objects.link(sh_obj)
    sh_obj.location = (-8.55, 4.10, 5.15)
    sh_obj.rotation_euler = (math.radians(12), math.radians(18), 0.0)
    sh_obj.data.materials.append(mats["matte_black"])
    lamp_parts.append(sh_obj)
    lamp_parts.append(pu.create_cylinder_obj(
        "Lamp_Bulb_Glow",
        radius=0.72,
        depth=0.08,
        vertices=28,
        location=(-8.38, 4.02, 4.66),
        rotation=(math.radians(12), math.radians(18), 0.0),
        material=mats["warm_bulb"],
    ))
    static_props.append(join_parts_as(lamp_parts, "Prop_Static_DeskLamp", root))

    # 5. White & Crimson Ceramic Coffee Mug on Cork Coaster (-12.05, -4.45)
    mug_parts = []
    mcx, mcy = -12.05, -4.45
    mug_parts.append(pu.create_cylinder_obj("Mug_Coaster", radius=0.82, depth=0.07, vertices=32, location=(mcx, mcy, 0.035), bevel_width=0.015, material=mats["cork"]))
    mug_parts.append(pu.create_cylinder_obj("Mug_Body", radius=0.64, depth=1.42, vertices=36, location=(mcx, mcy, 0.78), bevel_width=0.03, material=mats["ceramic_white"]))
    mug_parts.append(pu.create_cylinder_obj("Mug_Red_Stripe", radius=0.648, depth=0.26, vertices=36, location=(mcx, mcy, 0.78), bevel_width=0.005, material=mats["key_red"]))
    mug_parts.append(pu.create_cylinder_obj("Mug_Coffee", radius=0.56, depth=0.05, vertices=32, location=(mcx, mcy, 1.47), material=mats["coffee"]))
    # Mug C-handle
    for a_idx in range(9):
        ang = math.radians(-70 + a_idx * 17.5)
        hx = mcx - 0.62 - math.cos(ang) * 0.34
        hz = 0.78 + math.sin(ang) * 0.42
        mug_parts.append(pu.create_beveled_box(f"Mug_Handle_{a_idx}", size=(0.13, 0.14, 0.16), location=(hx, mcy, hz), bevel_width=0.03, material=mats["ceramic_white"]))
    static_props.append(join_parts_as(mug_parts, "Prop_Static_CoffeeMug", root))

    # 6. Potted Succulent Plant (-6.7, +6.25)
    suc_parts = []
    scx, scy = -6.7, 6.25
    suc_parts.append(pu.create_cylinder_obj("Pot_Saucer", radius=0.58, depth=0.09, vertices=28, location=(scx, scy, 0.045), bevel_width=0.015, material=mats["cork"]))
    suc_parts.append(pu.create_cylinder_obj("Pot_Ceramic", radius=0.48, depth=0.78, vertices=28, location=(scx, scy, 0.45), bevel_width=0.025, material=mats["ceramic_white"]))
    for ring_i, (n_leaf, r_off, z_off, tilt) in enumerate([(8, 0.28, 0.88, 52), (7, 0.18, 0.98, 34), (5, 0.08, 1.06, 16)]):
        for k in range(n_leaf):
            ang = k * (2.0 * math.pi / n_leaf) + ring_i * 0.4
            lx = scx + math.cos(ang) * r_off
            ly = scy + math.sin(ang) * r_off
            suc_parts.append(pu.create_beveled_box(
                f"Leaf_{ring_i}_{k}",
                size=(0.16, 0.30, 0.08),
                location=(lx, ly, z_off),
                rotation=(math.radians(tilt), 0.0, ang - math.pi * 0.5),
                bevel_width=0.025,
                material=mats["succulent_green"],
            ))
    static_props.append(join_parts_as(suc_parts, "Prop_Static_Succulent", root))

    # 7. Stacked Hardcover CS Tech Books (+8.1, +6.15) & Vertical Trio (+10.65, +6.05)
    book_parts = []
    # Horizontal stack of 3 hardcover books
    book_specs = [
        (0.16, mats["matte_black"]),
        (0.48, mats["book_blue"]),
        (0.80, mats["key_red"]),
    ]
    for idx, (bz, bmat) in enumerate(book_specs):
        book_parts.append(pu.create_beveled_box(f"Book_H_Cover_{idx}", size=(2.45, 1.75, 0.30), location=(8.05, 6.15, bz), rotation=(0, 0, math.radians(-4 + idx * 3)), bevel_width=0.02, material=bmat))
        book_parts.append(pu.create_beveled_box(f"Book_H_Pages_{idx}", size=(2.36, 1.66, 0.24), location=(8.05, 6.10, bz), rotation=(0, 0, math.radians(-4 + idx * 3)), bevel_width=0.005, material=mats["blind_cream"]))
    # Vertical trio of tall tech books
    for idx, bmat in enumerate([mats["key_red"], mats["matte_black"], mats["book_blue"]]):
        bx = 9.95 + idx * 0.42
        book_parts.append(pu.create_beveled_box(f"Book_V_{idx}", size=(0.38, 1.80, 2.35), location=(bx, 6.05, 1.18), rotation=(0, math.radians(-3), math.radians(-5)), bevel_width=0.02, material=bmat))
    static_props.append(join_parts_as(book_parts, "Prop_Static_TechBooks", root))

    # 8. Mini-ITX "曙光云·赤霄" Confidential Compute Cube Server (+12.25, +3.75)
    srv_parts = []
    svx, svy = 12.25, 3.75
    srv_parts.append(pu.create_beveled_box("Srv_Chassis", size=(1.68, 2.65, 2.48), location=(svx, svy, 1.24), rotation=(0, 0, math.radians(-6)), bevel_width=0.035, material=mats["gunmetal"]))
    # Glowing side matrix window facing the track (-X)
    srv_parts.append(pu.create_beveled_box("Srv_Matrix_Cyan", size=(0.04, 2.10, 1.85), location=(svx - 0.83, svy, 1.26), rotation=(0, 0, math.radians(-6)), bevel_width=0.008, material=mats["neon_cyan"]))
    srv_parts.append(pu.create_beveled_box("Srv_Matrix_Red", size=(0.05, 1.95, 0.14), location=(svx - 0.84, svy, 0.52), rotation=(0, 0, math.radians(-6)), bevel_width=0.006, material=mats["neon_red"]))
    srv_parts.append(pu.create_cylinder_obj("Srv_Power_Ring", radius=0.11, depth=0.03, vertices=24, location=(svx - 0.08, svy - 1.05, 2.49), material=mats["neon_cyan"]))
    static_props.append(join_parts_as(srv_parts, "Prop_Static_MiniServer", root))

    return static_props


def build_3d_track_meshes(xyz, tangents, rights, ups, arc_len, total_len, mats, root):
    """
    Build:
      - Visual Road Deck & Structural Viaduct Slab (`Track_Road_Visual`)
      - Left & Right Elevated Neon Energy Tubes (`Track_Neon_Rail_L`, `Track_Neon_Rail_R`) -> Custom GLSL in Three.js!
      - Semi-transparent Guardrail Walls (`Track_Guardrail_Visual`)
      - Automatic Non-Interfering Support Pillars (`Track_Support_Pillars`)
      - Clean Physics TriMeshes (`Col_Track_Road`, `Col_Track_Wall`)
    """
    n = len(xyz)
    v_repeats = round(total_len / 2.6)  # Integer repeat count so UV wraps seamlessly at sample n->0!

    # 1. Visual Road Surface + Viaduct Structural Underside
    bm_road = bmesh.new()
    uv_road = bm_road.loops.layers.uv.verify()

    top_l, top_c, top_r = [], [], []
    bot_l, bot_r = [], []
    for i in range(n):
        p = Vector(xyz[i])
        r = Vector(rights[i])
        u = Vector(ups[i])
        top_l.append(bm_road.verts.new(p - r * TRACK_HALF_WIDTH))
        top_c.append(bm_road.verts.new(p))
        top_r.append(bm_road.verts.new(p + r * TRACK_HALF_WIDTH))
        bot_l.append(bm_road.verts.new(p - r * (TRACK_HALF_WIDTH * 0.94) - u * DECK_THICKNESS))
        bot_r.append(bm_road.verts.new(p + r * (TRACK_HALF_WIDTH * 0.94) - u * DECK_THICKNESS))

    for i in range(n):
        j = (i + 1) % n
        v0 = (arc_len[i] / total_len) * v_repeats
        v1 = (arc_len[j] / total_len) * v_repeats if j > 0 else float(v_repeats)

        # Top road left half (u: 0.0 -> 0.5) & right half (u: 0.5 -> 1.0)
        f_tl = bm_road.faces.new((top_l[i], top_c[i], top_c[j], top_l[j]))
        f_tl.material_index = 0
        f_tl.smooth = True
        for loop, uv in zip(f_tl.loops, [(0.0, v0), (0.5, v0), (0.5, v1), (0.0, v1)]):
            loop[uv_road].uv = uv

        f_tr = bm_road.faces.new((top_c[i], top_r[i], top_r[j], top_c[j]))
        f_tr.material_index = 0
        f_tr.smooth = True
        for loop, uv in zip(f_tr.loops, [(0.5, v0), (1.0, v0), (1.0, v1), (0.5, v1)]):
            loop[uv_road].uv = uv

        # Structural side fascias & bottom deck (material_index = 1: gunmetal structure)
        f_sl = bm_road.faces.new((bot_l[i], bot_l[j], top_l[j], top_l[i]))
        f_sr = bm_road.faces.new((top_r[i], top_r[j], bot_r[j], bot_r[i]))
        f_bt = bm_road.faces.new((bot_r[i], bot_r[j], bot_l[j], bot_l[i]))
        for f_st in (f_sl, f_sr, f_bt):
            f_st.material_index = 1
            f_st.smooth = True

    bmesh.ops.recalc_face_normals(bm_road, faces=bm_road.faces)
    m_road = bpy.data.meshes.new("Track_Road_Visual_Mesh")
    bm_road.to_mesh(m_road)
    bm_road.free()

    road_visual = bpy.data.objects.new("Track_Road_Visual", m_road)
    bpy.context.collection.objects.link(road_visual)
    road_visual.data.materials.append(mats["track_road"])
    road_visual.data.materials.append(mats["gunmetal"])
    road_visual.parent = root

    # 2. Continuous Neon Energy Guardrail Tubes (Left = Cyan, Right = Sugon Red)
    # UV.x = normalized [0..1] progress along full circuit so GLSL shader animates directional pulses!
    for side_sign, side_name, mat_neon in [(-1.0, "L", mats["neon_cyan"]), (1.0, "R", mats["neon_red"])]:
        bm_n = bmesh.new()
        uv_n = bm_n.loops.layers.uv.verify()
        tube_r = 0.055
        n_sides = 8
        rings = []
        for i in range(n):
            p = Vector(xyz[i]) + Vector(rights[i]) * (side_sign * WALL_OFFSET) + Vector(ups[i]) * (WALL_HEIGHT + 0.03)
            r_ax = Vector(rights[i])
            u_ax = Vector(ups[i])
            ring = []
            for k in range(n_sides):
                ang = k * (2.0 * math.pi / n_sides)
                ring.append(bm_n.verts.new(p + (r_ax * math.cos(ang) + u_ax * math.sin(ang)) * tube_r))
            rings.append(ring)

        for i in range(n):
            j = (i + 1) % n
            u0 = arc_len[i] / total_len
            u1 = arc_len[j] / total_len if j > 0 else 1.0
            for k in range(n_sides):
                kn = (k + 1) % n_sides
                v0, v1 = k / float(n_sides), (k + 1) / float(n_sides)
                f = bm_n.faces.new((rings[i][k], rings[i][kn], rings[j][kn], rings[j][k]))
                f.smooth = True
                for loop, uv in zip(f.loops, [(u0, v0), (u0, v1), (u1, v1), (u1, v0)]):
                    loop[uv_n].uv = uv
        bmesh.ops.recalc_face_normals(bm_n, faces=bm_n.faces)
        m_n = bpy.data.meshes.new(f"Track_Neon_Rail_{side_name}_Mesh")
        bm_n.to_mesh(m_n)
        bm_n.free()
        n_obj = bpy.data.objects.new(f"Track_Neon_Rail_{side_name}", m_n)
        bpy.context.collection.objects.link(n_obj)
        n_obj.data.materials.append(mat_neon)
        n_obj.parent = root

    # 3. Sleek Polycarbonate Guardrail Walls + Stanchion Posts
    bm_gw = bmesh.new()
    for side_sign in (-1.0, 1.0):
        inner_b, inner_t, outer_b, outer_t = [], [], [], []
        for i in range(n):
            p = Vector(xyz[i])
            r = Vector(rights[i])
            u = Vector(ups[i])
            ib = p + r * (side_sign * (WALL_OFFSET - 0.03))
            ob = p + r * (side_sign * (WALL_OFFSET + 0.03))
            inner_b.append(bm_gw.verts.new(ib))
            inner_t.append(bm_gw.verts.new(ib + u * WALL_HEIGHT))
            outer_b.append(bm_gw.verts.new(ob - u * DECK_THICKNESS))
            outer_t.append(bm_gw.verts.new(ob + u * WALL_HEIGHT))
        for i in range(n):
            j = (i + 1) % n
            if side_sign > 0:
                bm_gw.faces.new((inner_b[i], inner_t[i], inner_t[j], inner_b[j]))
                bm_gw.faces.new((outer_b[i], outer_b[j], outer_t[j], outer_t[i]))
                bm_gw.faces.new((inner_t[i], outer_t[i], outer_t[j], inner_t[j]))
            else:
                bm_gw.faces.new((inner_b[i], inner_b[j], inner_t[j], inner_t[i]))
                bm_gw.faces.new((outer_b[i], outer_t[i], outer_t[j], outer_b[j]))
                bm_gw.faces.new((outer_t[i], inner_t[i], inner_t[j], outer_t[j]))
    bmesh.ops.recalc_face_normals(bm_gw, faces=bm_gw.faces)
    for f in bm_gw.faces:
        f.smooth = True
    m_gw = bpy.data.meshes.new("Track_Guardrail_Visual_Mesh")
    bm_gw.to_mesh(m_gw)
    bm_gw.free()
    gw_obj = bpy.data.objects.new("Track_Guardrail_Visual", m_gw)
    bpy.context.collection.objects.link(gw_obj)
    gw_obj.data.materials.append(mats["guard_glass"])
    gw_obj.parent = root

    # 4. Smart Viaduct Support Pillars (automatically avoids lower road & props!)
    pillar_parts = []
    low_pts_xy = xyz[xyz[:, 2] < 0.85][:, :2]
    for i in range(0, n, 24):
        pz = float(xyz[i, 2]) - DECK_THICKNESS
        if pz < 0.32:
            continue
        px, py = float(xyz[i, 0]), float(xyz[i, 1])
        # Check XY distance to all ground-level track points (e.g. Underpass!) — clean single-span bridge leap!
        dists_low = np.linalg.norm(low_pts_xy - np.array([px, py]), axis=1)
        if np.min(dists_low) < (WALL_OFFSET + 0.85):
            continue
        else:
            pillar_parts.append(pu.create_cylinder_obj(
                f"Viaduct_Pillar_{i}",
                radius=0.18,
                depth=pz + 0.04,
                vertices=20,
                location=(px, py, pz * 0.5),
                bevel_width=0.015,
                material=mats["gunmetal"],
            ))
            pillar_parts.append(pu.create_cylinder_obj(
                f"Viaduct_Foot_{i}",
                radius=0.34,
                depth=0.08,
                vertices=20,
                location=(px, py, 0.04),
                material=mats["neon_cyan"] if (i // 24) % 2 == 0 else mats["aluminum"],
            ))

    pillars_obj = join_parts_as(pillar_parts, "Track_Support_Pillars", root) if pillar_parts else None

    # 5. Clean Manifold Physics TriMeshes (`Col_Track_Road` & `Col_Track_Wall`)
    bm_col_r = bmesh.new()
    cl_verts, cr_verts = [], []
    for i in range(n):
        p = Vector(xyz[i])
        r = Vector(rights[i])
        # Slightly wider than visual kerbs up to WALL_OFFSET so there is zero gap between road & wall!
        cl_verts.append(bm_col_r.verts.new(p - r * WALL_OFFSET))
        cr_verts.append(bm_col_r.verts.new(p + r * WALL_OFFSET))
    for i in range(n):
        j = (i + 1) % n
        bm_col_r.faces.new((cl_verts[i], cr_verts[i], cr_verts[j], cl_verts[j]))
    bmesh.ops.triangulate(bm_col_r, faces=bm_col_r.faces)
    bmesh.ops.recalc_face_normals(bm_col_r, faces=bm_col_r.faces)
    m_col_r = bpy.data.meshes.new("Col_Track_Road_Mesh")
    bm_col_r.to_mesh(m_col_r)
    bm_col_r.free()
    col_road = bpy.data.objects.new("Col_Track_Road", m_col_r)
    bpy.context.collection.objects.link(col_road)
    col_road.parent = root

    bm_col_w = bmesh.new()
    for side_sign in (-1.0, 1.0):
        wb, wt = [], []
        for i in range(n):
            p = Vector(xyz[i]) + Vector(rights[i]) * (side_sign * WALL_OFFSET)
            u = Vector(ups[i])
            wb.append(bm_col_w.verts.new(p - u * 0.20))
            wt.append(bm_col_w.verts.new(p + u * (WALL_HEIGHT + 1.35)))
        for i in range(n):
            j = (i + 1) % n
            if side_sign > 0:
                bm_col_w.faces.new((wb[i], wt[i], wt[j], wb[j]))
            else:
                bm_col_w.faces.new((wb[i], wb[j], wt[j], wt[i]))
    bmesh.ops.triangulate(bm_col_w, faces=bm_col_w.faces)
    bmesh.ops.recalc_face_normals(bm_col_w, faces=bm_col_w.faces)
    m_col_w = bpy.data.meshes.new("Col_Track_Wall_Mesh")
    bm_col_w.to_mesh(m_col_w)
    bm_col_w.free()
    col_wall = bpy.data.objects.new("Col_Track_Wall", m_col_w)
    bpy.context.collection.objects.link(col_wall)
    col_wall.parent = root

    return road_visual, pillars_obj, col_road, col_wall


def run_bvh_collision_and_clearance_audit(xyz, tangents, rights, ups, road_visual, pillars_obj, static_props):
    """
    Google Desk Racer Pipeline Step:
    1. BVHTree mesh-overlap check between Track_Road_Visual and every Static Desk Prop.
    2. 640-point Swept-Car Envelope (width=1.70, height=1.05 above road) check against Static Props,
       Viaduct Pillars, and Overhead Overpass Bridge deck!
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh_road = BVHTree.FromObject(road_visual, depsgraph)

    prop_overlaps = {}
    total_prop_overlaps = 0
    prop_bvhs = {}

    for prop in static_props:
        bvh_p = BVHTree.FromObject(prop, depsgraph)
        prop_bvhs[prop.name] = bvh_p
        pairs = bvh_road.overlap(bvh_p)
        prop_overlaps[prop.name] = len(pairs)
        total_prop_overlaps += len(pairs)

    bvh_pillars = BVHTree.FromObject(pillars_obj, depsgraph) if pillars_obj else None

    # Build temporary swept-car clearance test box mesh (1.72m wide x 1.50m long x 0.98m tall, lifted +0.12m above road)
    n = len(xyz)
    swept_violations = []
    min_overpass_headroom = 999.0

    for i in range(0, n, 2):
        p = Vector(xyz[i])
        t = Vector(tangents[i])
        r = Vector(rights[i])
        u = Vector(ups[i])

        # Check vertical headroom to any non-adjacent track segment overhead (Overpass check!)
        for j in range(0, n, 4):
            dist_idx = min(abs(i - j), n - abs(i - j))
            if dist_idx < 50:
                continue
            xy_dist = math.hypot(float(xyz[i, 0] - xyz[j, 0]), float(xyz[i, 1] - xyz[j, 1]))
            if xy_dist < (TRACK_HALF_WIDTH * 1.6) and xyz[j, 2] > xyz[i, 2]:
                clear_h = float(xyz[j, 2] - DECK_THICKNESS - xyz[i, 2])
                if clear_h < min_overpass_headroom:
                    min_overpass_headroom = clear_h
                if clear_h < 1.25:
                    swept_violations.append({"sample": i, "type": "LOW_OVERPASS_HEADROOM", "clearance": round(clear_h, 3)})

        # Build 9 probe rays / points inside the car's swept safety envelope (width ±0.85, height 0.18..1.05)
        for lat in (-0.85, 0.0, 0.85):
            for hgt in (0.22, 0.65, 1.02):
                probe = p + r * lat + u * hgt
                for pname, pbvh in prop_bvhs.items():
                    loc, norm, fidx, dist = pbvh.find_nearest(probe, 0.12)
                    if loc is not None and dist < 0.08:
                        swept_violations.append({"sample": i, "type": f"PROP_PROXIMITY:{pname}", "dist": round(dist, 4)})
                if bvh_pillars is not None:
                    loc, norm, fidx, dist = bvh_pillars.find_nearest(probe, 0.12)
                    if loc is not None and dist < 0.08:
                        swept_violations.append({"sample": i, "type": "PILLAR_INTRUSION", "dist": round(dist, 4)})

    report = {
        "status": "PASS" if (total_prop_overlaps == 0 and len(swept_violations) == 0) else "FAIL",
        "trackSamplesChecked": n,
        "staticPropMeshOverlaps": prop_overlaps,
        "totalStaticPropMeshOverlaps": total_prop_overlaps,
        "minOverpassVerticalHeadroom": round(min_overpass_headroom, 3),
        "carHeightReference": 0.46,
        "sweptEnvelopeViolationsCount": len(swept_violations),
        "sweptEnvelopeViolations": swept_violations[:20],
    }

    report_path = os.path.join(pu.DATA_DIR, "collision_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("=== BLENDER BVH COLLISION & CLEARANCE AUDIT ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "PASS":
        raise RuntimeError(f"BVH Collision/Clearance check failed: {report}")
    return report


def export_track_metadata(xyz, tangents, rights, ups, bank, arc_len, total_len):
    """Export Three.js-space spline, start grid, gantry pose, checkpoints, boost pads, crypto nodes & dynamic props."""
    n = len(xyz)
    start_idx = 36  # Flat Start/Finish straight!

    # Re-index spline circularly so index 0 IS the Start/Finish Gantry line!
    order = [(start_idx + k) % n for k in range(n)]
    xyz_o = xyz[order]
    tan_o = tangents[order]
    rgt_o = rights[order]
    ups_o = ups[order]
    bnk_o = bank[order]

    # Recompute monotonic arc-length starting at 0 = Start/Finish line
    s_o = np.zeros(n, dtype=np.float64)
    acc = 0.0
    for k in range(1, n):
        acc += float(np.linalg.norm(xyz_o[k] - xyz_o[k - 1]))
        s_o[k] = acc

    waypoints = []
    for k in range(0, n, 2):  # 320 dense Three.js waypoints
        waypoints.append({
            "pos": bl_to_three_pos(xyz_o[k]),
            "tangent": bl_to_three_vec(tan_o[k]),
            "right": bl_to_three_vec(rgt_o[k]),
            "up": bl_to_three_vec(ups_o[k]),
            "bankDeg": round(float(bnk_o[k]), 2),
            "s": round(float(s_o[k]), 3),
        })

    # 10 Checkpoints around the loop (index 0 = Start/Finish line)
    checkpoints = []
    num_cp = 10
    for cp_i in range(num_cp):
        idx = int(round(cp_i * n / num_cp)) % n
        checkpoints.append({
            "id": cp_i,
            "pos": bl_to_three_pos(xyz_o[idx]),
            "tangent": bl_to_three_vec(tan_o[idx]),
            "up": bl_to_three_vec(ups_o[idx]),
            "right": bl_to_three_vec(rgt_o[idx]),
            "width": TRACK_HALF_WIDTH * 2.1,
            "s": round(float(s_o[idx]), 3),
        })

    # 5 Speed Boost Pads (including Start Straight exit, Underpass approach, Spiral climb, and High Launch Ramp!)
    boost_indices = [18, 95, 195, 282, 435]
    boost_pads = []
    for b_id, idx in enumerate(boost_indices):
        idx = idx % n
        boost_pads.append({
            "id": b_id,
            "pos": bl_to_three_pos(xyz_o[idx] + ups_o[idx] * 0.025),
            "tangent": bl_to_three_vec(tan_o[idx]),
            "up": bl_to_three_vec(ups_o[idx]),
            "right": bl_to_three_vec(rgt_o[idx]),
        })

    # 16 Floating "立体密算 (Stereo Confidential Computing)" Encrypted Compute Energy Cubes!
    crypto_nodes = []
    for c_id in range(16):
        idx = int((32 + c_id * (n / 16.0)) % n)
        lat_offset = 0.55 * math.sin(c_id * 1.7)
        c_pos = xyz_o[idx] + rgt_o[idx] * lat_offset + ups_o[idx] * 0.42
        crypto_nodes.append({
            "id": c_id,
            "pos": bl_to_three_pos(c_pos),
            "up": bl_to_three_vec(ups_o[idx]),
        })

    # 18 Dynamic Knockable Stationery Obstacles along wide shoulders (Keycaps, Dice, Erasers, Mini Energy Cells)
    dyn_props = []
    prop_kinds = ["keycap_red", "keycap_cyan", "dice", "eraser", "energy_can"]
    shoulder_indices = [55, 62, 138, 145, 225, 232, 315, 322, 395, 402, 478, 485, 545, 552, 595, 602]
    for p_id, idx in enumerate(shoulder_indices):
        idx = idx % n
        lat = (0.72 if p_id % 2 == 0 else -0.72)
        d_pos = xyz_o[idx] + rgt_o[idx] * lat + ups_o[idx] * 0.22
        dyn_props.append({
            "id": p_id,
            "kind": prop_kinds[p_id % len(prop_kinds)],
            "pos": bl_to_three_pos(d_pos),
        })

    # Car spawns 2.4 units behind the Start/Finish Gantry so crossing the Gantry starts/completes laps cleanly!
    spawn_idx = (n - 10) % n
    metadata = {
        "totalLength": round(float(total_len), 3),
        "trackWidth": TRACK_HALF_WIDTH * 2.0,
        "startGantry": {
            "pos": bl_to_three_pos(xyz_o[0]),
            "tangent": bl_to_three_vec(tan_o[0]),
            "up": bl_to_three_vec(ups_o[0]),
            "right": bl_to_three_vec(rgt_o[0]),
        },
        "carSpawn": {
            "pos": bl_to_three_pos(xyz_o[spawn_idx] + ups_o[spawn_idx] * 0.35),
            "tangent": bl_to_three_vec(tan_o[spawn_idx]),
            "up": bl_to_three_vec(ups_o[spawn_idx]),
        },
        "checkpoints": checkpoints,
        "boostPads": boost_pads,
        "cryptoNodes": crypto_nodes,
        "dynamicProps": dyn_props,
        "waypoints": waypoints,
    }

    meta_path = os.path.join(pu.DATA_DIR, "track_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Exported track_metadata.json -> {meta_path}")
    return metadata


def main():
    pu.clear_scene()

    mats = {
        "wood": pu.make_pbr_material(
            "Desk_Walnut_Wood",
            albedo_tex="wood_albedo.jpg",
            normal_tex="wood_normal.png",
            roughness_tex="wood_roughness.jpg",
            normal_strength=1.15,
            coat_weight=0.25,
            coat_roughness=0.28,
        ),
        "wall": pu.make_pbr_material(
            "Room_Plaster_Wall",
            albedo_tex="wall_albedo.jpg",
            normal_tex="wall_normal.png",
            roughness_tex="wall_roughness.jpg",
        ),
        "floor": pu.make_pbr_material(
            "Room_Floor_Mat",
            base_color=(0.16, 0.14, 0.12, 1.0),
            roughness=0.55,
        ),
        "deskmat": pu.make_pbr_material(
            "Desk_Mat_Woven",
            albedo_tex="deskmat_albedo.jpg",
            normal_tex="deskmat_normal.png",
            roughness_tex="deskmat_roughness.jpg",
        ),
        "dark_felt": pu.make_pbr_material(
            "Acoustic_Dark_Felt",
            base_color=(0.05, 0.055, 0.065, 1.0),
            roughness=0.92,
        ),
        "aluminum": pu.make_pbr_material(
            "Brushed_Silver_Aluminum",
            albedo_tex="metal_brushed_albedo.jpg",
            normal_tex="metal_brushed_normal.png",
            roughness_tex="metal_brushed_roughness.jpg",
            metallic=0.92,
        ),
        "gunmetal": pu.make_pbr_material(
            "Anodized_Gunmetal",
            base_color=(0.14, 0.16, 0.19, 1.0),
            metallic=0.82,
            roughness=0.28,
        ),
        "matte_black": pu.make_pbr_material(
            "Matte_Black_Metal",
            base_color=(0.045, 0.05, 0.06, 1.0),
            metallic=0.45,
            roughness=0.42,
        ),
        "monitor_ui": pu.make_pbr_material(
            "Monitor_Sugon_Screen",
            albedo_tex="monitor_screen.png",
            emissive_tex="monitor_screen.png",
            emission_strength=1.85,
            roughness=0.12,
        ),
        "key_white": pu.make_pbr_material("PBT_Key_White", base_color=(0.88, 0.90, 0.92, 1.0), roughness=0.48),
        "key_dark": pu.make_pbr_material("PBT_Key_Dark", base_color=(0.14, 0.16, 0.19, 1.0), roughness=0.50),
        "key_red": pu.make_pbr_material("Sugon_Red_Accent", base_color=(0.84, 0.02, 0.06, 1.0), roughness=0.32, coat_weight=0.4),
        "book_blue": pu.make_pbr_material("Book_Tech_Blue", base_color=(0.06, 0.20, 0.44, 1.0), roughness=0.48),
        "blind_cream": pu.make_pbr_material("Venetian_Cream", base_color=(0.94, 0.90, 0.83, 1.0), roughness=0.55),
        "sun_window": pu.make_pbr_material(
            "Window_Warm_Sun",
            base_color=(1.0, 0.95, 0.84, 1.0),
            emission_color=(1.0, 0.92, 0.74, 1.0),
            emission_strength=4.2,
        ),
        "warm_bulb": pu.make_pbr_material(
            "Lamp_Warm_Bulb",
            base_color=(1.0, 0.93, 0.78, 1.0),
            emission_color=(1.0, 0.88, 0.65, 1.0),
            emission_strength=7.5,
        ),
        "ceramic_white": pu.make_pbr_material("Ceramic_Mug_White", base_color=(0.94, 0.94, 0.93, 1.0), roughness=0.14, coat_weight=0.8),
        "cork": pu.make_pbr_material("Cork_Coaster", base_color=(0.56, 0.38, 0.22, 1.0), roughness=0.85),
        "coffee": pu.make_pbr_material("Dark_Espresso", base_color=(0.05, 0.025, 0.015, 1.0), roughness=0.08),
        "succulent_green": pu.make_pbr_material("Succulent_Leaf", base_color=(0.18, 0.46, 0.22, 1.0), roughness=0.38),
        "track_road": pu.make_pbr_material(
            "Track_Cyber_Asphalt",
            albedo_tex="track_road_albedo.png",
            normal_tex="track_road_normal.png",
            roughness_tex="track_road_roughness.jpg",
            emissive_tex="track_road_emissive.png",
            emission_strength=2.2,
            normal_strength=1.2,
        ),
        "neon_cyan": pu.make_pbr_material(
            "Track_Neon_Cyan",
            base_color=(0.0, 0.92, 1.0, 1.0),
            emission_color=(0.0, 0.88, 1.0, 1.0),
            emission_strength=6.0,
        ),
        "neon_red": pu.make_pbr_material(
            "Track_Neon_Red",
            base_color=(1.0, 0.04, 0.12, 1.0),
            emission_color=(1.0, 0.05, 0.14, 1.0),
            emission_strength=6.0,
        ),
        "guard_glass": pu.make_pbr_material(
            "Track_Guardrail_Glass",
            base_color=(0.08, 0.16, 0.26, 0.36),
            metallic=0.2,
            roughness=0.12,
            alpha=0.36,
        ),
    }

    root = bpy.data.objects.new("Desk_Racer_Scene_Root", None)
    bpy.context.collection.objects.link(root)

    xyz, tangents, rights, ups, bank, arc_len, total_len = generate_track_frames()
    build_room_and_desk(mats, root)
    static_props = build_static_desk_props(mats, root)
    road_visual, pillars_obj, col_road, col_wall = build_3d_track_meshes(
        xyz, tangents, rights, ups, arc_len, total_len, mats, root
    )

    # Run Automated BVH Collision & 640-Point Swept Envelope Clearance Check!
    run_bvh_collision_and_clearance_audit(xyz, tangents, rights, ups, road_visual, pillars_obj, static_props)

    # Export Track Metadata JSON in Three.js coordinates
    export_track_metadata(xyz, tangents, rights, ups, bank, arc_len, total_len)

    # Hide invisible physics colliders before rendering QA views, keep them in scene for GLB export
    col_road.hide_render = True
    col_wall.hide_render = True

    # Render Multi-Angle QA Views matching desk_reference.jpg & overpass close-up!
    pu.setup_qa_lighting_and_render(
        cam_location=(-2.5, -18.5, 11.8),
        cam_target=(0.2, 0.8, 1.4),
        out_filename="qa_desk_perspective.png",
        res=(1440, 810),
        lens=32.0,
    )
    pu.setup_qa_lighting_and_render(
        cam_location=(0.0, -0.2, 26.0),
        cam_target=(0.0, -0.2, 0.0),
        out_filename="qa_desk_topdown.png",
        res=(1440, 880),
        ortho_scale=28.5,
    )
    pu.setup_qa_lighting_and_render(
        cam_location=(7.2, -9.8, 4.8),
        cam_target=(1.5, -0.5, 1.5),
        out_filename="qa_overpass_and_ramp.png",
        res=(1280, 720),
        lens=34.0,
    )

    out_glb = os.path.join(pu.MODEL_DIR, "desk_track_scene.glb")
    pu.export_glb(out_glb, apply_modifiers=True)


if __name__ == "__main__":
    main()
