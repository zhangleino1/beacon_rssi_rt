"""
Audio-First 全自动操作 Sionna RT GUI 录屏与音画合成脚本

流程：
1. 读取 output/audio/timeline_map.json（由 video_tts_toolkit 预先测算的精确音频时间轴）
2. 启动真实汉化版 Sionna RT GUI (AppHolder + Polyscope + Mitsuba CUDA/OptiX)
3. 按各幕精确时间戳自动操作 GUI：运镜、添加 BLE Tx/Rx、计算平面热力图、显示多径、选中设备、开启轨迹动画
4. 通过 Polyscope framebuffer (screenshot_to_buffer, include_UI=True) 实时推流到 FFmpeg 编码无声视频
5. 根据 timeline_map.json 生成 ASS 中文字幕，使用 FFmpeg 将视频 + master_voiceover.mp3（响度标准化）+ 字幕合成成品 MP4
6. 同步导出 4 张高清配图到 docs/images/ 供公众号长文排版使用
"""

import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
import polyscope as ps

from sionna_rt_gui import AppHolder
from sionna_rt_gui.animation import LoopingMode
from sionna_rt_gui.config import RenderingMode, load_config
from sionna_rt_gui.selection import SelectionType


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * smoothstep(t)


def set_camera_orbit(center: tuple[float, float, float], radius: float, az_deg: float, el_deg: float):
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    cx, cy, cz = center
    eye = [
        cx + radius * math.cos(el) * math.cos(az),
        cy + radius * math.cos(el) * math.sin(az),
        cz + radius * math.sin(el),
    ]
    ps.look_at(eye, [cx, cy, cz])


def format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def wrap_subtitle_lines(text: str, max_chars: int = 28) -> str:
    if len(text) <= max_chars:
        return text
    mid = len(text) // 2
    best_split = mid
    for offset in range(0, 8):
        for idx in (mid - offset, mid + offset):
            if 0 < idx < len(text) and text[idx] in "，。、：；！ ":
                best_split = idx + 1
                return text[:best_split].strip() + r"\N" + text[best_split:].strip()
    return text[:mid].strip() + r"\N" + text[mid:].strip()


