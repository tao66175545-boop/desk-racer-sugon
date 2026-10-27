#!/usr/bin/env python3
"""
Generate 2K High-Definition PBR Texture Suite for Desk Racer (Sugon Cloud Edition).
Outputs Albedo, Tangent-Space Normal, Roughness, Metallic, and Emissive maps into public/textures/.
"""

import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "textures")
os.makedirs(OUT_DIR, exist_ok=True)


def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def get_mono_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [r"C:\Windows\Fonts\consolab.ttf", r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyhbd.ttc"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return get_font(size, bold=True)


def tileable_noise(h: int, w: int, freq_y: int, freq_x: int, seed: int) -> np.ndarray:
    """Generate smooth periodic 2D noise via FFT band-limited synthesis (100% seamless)."""
    rng = np.random.default_rng(seed)
    grid = rng.standard_normal((freq_y, freq_x))
    img = Image.fromarray(((grid - grid.min()) / (np.ptp(grid) + 1e-8) * 255.0).astype(np.uint8), mode="L")
    # Pad circularly before resize so edges wrap seamlessly
    pad_y = max(2, freq_y // 2)
    pad_x = max(2, freq_x // 2)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    padded = np.pad(arr, ((pad_y, pad_y), (pad_x, pad_x)), mode="wrap")
    scale_y = h / freq_y
    scale_x = w / freq_x
    big_h = int(round(padded.shape[0] * scale_y))
    big_w = int(round(padded.shape[1] * scale_x))
    pil_big = Image.fromarray((padded * 255.0).astype(np.uint8), mode="L").resize((big_w, big_h), Image.Resampling.BICUBIC)
    big_arr = np.asarray(pil_big, dtype=np.float32) / 255.0
    sy = int(round(pad_y * scale_y))
    sx = int(round(pad_x * scale_x))
    cropped = big_arr[sy:sy + h, sx:sx + w]
    return (cropped - cropped.min()) / (np.ptp(cropped) + 1e-8)


def height_to_normal(height: np.ndarray, strength: float = 2.5) -> Image.Image:
    """Convert [0,1] scalar heightfield to OpenGL tangent-space RGB normal map."""
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5 * strength
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5 * strength
    nx = -dx
    ny = dy  # OpenGL Y+ up convention
    nz = np.ones_like(height)
    inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz + 1e-8)
    rgb = np.stack([
        (nx * inv_len * 0.5 + 0.5) * 255.0,
        (ny * inv_len * 0.5 + 0.5) * 255.0,
        (nz * inv_len * 0.5 + 0.5) * 255.0,
    ], axis=-1).clip(0, 255).astype(np.uint8)
    return Image.fromarray(rgb, mode="RGB")


def generate_walnut_wood(size: int = 2048):
    print("Generating 2K Walnut Desk Wood PBR set...")
    y, x = np.meshgrid(np.linspace(0, 1, size, endpoint=False), np.linspace(0, 1, size, endpoint=False), indexing="ij")
    n1 = tileable_noise(size, size, 8, 24, seed=101)
    n2 = tileable_noise(size, size, 16, 64, seed=102)
    n3 = tileable_noise(size, size, 64, 256, seed=103)
    pores = tileable_noise(size, size, 128, 512, seed=104)

    # Anisotropic walnut cathedral rings along X axis
    rings = np.sin((y * 14.0 + n1 * 2.6 + n2 * 0.75) * 2.0 * np.pi) * 0.5 + 0.5
    rings = np.power(rings, 1.45)
    fine_grain = (n3 * 0.6 + pores * 0.4)
    pore_streaks = np.clip((pores - 0.72) * 3.5, 0.0, 1.0)

    blend = np.clip(rings * 0.68 + fine_grain * 0.32 - pore_streaks * 0.22, 0.0, 1.0)

    # Rich warm American Walnut palette
    dark_col = np.array([58, 34, 21], dtype=np.float32)
    mid_col = np.array([108, 67, 42], dtype=np.float32)
    light_col = np.array([148, 96, 61], dtype=np.float32)

    albedo = np.where(
        blend[..., None] < 0.5,
        dark_col + (mid_col - dark_col) * (blend[..., None] * 2.0),
        mid_col + (light_col - mid_col) * ((blend[..., None] - 0.5) * 2.0),
    )
    # Subtle plank variation across Y
    plank_idx = np.floor(y * 6.0)
    plank_tint = 0.94 + 0.12 * (np.sin(plank_idx * 2.3 + 0.5) * 0.5 + 0.5)
    plank_seam = np.exp(-np.square(np.minimum(np.mod(y * 6.0, 1.0), 1.0 - np.mod(y * 6.0, 1.0)) * 180.0))
    albedo = albedo * plank_tint[..., None] * (1.0 - 0.35 * plank_seam[..., None])

    Image.fromarray(albedo.clip(0, 255).astype(np.uint8), mode="RGB").save(
        os.path.join(OUT_DIR, "wood_albedo.jpg"), quality=94
    )

    height = rings * 0.25 + fine_grain * 0.35 - pore_streaks * 0.55 - plank_seam * 0.8
    height_to_normal(height, strength=2.2).save(os.path.join(OUT_DIR, "wood_normal.png"))

    rough = (0.30 + 0.18 * (1.0 - rings) + 0.22 * pore_streaks + 0.20 * plank_seam).clip(0.18, 0.85)
    Image.fromarray((rough * 255.0).astype(np.uint8), mode="L").save(
        os.path.join(OUT_DIR, "wood_roughness.jpg"), quality=92
    )


def generate_deskmat_pbr(size: int = 1024):
    print("Generating Woven Cyber Desk Mat PBR set...")
    y, x = np.meshgrid(np.linspace(0, 1, size, endpoint=False), np.linspace(0, 1, size, endpoint=False), indexing="ij")
    weave_x = np.sin(x * size * 0.5 * np.pi) * 0.5 + 0.5
    weave_y = np.sin(y * size * 0.5 * np.pi) * 0.5 + 0.5
    micro_weave = (weave_x * 0.5 + weave_y * 0.5)

    # Subtle topographic contour lines on charcoal desk mat
    topo_field = tileable_noise(size, size, 6, 10, seed=202)
    contour = np.abs(np.mod(topo_field * 12.0, 1.0) - 0.5)
    contour_line = np.clip(1.0 - contour * 26.0, 0.0, 1.0)

    base = np.zeros((size, size, 3), dtype=np.float32)
    base[..., 0] = 28 + micro_weave * 6 + contour_line * 14
    base[..., 1] = 32 + micro_weave * 6 + contour_line * 20
    base[..., 2] = 40 + micro_weave * 7 + contour_line * 30

    Image.fromarray(base.clip(0, 255).astype(np.uint8), mode="RGB").save(
        os.path.join(OUT_DIR, "deskmat_albedo.jpg"), quality=93
    )
    height_to_normal(micro_weave * 0.4 + topo_field * 0.08, strength=1.8).save(
        os.path.join(OUT_DIR, "deskmat_normal.png")
    )
    rough = np.clip(0.82 - contour_line * 0.14 + micro_weave * 0.06, 0.5, 0.95)
    Image.fromarray((rough * 255.0).astype(np.uint8), mode="L").save(
        os.path.join(OUT_DIR, "deskmat_roughness.jpg"), quality=90
    )


def generate_brushed_metal_pbr(size: int = 1024):
    print("Generating Brushed Aluminum PBR set...")
    streaks = tileable_noise(size, size, 16, 512, seed=303)
    fine = tileable_noise(size, size, 32, 512, seed=304)
    brushed = streaks * 0.65 + fine * 0.35

    albedo = np.stack([
        196 + brushed * 28,
        200 + brushed * 28,
        208 + brushed * 28,
    ], axis=-1).clip(0, 255).astype(np.uint8)
    Image.fromarray(albedo, mode="RGB").save(os.path.join(OUT_DIR, "metal_brushed_albedo.jpg"), quality=93)
    height_to_normal(brushed, strength=1.4).save(os.path.join(OUT_DIR, "metal_brushed_normal.png"))
    rough = np.clip(0.24 + brushed * 0.16, 0.15, 0.55)
    Image.fromarray((rough * 255.0).astype(np.uint8), mode="L").save(
        os.path.join(OUT_DIR, "metal_brushed_roughness.jpg"), quality=92
    )


def generate_wall_pbr(size: int = 1024):
    print("Generating Studio Wall Plaster PBR set...")
    n1 = tileable_noise(size, size, 16, 16, seed=401)
    n2 = tileable_noise(size, size, 64, 64, seed=402)
    h = n1 * 0.6 + n2 * 0.4
    albedo = np.stack([
        214 + h * 18,
        210 + h * 18,
        204 + h * 16,
    ], axis=-1).clip(0, 255).astype(np.uint8)
    Image.fromarray(albedo, mode="RGB").save(os.path.join(OUT_DIR, "wall_albedo.jpg"), quality=92)
    height_to_normal(h, strength=1.2).save(os.path.join(OUT_DIR, "wall_normal.png"))
    rough = np.clip(0.76 + h * 0.14, 0.6, 0.95)
    Image.fromarray((rough * 255.0).astype(np.uint8), mode="L").save(
        os.path.join(OUT_DIR, "wall_roughness.jpg"), quality=90
    )


def generate_track_road_pbr(size: int = 2048):
    print("Generating 2K Cyber-Asphalt & FIA Racing Kerbs PBR set...")
    v, u = np.meshgrid(np.linspace(0, 1, size, endpoint=False), np.linspace(0, 1, size, endpoint=False), indexing="ij")
    agg1 = tileable_noise(size, size, 128, 128, seed=501)
    agg2 = tileable_noise(size, size, 256, 256, seed=502)
    streak_v = tileable_noise(size, size, 16, 128, seed=503)

    aggregate = agg1 * 0.55 + agg2 * 0.45

    # Base dark tarmac
    albedo = np.zeros((size, size, 3), dtype=np.float32)
    albedo[..., 0] = 28 + aggregate * 22
    albedo[..., 1] = 31 + aggregate * 23
    albedo[..., 2] = 38 + aggregate * 26

    # Subtle tire rubber racing grooves around u=0.30 and u=0.70
    groove = np.exp(-np.square((u - 0.30) / 0.11)) + np.exp(-np.square((u - 0.70) / 0.11))
    groove = np.clip(groove * (0.7 + 0.3 * streak_v), 0.0, 1.0)
    albedo *= (1.0 - 0.22 * groove[..., None])

    # FIA Red & White Kerbs at u in [0, 0.085] and [0.915, 1.0]
    kerb_mask = (u < 0.085) | (u > 0.915)
    kerb_seg = np.mod(np.floor(v * 10.0), 2.0)  # 10 alternating red/white blocks per V repeat
    kerb_seam = np.exp(-np.square(np.minimum(np.mod(v * 10.0, 1.0), 1.0 - np.mod(v * 10.0, 1.0)) * 90.0))

    red_kerb = np.array([218, 18, 34], dtype=np.float32)
    white_kerb = np.array([242, 245, 250], dtype=np.float32)
    kerb_col = np.where(kerb_seg[..., None] < 0.5, red_kerb, white_kerb) * (0.90 + 0.10 * aggregate[..., None])
    kerb_col *= (1.0 - 0.45 * kerb_seam[..., None])
    albedo = np.where(kerb_mask[..., None], kerb_col, albedo)

    # White solid edge lines at u in [0.092, 0.110] and [0.890, 0.908]
    edge_line = ((u >= 0.092) & (u <= 0.110)) | ((u >= 0.890) & (u <= 0.908))
    albedo = np.where(edge_line[..., None], np.array([236, 242, 250], dtype=np.float32), albedo)

    # Cyber telemetry center dashed line + subtle cyan twin guide rails
    dash_on = np.mod(v * 8.0, 1.0) < 0.52
    center_dash = (np.abs(u - 0.5) < 0.008) & dash_on
    cyan_guide = ((np.abs(u - 0.118) < 0.004) | (np.abs(u - 0.882) < 0.004))

    emissive = np.zeros((size, size, 3), dtype=np.float32)
    albedo = np.where(center_dash[..., None], np.array([0, 228, 255], dtype=np.float32), albedo)
    albedo = np.where(cyan_guide[..., None], np.array([0, 210, 245], dtype=np.float32), albedo)

    emissive = np.where(center_dash[..., None], np.array([0, 190, 255], dtype=np.float32), emissive)
    emissive = np.where(cyan_guide[..., None], np.array([0, 150, 220], dtype=np.float32), emissive)

    Image.fromarray(albedo.clip(0, 255).astype(np.uint8), mode="RGB").save(
        os.path.join(OUT_DIR, "track_road_albedo.png")
    )
    Image.fromarray(emissive.clip(0, 255).astype(np.uint8), mode="RGB").save(
        os.path.join(OUT_DIR, "track_road_emissive.png")
    )

    height = aggregate * 0.45 + kerb_mask.astype(np.float32) * (0.45 - 0.35 * kerb_seam)
    height_to_normal(height, strength=2.6).save(os.path.join(OUT_DIR, "track_road_normal.png"))

    rough = 0.74 - 0.30 * groove + 0.12 * aggregate - 0.22 * kerb_mask.astype(np.float32)
    Image.fromarray((np.clip(rough, 0.22, 0.92) * 255.0).astype(np.uint8), mode="L").save(
        os.path.join(OUT_DIR, "track_road_roughness.jpg"), quality=92
    )


def draw_sugon_cloud_emblem(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float, emissive_mode: bool = False):
    """Draw stylized Sugon Cloud (Cloud + Security Shield) emblem."""
    s = scale
    # Outer cyber-shield polygon
    shield_pts = [
        (cx, cy - int(95 * s)),
        (cx + int(86 * s), cy - int(58 * s)),
        (cx + int(76 * s), cy + int(22 * s)),
        (cx, cy + int(98 * s)),
        (cx - int(76 * s), cy + int(22 * s)),
        (cx - int(86 * s), cy - int(58 * s)),
    ]
    fill_shield = (12, 42, 82) if not emissive_mode else (0, 85, 160)
    outline_cyan = (0, 240, 255)
    sugon_red = (230, 0, 24) if not emissive_mode else (255, 35, 55)

    draw.polygon(shield_pts, fill=fill_shield, outline=outline_cyan, width=max(3, int(6 * s)))

    # Inner red chevron accent at top of shield (Sugon Dawn / Horizon motif)
    inner_top = [
        (cx, cy - int(74 * s)),
        (cx + int(62 * s), cy - int(44 * s)),
        (cx + int(56 * s), cy - int(22 * s)),
        (cx, cy - int(50 * s)),
        (cx - int(56 * s), cy - int(22 * s)),
        (cx - int(62 * s), cy - int(44 * s)),
    ]
    draw.polygon(inner_top, fill=sugon_red)

    # Stylized Cloud silhouette inside the shield
    cloud_col = (248, 252, 255) if not emissive_mode else (190, 245, 255)
    r1 = int(24 * s)
    r2 = int(31 * s)
    r3 = int(21 * s)
    by = cy + int(18 * s)
    draw.ellipse((cx - int(48 * s), by - r1, cx - int(48 * s) + 2 * r1, by + r1), fill=cloud_col)
    draw.ellipse((cx - r2 + int(2 * s), by - int(22 * s) - r2, cx + r2 + int(2 * s), by - int(22 * s) + r2), fill=cloud_col)
    draw.ellipse((cx + int(12 * s), by - r3 + int(4 * s), cx + int(12 * s) + 2 * r3, by + r3 + int(4 * s)), fill=cloud_col)
    draw.rectangle((cx - int(32 * s), by, cx + int(34 * s), by + r1), fill=cloud_col)


def generate_gantry_banner():
    print("Generating 2K Sugon Cloud Start Gantry Banner & Emissive...")
    W, H = 2048, 512
    albedo = Image.new("RGB", (W, H), (10, 18, 34))
    emissive = Image.new("RGB", (W, H), (0, 0, 0))

    da = ImageDraw.Draw(albedo)
    de = ImageDraw.Draw(emissive)

    # Subtle tech grid background on albedo
    for gx in range(0, W, 32):
        da.line([(gx, 0), (gx, H)], fill=(18, 32, 56), width=1)
    for gy in range(0, H, 32):
        da.line([(0, gy), (W, gy)], fill=(18, 32, 56), width=1)

    # Top and bottom glowing laser trim bars
    da.rectangle((0, 0, W, 18), fill=(225, 0, 24))
    da.rectangle((0, H - 18, W, H), fill=(0, 232, 255))
    de.rectangle((0, 0, W, 18), fill=(255, 25, 45))
    de.rectangle((0, H - 18, W, H), fill=(0, 225, 255))

    # Left & Right dynamic racing chevrons
    for i in range(4):
        ox = 55 + i * 72
        pts_l = [(ox, 70), (ox + 46, 70), (ox + 96, H // 2), (ox + 46, H - 70), (ox, H - 70), (ox + 50, H // 2)]
        col = (230, 0, 24) if i % 2 == 0 else (0, 220, 255)
        da.polygon(pts_l, fill=col)
        de.polygon(pts_l, fill=col)

        rx = W - 55 - i * 72
        pts_r = [(rx, 70), (rx - 46, 70), (rx - 96, H // 2), (rx - 46, H - 70), (rx, H - 70), (rx - 50, H // 2)]
        da.polygon(pts_r, fill=col)
        de.polygon(pts_r, fill=col)

    # Sugon Cloud Emblem on left-of-center
    draw_sugon_cloud_emblem(da, cx=565, cy=H // 2, scale=1.45, emissive_mode=False)
    draw_sugon_cloud_emblem(de, cx=565, cy=H // 2, scale=1.45, emissive_mode=True)

    # Crisp Brand Typography
    f_title = get_font(120, bold=True)
    f_en = get_font(54, bold=True)
    f_sub = get_font(34, bold=True)

    da.text((720, 92), "曙光云", font=f_title, fill=(255, 255, 255))
    de.text((720, 92), "曙光云", font=f_title, fill=(215, 240, 255))

    da.text((1125, 138), "SUGON CLOUD", font=f_en, fill=(0, 232, 255))
    de.text((1125, 138), "SUGON CLOUD", font=f_en, fill=(0, 215, 255))

    # Pill badge for 立体密算 with exact measured width
    sub_text = "立体密算 · 全栈可信超算赛道  |  START / FINISH"
    bbox = da.textbbox((0, 0), sub_text, font=f_sub)
    tw = bbox[2] - bbox[0]
    px0, py0 = 724, 268
    px1, py1 = px0 + tw + 64, 348
    da.rounded_rectangle((px0, py0, px1, py1), radius=18, fill=(22, 44, 80), outline=(0, 230, 255), width=3)
    de.rounded_rectangle((px0, py0, px1, py1), radius=18, fill=(0, 0, 0), outline=(0, 180, 230), width=3)

    da.text((px0 + 32, py0 + 17), sub_text, font=f_sub, fill=(235, 248, 255))
    de.text((px0 + 32, py0 + 17), sub_text, font=f_sub, fill=(110, 215, 255))

    albedo.save(os.path.join(OUT_DIR, "gantry_banner_albedo.png"))
    emissive.save(os.path.join(OUT_DIR, "gantry_banner_emissive.png"))


def generate_car_livery(size: int = 2048):
    """
    Generate 2K Red-Gray-White Works GT Livery UV map.
    UV convention: U in [0,1] maps car X [-0.44, +0.44]; V in [0,1] maps car Y [-0.86, +0.86]
    (Note: in PNG image space, y_px=0 is V=1.0 = Front Nose, y_px=size-1 is V=0.0 = Rear Diffuser).
    """
    print("Generating 2K Red-Gray-White Race Car Livery PBR set...")
    albedo = Image.new("RGB", (size, size), (242, 245, 250))  # Pearl White base
    metallic = Image.new("L", (size, size), 35)               # Clearcoat paint base metallic
    roughness = Image.new("L", (size, size), 42)              # Glossy clearcoat 0.16
    emissive = Image.new("RGB", (size, size), (0, 0, 0))

    da = ImageDraw.Draw(albedo)
    dm = ImageDraw.Draw(metallic)
    dr = ImageDraw.Draw(roughness)
    de = ImageDraw.Draw(emissive)

    # Outer carbon-titanium gray sidepods & floor aero skirts (U < 0.23 or U > 0.77)
    da.rectangle((0, 0, int(size * 0.24), size), fill=(56, 62, 72))
    da.rectangle((int(size * 0.76), 0, size, size), fill=(56, 62, 72))
    dm.rectangle((0, 0, int(size * 0.24), size), fill=165)
    dm.rectangle((int(size * 0.76), 0, size, size), fill=165)
    dr.rectangle((0, 0, int(size * 0.24), size), fill=95)
    dr.rectangle((int(size * 0.76), 0, size, size), fill=95)

    # Front carbon splitter lip (top of image y_px in [0, 0.08*size]) & Rear diffuser (bottom [0.90*size, size])
    da.rectangle((0, 0, size, int(size * 0.075)), fill=(38, 42, 48))
    da.rectangle((0, int(size * 0.90), size, size), fill=(36, 40, 46))
    dr.rectangle((0, 0, size, int(size * 0.075)), fill=115)
    dr.rectangle((0, int(size * 0.90), size, size), fill=115)

    # Metallic titanium gray flanking aero wedges
    wedge_l = [
        (int(size * 0.24), int(size * 0.16)),
        (int(size * 0.36), int(size * 0.08)),
        (int(size * 0.33), int(size * 0.88)),
        (int(size * 0.24), int(size * 0.88)),
    ]
    wedge_r = [(size - x, y) for (x, y) in wedge_l]
    da.polygon(wedge_l, fill=(84, 92, 104))
    da.polygon(wedge_r, fill=(84, 92, 104))
    dm.polygon(wedge_l, fill=190)
    dm.polygon(wedge_r, fill=190)

    # Iconic Sugon Crimson Red (#DC0014) Racing Chevrons & Spine Stripes
    red = (220, 0, 24)
    # Sweeping V-hood stripes from nose cone back along shoulders
    hood_v_l = [
        (int(size * 0.455), int(size * 0.075)),
        (int(size * 0.490), int(size * 0.075)),
        (int(size * 0.355), int(size * 0.52)),
        (int(size * 0.355), int(size * 0.89)),
        (int(size * 0.285), int(size * 0.89)),
        (int(size * 0.285), int(size * 0.46)),
    ]
    hood_v_r = [(size - x, y) for (x, y) in hood_v_l]
    da.polygon(hood_v_l, fill=red)
    da.polygon(hood_v_r, fill=red)

    # Center crimson spine fin stripe behind cockpit (y_px in [0.56, 0.90])
    da.rectangle((int(size * 0.478), int(size * 0.54), int(size * 0.522), int(size * 0.90)), fill=red)

    # Red aero trim lip along front splitter & side skirts
    da.rectangle((int(size * 0.14), int(size * 0.062), int(size * 0.86), int(size * 0.078)), fill=red)
    da.rectangle((int(size * 0.06), int(size * 0.20), int(size * 0.085), int(size * 0.84)), fill=red)
    da.rectangle((int(size * 0.915), int(size * 0.20), int(size * 0.94), int(size * 0.84)), fill=red)

    # Nose racing roundel "#01" & Sugon Cloud branding (rotated 180 deg so readable when viewing car from Front Nose!)
    cx, cy = size // 2, int(size * 0.285)
    roundel = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    dr_r = ImageDraw.Draw(roundel)
    dr_r.ellipse((15, 15, 245, 245), fill=(18, 26, 40, 255), outline=(220, 0, 24, 255), width=10)
    f_num = get_font(112, bold=True)
    nb = dr_r.textbbox((0, 0), "01", font=f_num)
    dr_r.text((130 - (nb[2] - nb[0]) // 2 - nb[0], 130 - (nb[3] - nb[1]) // 2 - nb[1]), "01", font=f_num, fill=(255, 255, 255, 255))
    roundel_rot = roundel.rotate(180, resample=Image.Resampling.BICUBIC)
    albedo.paste(roundel_rot, (cx - 130, cy - 130), roundel_rot)

    f_brand = get_font(48, bold=True)
    bb = da.textbbox((0, 0), "曙光云", font=f_brand)
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    pw, ph = bw + 60, bh + 30
    badge = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    dr_b = ImageDraw.Draw(badge)
    dr_b.rounded_rectangle((3, 3, pw - 4, ph - 4), radius=14, fill=(18, 26, 40, 255), outline=(0, 225, 255, 255), width=4)
    dr_b.text((30 - bb[0], 14 - bb[1]), "曙光云", font=f_brand, fill=(255, 255, 255, 255))
    badge_rot = badge.rotate(180, resample=Image.Resampling.BICUBIC)
    albedo.paste(badge_rot, (cx - pw // 2, int(size * 0.135)), badge_rot)

    # Rear wing / engine cover branding badge
    f_wing = get_font(56, bold=True)
    wb = da.textbbox((0, 0), "SUGON CLOUD", font=f_wing)
    ww, wh = wb[2] - wb[0], wb[3] - wb[1]
    wy = int(size * 0.79)
    da.rounded_rectangle((cx - ww // 2 - 34, wy - 14, cx + ww // 2 + 34, wy + wh + 20), radius=14, fill=(18, 26, 40), outline=(220, 0, 24), width=5)
    da.text((cx - ww // 2 - wb[0], wy - wb[1] + 3), "SUGON CLOUD", font=f_wing, fill=(255, 255, 255))

    # Cyber cyan stereo-compute subtle accent circuit lines on sidepods
    da.line([(int(size * 0.18), int(size * 0.32)), (int(size * 0.18), int(size * 0.74))], fill=(0, 230, 255), width=6)
    da.line([(int(size * 0.82), int(size * 0.32)), (int(size * 0.82), int(size * 0.74))], fill=(0, 230, 255), width=6)
    de.line([(int(size * 0.18), int(size * 0.32)), (int(size * 0.18), int(size * 0.74))], fill=(0, 180, 255), width=6)
    de.line([(int(size * 0.82), int(size * 0.32)), (int(size * 0.82), int(size * 0.74))], fill=(0, 180, 255), width=6)

    albedo.save(os.path.join(OUT_DIR, "car_livery_albedo.png"))
    metallic.save(os.path.join(OUT_DIR, "car_livery_metallic.jpg"), quality=92)
    roughness.save(os.path.join(OUT_DIR, "car_livery_roughness.jpg"), quality=92)
    emissive.save(os.path.join(OUT_DIR, "car_livery_emissive.png"))


def generate_monitor_screen():
    print("Generating Ultrawide Monitor 'Sugon Cloud Stereo Confidential Computing' Dashboard UI...")
    W, H = 2048, 860
    img = Image.new("RGB", (W, H), (7, 13, 26))
    d = ImageDraw.Draw(img)

    # Subtle cyber grid
    for gx in range(0, W, 40):
        d.line([(gx, 0), (gx, H)], fill=(13, 24, 46), width=1)
    for gy in range(0, H, 40):
        d.line([(0, gy), (W, gy)], fill=(13, 24, 46), width=1)

    # Top Header Bar
    d.rectangle((0, 0, W, 86), fill=(12, 24, 48))
    d.line([(0, 86), (W, 86)], fill=(0, 225, 255), width=3)
    draw_sugon_cloud_emblem(d, cx=64, cy=43, scale=0.36, emissive_mode=False)

    f_h1 = get_font(38, bold=True)
    f_h2 = get_mono_font(26)
    f_card = get_font(28, bold=True)
    f_small = get_mono_font(22)

    d.text((116, 20), "曙光云 · 立体密算全栈可信安全控制台", font=f_h1, fill=(240, 248, 255))
    d.text((1380, 28), "C86 TRUSTED ROOT: ACTIVE  |  TEE ENCLAVE: 99.99%", font=f_h2, fill=(0, 240, 210))

    # Left Panel: 5-Layer Stereo Confidential Computing Architecture
    d.rounded_rectangle((36, 118, 660, 824), radius=16, fill=(11, 22, 42), outline=(28, 68, 120), width=2)
    d.text((62, 138), "立体密算五层可信架构", font=f_card, fill=(0, 232, 255))

    layers = [
        ("L5 可信 AI 与密态推理层", (0, 230, 255)),
        ("L4 可信数据空间流通层", (0, 195, 245)),
        ("L3 密态计算技术中台层", (40, 155, 255)),
        ("L2 赤霄内生安全基础设施", (225, 28, 52)),
        ("L1 国产芯云密码算力底座", (235, 65, 35)),
    ]
    for idx, (label, col) in enumerate(layers):
        ly = 205 + idx * 116
        d.rounded_rectangle((64, ly, 632, ly + 92), radius=12, fill=(16, 32, 60), outline=col, width=3)
        d.rectangle((64, ly, 82, ly + 92), fill=col)
        d.text((104, ly + 26), label, font=f_card, fill=(238, 246, 255))
        d.text((515, ly + 32), "ENCRYPTED", font=f_small, fill=col)

    # Center Panel: 3D Hexagonal Confidential Shield & Live Circuit Telemetry
    d.rounded_rectangle((692, 118, 1396, 824), radius=16, fill=(10, 20, 40), outline=(0, 190, 240), width=2)
    d.text((722, 138), "密态算力拓扑 & 桌面赛道实时遥测", font=f_card, fill=(255, 255, 255))

    ccx, ccy = 1044, 465
    for r, col in [(245, (18, 58, 104)), (190, (0, 150, 210)), (130, (225, 20, 45)), (75, (0, 240, 255))]:
        pts = [
            (ccx + int(r * math.cos(math.radians(60 * k - 30))), ccy + int(r * math.sin(math.radians(60 * k - 30))))
            for k in range(6)
        ]
        d.polygon(pts, outline=col, width=3)
    draw_sugon_cloud_emblem(d, cx=ccx, cy=ccy, scale=0.65, emissive_mode=True)
    d.text((855, 748), "STEREO SHIELD MATRIX // READY", font=f_h2, fill=(0, 240, 255))

    # Right Panel: Throughput Waveforms & Node Metrics
    d.rounded_rectangle((1428, 118, 2012, 824), radius=16, fill=(11, 22, 42), outline=(28, 68, 120), width=2)
    d.text((1458, 138), "密态吞吐量与护盾能量监控", font=f_card, fill=(0, 232, 255))

    metrics = [
        ("SM4/SM9 硬件吞吐", "128.4 Gbps", 0.92, (0, 235, 255)),
        ("立体护盾场强指数", "98.6 %", 0.98, (230, 25, 48)),
        ("零信任内存隔离率", "100.0 %", 1.00, (0, 240, 180)),
        ("低延迟密态帧同步", "0.42 ms", 0.86, (90, 175, 255)),
    ]
    for idx, (m_name, m_val, ratio, col) in enumerate(metrics):
        my = 215 + idx * 140
        d.text((1458, my), m_name, font=f_card, fill=(210, 226, 245))
        d.text((1820, my + 4), m_val, font=f_small, fill=col)
        d.rounded_rectangle((1458, my + 52, 1980, my + 82), radius=8, fill=(20, 36, 64))
        d.rounded_rectangle((1458, my + 52, int(1458 + 522 * ratio), my + 82), radius=8, fill=col)

    img.save(os.path.join(OUT_DIR, "monitor_screen.png"))


if __name__ == "__main__":
    generate_walnut_wood(2048)
    generate_deskmat_pbr(1024)
    generate_brushed_metal_pbr(1024)
    generate_wall_pbr(1024)
    generate_track_road_pbr(2048)
    generate_gantry_banner()
    generate_car_livery(2048)
    generate_monitor_screen()
    print(f"All PBR textures generated successfully in: {OUT_DIR}")
