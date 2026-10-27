"""
Shared Blender 5.2 PBR material, geometry, UV projection, and QA camera rendering utilities.
"""

import os
import math
import bpy
import bmesh
from mathutils import Vector, Matrix

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX_DIR = os.path.join(PROJECT_ROOT, "public", "textures")
MODEL_DIR = os.path.join(PROJECT_ROOT, "public", "models")
DATA_DIR = os.path.join(PROJECT_ROOT, "public", "data")
QA_DIR = os.path.join(PROJECT_ROOT, "blender", "qa_renders")

for d in (MODEL_DIR, DATA_DIR, QA_DIR):
    os.makedirs(d, exist_ok=True)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def load_image_cached(filename: str, is_data: bool = False):
    path = os.path.join(TEX_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing texture file: {path}")
    for img in bpy.data.images:
        if os.path.abspath(bpy.path.abspath(img.filepath)) == os.path.abspath(path):
            return img
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = "Non-Color" if is_data else "sRGB"
    return img


def make_pbr_material(
    name: str,
    base_color=(0.8, 0.8, 0.8, 1.0),
    metallic: float = 0.0,
    roughness: float = 0.45,
    coat_weight: float = 0.0,
    coat_roughness: float = 0.05,
    emission_color=(0.0, 0.0, 0.0, 1.0),
    emission_strength: float = 0.0,
    alpha: float = 1.0,
    transmission: float = 0.0,
    albedo_tex: str = None,
    normal_tex: str = None,
    roughness_tex: str = None,
    metallic_tex: str = None,
    emissive_tex: str = None,
    uv_scale=(1.0, 1.0),
    normal_strength: float = 1.0,
):
    mat = bpy.data.materials.new(name=name)
    if not mat.node_tree:
        mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (650, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Coat Weight"].default_value = coat_weight
    bsdf.inputs["Coat Roughness"].default_value = coat_roughness
    bsdf.inputs["Emission Color"].default_value = emission_color
    bsdf.inputs["Emission Strength"].default_value = emission_strength
    bsdf.inputs["Alpha"].default_value = alpha
    bsdf.inputs["Transmission Weight"].default_value = transmission

    if alpha < 0.999:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"

    mapping_out = None
    if any([albedo_tex, normal_tex, roughness_tex, metallic_tex, emissive_tex]):
        tex_coord = nodes.new("ShaderNodeTexCoord")
        tex_coord.location = (-750, 0)
        mapping = nodes.new("ShaderNodeMapping")
        mapping.location = (-520, 0)
        mapping.inputs["Scale"].default_value = (uv_scale[0], uv_scale[1], 1.0)
        links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])
        mapping_out = mapping.outputs["Vector"]

    if albedo_tex:
        t_alb = nodes.new("ShaderNodeTexImage")
        t_alb.location = (-200, 280)
        t_alb.image = load_image_cached(albedo_tex, is_data=False)
        links.new(mapping_out, t_alb.inputs["Vector"])
        links.new(t_alb.outputs["Color"], bsdf.inputs["Base Color"])

    if metallic_tex:
        t_met = nodes.new("ShaderNodeTexImage")
        t_met.location = (-200, 60)
        t_met.image = load_image_cached(metallic_tex, is_data=True)
        links.new(mapping_out, t_met.inputs["Vector"])
        links.new(t_met.outputs["Color"], bsdf.inputs["Metallic"])

    if roughness_tex:
        t_rgh = nodes.new("ShaderNodeTexImage")
        t_rgh.location = (-200, -160)
        t_rgh.image = load_image_cached(roughness_tex, is_data=True)
        links.new(mapping_out, t_rgh.inputs["Vector"])
        links.new(t_rgh.outputs["Color"], bsdf.inputs["Roughness"])

    if normal_tex:
        t_nrm = nodes.new("ShaderNodeTexImage")
        t_nrm.location = (-260, -400)
        t_nrm.image = load_image_cached(normal_tex, is_data=True)
        links.new(mapping_out, t_nrm.inputs["Vector"])
        nrm_node = nodes.new("ShaderNodeNormalMap")
        nrm_node.location = (40, -380)
        nrm_node.inputs["Strength"].default_value = normal_strength
        links.new(t_nrm.outputs["Color"], nrm_node.inputs["Color"])
        links.new(nrm_node.outputs["Normal"], bsdf.inputs["Normal"])

    if emissive_tex:
        t_emi = nodes.new("ShaderNodeTexImage")
        t_emi.location = (-200, -640)
        t_emi.image = load_image_cached(emissive_tex, is_data=False)
        links.new(mapping_out, t_emi.inputs["Vector"])
        links.new(t_emi.outputs["Color"], bsdf.inputs["Emission Color"])
        if emission_strength <= 0.0:
            bsdf.inputs["Emission Strength"].default_value = 2.0

    return mat