def write_ass_subtitles(timeline: dict, ass_path: Path):
    header = """[Script Info]
Title: Sionna RT GUI Indoor BLE Demo
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,46,&H00FFFFFF,&H000000FF,&H00121418,&H90000000,-1,0,0,0,100,100,1,0,1,3.2,1.2,2,80,80,52,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header.strip()]
    for sc in timeline["scenes"]:
        t0 = format_ass_time(sc["startTime"])
        t1 = format_ass_time(sc["endTime"])
        sub_text = wrap_subtitle_lines(sc.get("subtitle", sc["text"]))
        lines.append(f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,{sub_text}")
    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_rgba_png(buf: np.ndarray, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(buf[:, :, :3], mode="RGB").save(out_path)


def main():
    project_dir = Path(__file__).parent
    timeline_path = project_dir / "output" / "audio" / "timeline_map.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    scenes_by_id = {s["id"]: s for s in timeline["scenes"]}
    total_duration = float(timeline["totalDuration"])
    fps = 24
    total_frames = int(math.ceil(total_duration * fps))

    raw_video_path = project_dir / "output" / "raw_gui_capture.mp4"
    ass_path = project_dir / "output" / "subtitles.ass"
    final_video_path = project_dir / "output" / "sionna_rt_gui_ble_demo.mp4"
    docs_img_dir = project_dir / "docs" / "images"
    docs_img_dir.mkdir(parents=True, exist_ok=True)

    write_ass_subtitles(timeline, ass_path)

    # 加载并优化 GUI 启动配置（1600x900 无标题栏裁切，平滑帧率）
    cfg = load_config(
        str(project_dir / "configs" / "ble_indoor.yaml"),
        scene_filename=str(project_dir / "scenes" / "apartment.xml"),
    )
    win_w, win_h = 1600, 900
    cfg.rendering.default_resolution = (win_w, win_h)
    cfg.rendering.spp_per_frame = 4
    cfg.rendering.max_accumulated_spp = 64
    cfg.radio_map.log_samples_per_it = 6.3
    cfg.radio_map.accumulate_max_samples_per_tx = int(5e7)
    cfg.use_vsync = False

    holder = AppHolder(
        cfg,
        scene_filename=str(project_dir / "scenes" / "apartment.xml"),
        overrides={"use_live_reload": False},
    )
    gui = holder.app

    # 验证首帧缓冲尺寸
    ps.frame_tick()
    first_buf = ps.screenshot_to_buffer(transparent_bg=False, vertical_flip=True, include_UI=True)
    bh, bw = first_buf.shape[:2]
    print(f"[INFO] 录屏分辨率: {bw}x{bh} @ {fps}fps, 总时长: {total_duration:.2f}s ({total_frames} 帧)")

    # 启动 FFmpeg 接收原始 RGBA 帧编码为无损/高质量中间视频
    ffmpeg_raw_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgba",
        "-s", f"{bw}x{bh}",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "16",
        "-pix_fmt", "yuv420p",
        str(raw_video_path),
    ]
    proc = subprocess.Popen(ffmpeg_raw_cmd, stdin=subprocess.PIPE)

    # 各幕起止时间戳
    t_s1_end = scenes_by_id["scene_01_intro"]["endTime"]
    t_s2_start = scenes_by_id["scene_02_scene_materials"]["startTime"]
    t_s2_end = scenes_by_id["scene_02_scene_materials"]["endTime"]
    t_s3_start = scenes_by_id["scene_03_radiomap"]["startTime"]
    t_s3_end = scenes_by_id["scene_03_radiomap"]["endTime"]
    t_s4_start = scenes_by_id["scene_04_multipath"]["startTime"]
    t_s4_end = scenes_by_id["scene_04_multipath"]["endTime"]
    t_s5_start = scenes_by_id["scene_05_dynamic_motion"]["startTime"]
    t_s5_end = scenes_by_id["scene_05_dynamic_motion"]["endTime"]
    t_s6_start = scenes_by_id["scene_06_da3_outro"]["startTime"]

    # 状态触发标志（确保每个交互动作精确执行一次）
    state = {
        "switched_raster": False,
        "switched_raytrace": False,
        "added_tx0": False,
        "computed_rm": False,
        "added_rx0": False,
        "added_rx1": False,
        "added_rx2": False,
        "selected_rx0": False,
        "started_traj": False,
        "cleared_sel": False,
        "saved_img1": False,
        "saved_img2": False,
        "saved_img3": False,
        "saved_img4": False,
    }

    try:
        for frame_idx in range(total_frames):
            t = frame_idx / fps

            # -------------------------------------------------------------
            # 1. 运镜与各幕 GUI 交互编排（Audio-First 精确对齐）
            # -------------------------------------------------------------
            if t < t_s2_start:
                # Scene 01: 全景俯瞰并环绕展示汉化面板与 1:1 公寓
                u = t / max(t_s2_start, 1e-3)
                set_camera_orbit(
                    center=(-0.2, 0.0, 0.5),
                    radius=lerp(13.0, 11.2, u),
                    az_deg=lerp(-78.0, -38.0, u),
                    el_deg=lerp(50.0, 56.0, u),
                )
            elif t < t_s3_start:
                # Scene 02: 近景扫描功能区，并中途演示光栅化+剖切平面切换
                u = (t - t_s2_start) / max(t_s3_start - t_s2_start, 1e-3)
                set_camera_orbit(
                    center=(lerp(-0.2, 0.0, u), lerp(0.0, 0.3, u), 0.7),
                    radius=lerp(11.2, 8.6, u),
                    az_deg=lerp(-38.0, 22.0, u),
                    el_deg=lerp(56.0, 44.0, u),
                )
                if t >= t_s2_start + 9.0 and not state["switched_raster"]:
                    gui.set_rendering_mode(RenderingMode.RASTERIZATION)
                    gui.set_slice_plane_active(True)
                    state["switched_raster"] = True
                if t >= t_s2_start + 13.5 and not state["switched_raytrace"]:
                    gui.set_slice_plane_active(False)
                    gui.set_rendering_mode(RenderingMode.RAY_TRACING)
                    state["switched_raytrace"] = True

            elif t < t_s4_start:
                # Scene 03: 拉升视角，放置客厅 BLE 信标并开启全屋热力图
                u = (t - t_s3_start) / max(t_s4_start - t_s3_start, 1e-3)
                set_camera_orbit(
                    center=(-0.15, 0.0, 0.5),
                    radius=lerp(8.6, 11.8, min(u * 1.4, 1.0)),
                    az_deg=lerp(22.0, -52.0, u),
                    el_deg=lerp(44.0, 62.0, u),
                )
                if t >= t_s3_start + 1.4 and not state["added_tx0"]:
                    gui.add_radio_device([-0.1, -3.4, 1.4], is_transmitter=True)
                    state["added_tx0"] = True
                if t >= t_s3_start + 3.0 and not state["computed_rm"]:
                    gui.set_radio_map(gui.compute_radio_map(), show=True)
                    state["computed_rm"] = True

            elif t < t_s5_start:
                # Scene 04: 分别在卧室、厨房、卫浴间放置 3 个接收端，展示多径射线
                u = (t - t_s4_start) / max(t_s5_start - t_s4_start, 1e-3)
                set_camera_orbit(
                    center=(-0.15, 0.0, 0.6),
                    radius=lerp(11.8, 10.6, u),
                    az_deg=lerp(-52.0, -18.0, u),
                    el_deg=lerp(62.0, 48.0, u),
                )
                if t >= t_s4_start + 1.2 and not state["added_rx0"]:
                    gui.add_radio_device([0.2, 2.8, 1.0], is_transmitter=False)
                    gui.update_paths(show=True)
                    state["added_rx0"] = True
                if t >= t_s4_start + 3.8 and not state["added_rx1"]:
                    gui.add_radio_device([2.9, -2.0, 1.0], is_transmitter=False)
                    gui.update_paths(show=True)
                    state["added_rx1"] = True
                if t >= t_s4_start + 6.4 and not state["added_rx2"]:
                    gui.add_radio_device([-3.2, 1.2, 1.0], is_transmitter=False)
                    gui.update_paths(show=True)
                    state["added_rx2"] = True

            elif t < t_s6_start:
                # Scene 05: 选中 rx-0 弹出右侧控制面板 + Gizmo，开启室内移动轨迹动画
                u = (t - t_s5_start) / max(t_s6_start - t_s5_start, 1e-3)
                set_camera_orbit(
                    center=(-0.2, 0.0, 0.6),
                    radius=lerp(10.6, 11.4, u),
                    az_deg=lerp(-18.0, -68.0, u),
                    el_deg=lerp(48.0, 56.0, u),
                )
                if t >= t_s5_start + 1.2 and not state["selected_rx0"]:
                    rx0 = gui.scene.get("rx-0")
                    gui.selected_object = rx0
                    gui.selected_type = SelectionType.Receiver
                    state["selected_rx0"] = True
                if t >= t_s5_start + 3.2 and not state["started_traj"]:
                    traj = gui.animation_config.trajectories["rx-0"]
                    traj.add_point([0.2, 2.8, 1.0])
                    traj.add_point([-0.2, 0.6, 1.0])
                    traj.add_point([-0.9, -1.6, 1.0])
                    traj.add_point([0.6, -2.4, 1.0])
                    traj.velocity = 0.25
                    traj.looping_mode_i = LoopingMode.Mirror.value
                    traj.distance = 0.0
                    traj.enabled = True
                    gui.animation_config.playing = True
                    state["started_traj"] = True
            else:
                # Scene 06: 取消选中并拉远环绕全景收尾
                u = (t - t_s6_start) / max(total_duration - t_s6_start, 1e-3)
                if not state["cleared_sel"]:
                    gui.animation_config.playing = False
                    gui.clear_selection()
                    state["cleared_sel"] = True
                set_camera_orbit(
                    center=(-0.15, 0.0, 0.5),
                    radius=lerp(11.4, 13.4, u),
                    az_deg=lerp(-68.0, -108.0, u),
                    el_deg=lerp(56.0, 62.0, u),
                )

            # 推进一帧真实 GUI 渲染与仿真
            ps.frame_tick()
            buf = ps.screenshot_to_buffer(transparent_bg=False, vertical_flip=True, include_UI=True)
            proc.stdin.write(buf.tobytes())

            # 同步保存 4 张公众号高清实测截图
            if t >= 10.0 and not state["saved_img1"]:
                save_rgba_png(buf, docs_img_dir / "01_gui_overview.png")
                state["saved_img1"] = True
            if t >= t_s3_end - 1.5 and not state["saved_img2"]:
                save_rgba_png(buf, docs_img_dir / "02_ble_radiomap_2d4g.png")
                state["saved_img2"] = True
            if t >= t_s4_end - 1.5 and not state["saved_img3"]:
                save_rgba_png(buf, docs_img_dir / "03_multipath_rays.png")
                state["saved_img3"] = True
            if t >= t_s5_start + 9.0 and not state["saved_img4"]:
                save_rgba_png(buf, docs_img_dir / "04_device_selection_trajectory.png")
                state["saved_img4"] = True

            if frame_idx % 120 == 0:
                print(f"[PROGRESS] {frame_idx}/{total_frames} 帧 ({t:.1f}s / {total_duration:.1f}s)")
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg 原始视频编码失败，退出码: {proc.returncode}")

    # 使用 FFmpeg 合成最终带响度标准化配音与硬字幕的 1080p MP4
    output_dir = project_dir / "output"
    master_audio = output_dir / "audio" / "master_voiceover.mp3"
    mux_cmd = [
        "ffmpeg", "-y",
        "-i", raw_video_path.name,
        "-i", str(master_audio),
        "-vf", "scale=1920:1080:flags=lanczos,ass=subtitles.ass",
        "-af", f"loudnorm=I=-15:TP=-1.5:LRA=11,apad=whole_dur={total_duration:.2f}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-t", f"{total_duration:.2f}",
        "-movflags", "+faststart",
        final_video_path.name,
    ]
    print("[INFO] 正在合成最终 1080p 带配音与字幕成片...")
    res = subprocess.run(mux_cmd, cwd=str(output_dir), capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg 成片合成失败:\n{res.stderr}")

    print(f"[OK] 成片已生成: {final_video_path}")


if __name__ == "__main__":
    main()
