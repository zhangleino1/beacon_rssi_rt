"""
为 3:4 与 4:3 海报图添加高清标题与图例排版（支持中文微软雅黑粗体）
"""

from pathlib import Path
import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont


FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
NVIDIA_GREEN = (118, 185, 0)


def draw_centered_text(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill, canvas_w: int, shadow=None):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (canvas_w - tw) // 2
    if shadow is not None:
        draw.text((x + 2, y + 3), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def build_colorbar_strip(width: int, height: int, cmap_name: str = "viridis") -> Image.Image:
    cmap = matplotlib.colormaps.get_cmap(cmap_name)
    xs = np.linspace(0.0, 1.0, width)[None, :]
    rgba = (cmap(np.repeat(xs, height, axis=0)) * 255).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def annotate_3_4(raw_path: Path, out_path: Path):
    base = Image.open(raw_path).convert("RGBA")
    w, h = base.size  # 1200 x 1600

    # 将透明背景的 3D 渲染图缩放至 90% 并下移，给顶部标题与底部色标留出充裕白底空间
    canvas = Image.new("RGBA", (w, h), (248, 250, 252, 255))
    scaled_w, scaled_h = int(w * 0.90), int(h * 0.90)
    base_scaled = base.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
    canvas.alpha_composite(base_scaled, ((w - scaled_w) // 2, 135))

    draw = ImageDraw.Draw(canvas)
    f_badge = ImageFont.truetype(FONT_BOLD, 24)
    f_title = ImageFont.truetype(FONT_BOLD, 50)
    f_sub = ImageFont.truetype(FONT_BOLD, 30)
    f_foot = ImageFont.truetype(FONT_REG, 22)

    # 1. 顶部标签胶囊
    badge_text = "NVIDIA Sionna RT GUI · RTX 4070 室内实测"
    bb = draw.textbbox((0, 0), badge_text, font=f_badge)
    bw, bh = bb[2] - bb[0] + 38, bb[3] - bb[1] + 16
    bx0 = (w - bw) // 2
    draw.rounded_rectangle([bx0, 24, bx0 + bw, 24 + bh], radius=bh // 2, fill=(*NVIDIA_GREEN, 255))
    draw_centered_text(draw, 29, badge_text, f_badge, (255, 255, 255, 255), w)

    # 2. 主标题（两行居中）
    draw_centered_text(draw, 80, "用 NVIDIA Sionna RT GUI", f_title, (15, 23, 42, 255), w)
    draw_centered_text(draw, 142, "实时仿真室内蓝牙 Beacon 信号覆盖", f_title, (15, 23, 42, 255), w)

    # 3. 副标题（Wi-Fi / 蓝牙指纹定位）
    sub_text = "用于 Wi-Fi / 蓝牙指纹定位 · 2.4 GHz 覆盖热力图"
    sb = draw.textbbox((0, 0), sub_text, font=f_sub)
    sw, sh = sb[2] - sb[0] + 44, sb[3] - sb[1] + 16
    sx0 = (w - sw) // 2
    draw.rounded_rectangle(
        [sx0, 214, sx0 + sw, 214 + sh],
        radius=12,
        fill=(240, 249, 232, 255),
        outline=(118, 185, 0, 255),
        width=2,
    )
    draw_centered_text(draw, 219, sub_text, f_sub, (56, 98, 0, 255), w)

    # 4. 底部色标与图例栏
    draw.rectangle([0, h - 82, w, h], fill=(241, 245, 249, 250))
    draw.line([(48, h - 82), (w - 48, h - 82)], fill=(203, 213, 225, 255), width=2)
    draw.text((48, h - 55), "2.4 GHz 平面 RSS 热力图（穿墙/多径光线追踪）", font=f_foot, fill=(51, 65, 85, 255))

    bar_w, bar_h = 270, 20
    bar_x, bar_y = w - bar_w - 118, h - 51
    cbar = build_colorbar_strip(bar_w, bar_h, "viridis")
    canvas.paste(cbar, (bar_x, bar_y))
    draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline=(100, 116, 139, 255), width=1)
    draw.text((bar_x - 98, h - 55), "-78 dBm", font=f_foot, fill=(51, 65, 85, 255))
    draw.text((bar_x + bar_w + 12, h - 55), "-32 dBm", font=f_foot, fill=(51, 65, 85, 255))

    canvas.convert("RGB").save(out_path, quality=95)
    print(f"[OK] 3:4 海报已更新: {out_path}")


def annotate_4_3(raw_path: Path, out_path: Path):
    base = Image.open(raw_path).convert("RGBA")
    w, h = base.size  # 1600 x 1200

    # 顶部暗色半透明渐变遮罩，确保白色文字高对比度且不遮挡中部信号射线
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    grad_h = 235
    for y in range(grad_h):
        alpha = int(228 * ((1.0 - y / grad_h) ** 1.35))
        odraw.line([(0, y), (w, y)], fill=(12, 17, 26, alpha))

    # 底部右侧微遮罩（放置图例）
    odraw.rounded_rectangle([w - 670, h - 62, w - 24, h - 18], radius=12, fill=(12, 17, 26, 195))

    canvas = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(canvas)

    f_badge = ImageFont.truetype(FONT_BOLD, 24)
    f_title = ImageFont.truetype(FONT_BOLD, 48)
    f_sub = ImageFont.truetype(FONT_BOLD, 30)
    f_leg = ImageFont.truetype(FONT_REG, 22)

    # 1. 顶部标签胶囊
    badge_text = "2.4 GHz 多径射线追踪 · 室内穿墙仿真"
    bb = draw.textbbox((0, 0), badge_text, font=f_badge)
    bw, bh = bb[2] - bb[0] + 36, bb[3] - bb[1] + 14
    bx0 = (w - bw) // 2
    draw.rounded_rectangle([bx0, 18, bx0 + bw, 18 + bh], radius=bh // 2, fill=(*NVIDIA_GREEN, 255))
    draw_centered_text(draw, 22, badge_text, f_badge, (255, 255, 255, 255), w)

    # 2. 主标题
    draw_centered_text(
        draw,
        72,
        "用 NVIDIA Sionna RT GUI 实时仿真室内蓝牙 Beacon 信号覆盖",
        f_title,
        (255, 255, 255, 255),
        w,
        shadow=(0, 0, 0, 210),
    )

    # 3. 副标题
    draw_centered_text(
        draw,
        136,
        "用于 Wi-Fi / 蓝牙指纹定位 · 视距直达 / 镜面反射 / 穿墙透射",
        f_sub,
        (163, 230, 53, 255),
        w,
        shadow=(0, 0, 0, 210),
    )

    # 4. 右下角图例
    lx = w - 648
    ly = h - 49
    draw.ellipse([lx, ly + 4, lx + 18, ly + 22], fill=(239, 68, 68, 255))
    draw.text((lx + 26, ly), "BLE 信标 (Tx)", font=f_leg, fill=(241, 245, 249, 255))
    draw.ellipse([lx + 195, ly + 4, lx + 213, ly + 22], fill=(134, 239, 172, 255))
    draw.text((lx + 221, ly), "接收端 (Rx)", font=f_leg, fill=(241, 245, 249, 255))
    draw.line([(lx + 365, ly + 13), (lx + 402, ly + 13)], fill=(226, 232, 240, 255), width=4)
    draw.text((lx + 412, ly), "3D 多径传播 + 热力图", font=f_leg, fill=(241, 245, 249, 255))

    canvas.convert("RGB").save(out_path, quality=95)
    print(f"[OK] 4:3 海报已更新: {out_path}")


if __name__ == "__main__":
    out_dir = Path(__file__).parent / "output"
    raw_dir = out_dir / "raw_posters"
    annotate_3_4(raw_dir / "poster_3_4_radiomap.png", out_dir / "poster_3_4_radiomap.png")
    annotate_4_3(raw_dir / "poster_4_3_propagation.png", out_dir / "poster_4_3_propagation.png")
