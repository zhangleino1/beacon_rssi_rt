"""
生成两张高质量海报图（3:4 竖版聚焦热力图，4:3 横版聚焦多径信号传播+热力图）
输出至 output/poster_3_4_radiomap.png 与 output/poster_4_3_propagation.png
"""

import math
from pathlib import Path
from PIL import Image
import polyscope as ps

from sionna_rt_gui import AppHolder
from sionna_rt_gui.config import GuiMode, load_config


def set_camera_orbit(center, radius, az_deg, el_deg):
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    cx, cy, cz = center
    eye = [
        cx + radius * math.cos(el) * math.cos(az),
        cy + radius * math.cos(el) * math.sin(az),
        cz + radius * math.sin(el),
    ]
    ps.look_at(eye, [cx, cy, cz])


def capture_poster(
    width: int,
    height: int,
    out_path: Path,
    camera_center,
    camera_radius: float,
    az_deg: float,
    el_deg: float,
    with_paths: bool,
    color_map: str = "plasma",
    vmin: float = -78.0,
    vmax: float = -32.0,
    rm_max_depth: int = 5,
    paths_max_depth: int = 3,
    target_upscale: tuple[int, int] | None = None,
):
    project_dir = Path(__file__).parent
    cfg = load_config(
        str(project_dir / "configs" / "ble_indoor.yaml"),
        scene_filename=str(project_dir / "scenes" / "apartment.xml"),
    )
    cfg.gui_mode = GuiMode.HIDDEN
    cfg.rendering.default_resolution = (width, height)
    cfg.rendering.spp_per_frame = 8
    cfg.rendering.max_accumulated_spp = 128
    cfg.radio_map.center = (0.0, 0.0, 1.0)
    cfg.radio_map.color_map = color_map
    cfg.radio_map.vmin = vmin
    cfg.radio_map.vmax = vmax
    cfg.radio_map.max_depth = rm_max_depth
    cfg.radio_map.log_samples_per_it = 7.2
    cfg.radio_map.accumulate_max_samples_per_tx = int(8e7)
    cfg.paths.max_depth = paths_max_depth
    cfg.use_vsync = False

    holder = AppHolder(
        cfg,
        scene_filename=str(project_dir / "scenes" / "apartment.xml"),
        overrides={"use_live_reload": False},
    )
    gui = holder.app

    # 放置客厅 BLE Beacon
    gui.add_radio_device([-0.1, -3.2, 1.35], is_transmitter=True)
    if with_paths:
        gui.add_radio_device([0.2, 2.8, 1.0], is_transmitter=False)
        gui.add_radio_device([2.9, -2.0, 1.0], is_transmitter=False)
        gui.add_radio_device([-3.2, 1.2, 1.0], is_transmitter=False)

    # 调整设备球体尺寸使其更精致，不遮挡热力图与射线
    for rd_name, rad in (("Transmitters", 0.28), ("Receivers", 0.22)):
        if ps.has_point_cloud(rd_name):
            ps.get_point_cloud(rd_name).set_radius(rad, relative=False)

    gui.set_radio_map(gui.compute_radio_map(), show=True)
    if with_paths:
        gui.update_paths(show=True)
        if ps.has_curve_network("paths"):
            ps.get_curve_network("paths").set_radius(0.035, relative=False)

    set_camera_orbit(camera_center, camera_radius, az_deg, el_deg)

    # 累积多帧以获得高采样低噪点的清晰画面
    for _ in range(18):
        ps.frame_tick()

    buf = ps.screenshot_to_buffer(transparent_bg=False, vertical_flip=True, include_UI=True)
    img = Image.fromarray(buf[:, :, :3], mode="RGB")
    if target_upscale is not None and img.size != target_upscale:
        img = img.resize(target_upscale, Image.Resampling.LANCZOS)
    img.save(out_path, quality=95)
    print(f"[OK] 海报已保存: {out_path} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 3:4 竖版海报：突出 2.4GHz 平面热力图与穿墙衰减梯度 (plasma 色谱)
    capture_poster(
        width=750,
        height=1000,
        out_path=out_dir / "poster_3_4_radiomap.png",
        camera_center=(-0.2, 0.0, 0.35),
        camera_radius=14.4,
        az_deg=-78.0,
        el_deg=60.0,
        with_paths=False,
        color_map="plasma",
        vmin=-82.0,
        vmax=-32.0,
        target_upscale=(1200, 1600),
    )

    # 2. 4:3 横版海报：突出多房间三维信号传播路径 + 细线射线与热力图叠加
    capture_poster(
        width=1360,
        height=1020,
        out_path=out_dir / "poster_4_3_propagation.png",
        camera_center=(-0.15, 0.05, 0.50),
        camera_radius=11.4,
        az_deg=-44.0,
        el_deg=52.0,
        with_paths=True,
        color_map="viridis",
        vmin=-85.0,
        vmax=-35.0,
        paths_max_depth=3,
        target_upscale=(1600, 1200),
    )