def create_beveled_box(
    name: str,
    size=(1.0, 1.0, 1.0),
    location=(0.0, 0.0, 0.0),
    rotation=(0.0, 0.0, 0.0),
    bevel_width: float = 0.02,
    bevel_segments: int = 3,
    material=None,
    uv_box_scale: float = 1.0,
    parent=None,
):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    if bevel_width > 0.0:
        bmesh.ops.bevel(
            bm,
            geom=list(bm.edges),
            offset=bevel_width,
            segments=bevel_segments,
            profile=0.5,
            affect="EDGES",
        )
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # Clean box UV projection proportional to world size
    uv_layer = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for loop in f.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                u, v = (co.x / max(size[0], 1e-4) + 0.5) * uv_box_scale, (co.y / max(size[1], 1e-4) + 0.5) * uv_box_scale
            elif ay >= ax:
                u, v = (co.x / max(size[0], 1e-4) + 0.5) * uv_box_scale, (co.z / max(size[2], 1e-4) + 0.5) * uv_box_scale
            else:
                u, v = (co.y / max(size[1], 1e-4) + 0.5) * uv_box_scale, (co.z / max(size[2], 1e-4) + 0.5) * uv_box_scale
            loop[uv_layer].uv = (u, v)

    for f in bm.faces:
        f.smooth = bevel_width > 0.0

    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    if material:
        obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    return obj


def create_cylinder_obj(
    name: str,
    radius: float = 0.5,
    depth: float = 1.0,
    vertices: int = 32,
    location=(0.0, 0.0, 0.0),
    rotation=(0.0, 0.0, 0.0),
    bevel_width: float = 0.0,
    material=None,
    parent=None,
):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=vertices,
        radius1=radius,
        radius2=radius,
        depth=depth,
        calc_uvs=True,
    )
    if bevel_width > 0.0:
        cap_edges = [e for e in bm.edges if len(e.link_faces) == 2 and abs(e.link_faces[0].normal.dot(e.link_faces[1].normal)) < 0.5]
        if cap_edges:
            bmesh.ops.bevel(bm, geom=cap_edges, offset=bevel_width, segments=2, affect="EDGES")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = abs(f.normal.z) < 0.92 or bevel_width > 0.0
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    if material:
        obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    return obj


def setup_qa_lighting_and_render(cam_location, cam_target, out_filename: str, res=(1280, 720), lens: float = 35.0, ortho_scale: float = None):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = res[0]
    scene.render.resolution_y = res[1]
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(QA_DIR, out_filename)

    # Ensure world lighting exists
    if not scene.world:
        world = bpy.data.worlds.new("QA_World")
        scene.world = world
    if not scene.world.node_tree:
        scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.18, 0.21, 0.27, 1.0)
        bg.inputs["Strength"].default_value = 1.15

    # Add sun & fill lights if not already added
    if not any(o.type == "LIGHT" for o in bpy.data.objects):
        sun_data = bpy.data.lights.new("QA_Sun", type="SUN")
        sun_data.energy = 3.6
        sun_data.color = (1.0, 0.95, 0.88)
        sun_obj = bpy.data.objects.new("QA_Sun", sun_data)
        bpy.context.collection.objects.link(sun_obj)
        sun_obj.rotation_euler = (math.radians(48), math.radians(-28), math.radians(-35))

        fill_data = bpy.data.lights.new("QA_Fill", type="SUN")
        fill_data.energy = 1.4
        fill_data.color = (0.72, 0.86, 1.0)
        fill_obj = bpy.data.objects.new("QA_Fill", fill_data)
        bpy.context.collection.objects.link(fill_obj)
        fill_obj.rotation_euler = (math.radians(55), math.radians(40), math.radians(145))

    cam_data = bpy.data.cameras.new("QA_Cam")
    if ortho_scale is not None:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho_scale
    else:
        cam_data.lens = lens
    cam_obj = bpy.data.objects.new("QA_Cam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = Vector(cam_location)
    direction = Vector(cam_target) - Vector(cam_location)
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam_obj

    bpy.ops.render.render(write_still=True)

    bpy.data.objects.remove(cam_obj, do_unlink=True)
    bpy.data.cameras.remove(cam_data, do_unlink=True)
    return scene.render.filepath


def export_glb(filepath: str, apply_modifiers: bool = True):
    # Remove any temporary QA lights/cameras before exporting GLB
    for obj in list(bpy.data.objects):
        if obj.name.startswith("QA_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format="GLB",
        export_yup=True,
        export_apply=apply_modifiers,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
    )
    print(f"Exported GLB -> {filepath} ({os.path.getsize(filepath) / 1024:.1f} KB)")
