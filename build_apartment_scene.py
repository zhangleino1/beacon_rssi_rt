"""
根据户型平面图生成 1:1 室内公寓 3D 场景 (Sionna RT 1.2.2 / Mitsuba XML)

包含功能区（与平面图完全对应）：
- 玄关 (Lobby / Entrance)：左下角入户门洞、玄关柜
- 更衣室 (Dressing)：左中双排衣柜、门洞
- 卫浴间 (Bathroom)：左上洗手台外拓区、马桶、干湿分离玻璃淋浴间、通往主空间的门洞
- 客厅 (Living Room)：中下三人位沙发、长茶几、整墙电视柜、电视机、转角冰箱
- 餐厅 (Dining Area)：正中餐桌 + 四把餐椅
- 卧室 (Bedroom)：中上双人床（含枕头/被褥）、左右床头柜、左侧整排衣柜、北侧大窗
- 厨房 (Kitchen)：右下操作台、水槽、双燃气灶、北侧储物柜
- 工作阳台 (Working Balcony)：右中上圆形水槽、洗衣机、外凸飘窗
- 阳台 (Balcony)：右上角玻璃门、护栏
"""

from pathlib import Path
import numpy as np
import trimesh


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> trimesh.Trimesh:
    """用轴对齐边界框 [x0, x1] x [y0, y1] x [z0, z1] 创建 Trimesh 立方体"""
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    assert dx > 0 and dy > 0 and dz > 0, f"Invalid box dimensions: {(x0, x1, y0, y1, z0, z1)}"
    m = trimesh.creation.box(extents=[dx, dy, dz])
    m.apply_translation([(x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5])
    return m


def wall_with_door(
    x0: float, x1: float, y0: float, y1: float,
    door_start: float, door_end: float,
    axis: str = "y",
    wall_h: float = 2.8, door_h: float = 2.1
) -> list[trimesh.Trimesh]:
    """创建带门洞（含门楣）的墙体，axis='x' 表示沿 X 方向延伸，axis='y' 表示沿 Y 方向延伸"""
    parts = []
    if axis == "x":
        if door_start > x0:
            parts.append(box(x0, door_start, y0, y1, 0.0, wall_h))
        if door_end < x1:
            parts.append(box(door_end, x1, y0, y1, 0.0, wall_h))
        if wall_h > door_h:
            parts.append(box(door_start, door_end, y0, y1, door_h, wall_h))
    else:
        if door_start > y0:
            parts.append(box(x0, x1, y0, door_start, 0.0, wall_h))
        if door_end < y1:
            parts.append(box(x0, x1, door_end, y1, 0.0, wall_h))
        if wall_h > door_h:
            parts.append(box(x0, x1, door_start, door_end, door_h, wall_h))
    return parts


def wall_with_window(
    x0: float, x1: float, y0: float, y1: float,
    win_start: float, win_end: float,
    axis: str = "x",
    wall_h: float = 2.8, sill_h: float = 0.85, head_h: float = 2.4
) -> tuple[list[trimesh.Trimesh], trimesh.Trimesh]:
    """创建带窗洞的墙体及对应窗玻璃网格"""
    parts = []
    if axis == "x":
        if win_start > x0:
            parts.append(box(x0, win_start, y0, y1, 0.0, wall_h))
        if win_end < x1:
            parts.append(box(win_end, x1, y0, y1, 0.0, wall_h))
        if sill_h > 0:
            parts.append(box(win_start, win_end, y0, y1, 0.0, sill_h))
        if wall_h > head_h:
            parts.append(box(win_start, win_end, y0, y1, head_h, wall_h))
        ym = 0.5 * (y0 + y1)
        glass = box(win_start, win_end, ym - 0.015, ym + 0.015, sill_h, head_h)
    else:
        if win_start > y0:
            parts.append(box(x0, x1, y0, win_start, 0.0, wall_h))
        if win_end < y1:
            parts.append(box(x0, x1, win_end, y1, 0.0, wall_h))
        if sill_h > 0:
            parts.append(box(x0, x1, win_start, win_end, 0.0, sill_h))
        if wall_h > head_h:
            parts.append(box(x0, x1, win_start, win_end, head_h, wall_h))
        xm = 0.5 * (x0 + x1)
        glass = box(xm - 0.015, xm + 0.015, win_start, win_end, sill_h, head_h)
    return parts, glass


def build_apartment(out_dir: Path) -> Path:
    meshes_dir = out_dir / "meshes"
    meshes_dir.mkdir(parents=True, exist_ok=True)

    H = 2.80  # 层高 2.8m

    concrete_meshes = []
    plaster_meshes = []
    wood_floor_meshes = []
    tile_floor_meshes = []
    wood_furniture_meshes = []
    soft_furniture_meshes = []
    glass_meshes = []
    metal_meshes = []
    ceramic_meshes = []

    # =========================================================================
    # 1. 地面 (Floors)
    # =========================================================================
    # 主空间木地板 (玄关 + 客厅 + 餐厅 + 卧室 + 更衣室)
    wood_floor_meshes.append(box(-2.30, 2.00, -4.30, 4.30, -0.12, 0.0))   # 客厅/餐厅/卧室通铺
    wood_floor_meshes.append(box(-3.85, -2.30, -4.20, -2.05, -0.12, 0.0)) # 玄关地面
    wood_floor_meshes.append(box(-4.15, -2.30, -2.05, 0.20, -0.12, 0.0))  # 更衣室地面

    # 瓷砖地面 (卫浴间 + 厨房 + 工作阳台 + 阳台)
    tile_floor_meshes.append(box(-3.85, -2.30, 0.20, 4.15, -0.12, 0.0))   # 卫浴间主区
    tile_floor_meshes.append(box(-4.25, -3.85, 0.20, 1.55, -0.12, 0.0))   # 卫浴间洗手台外拓区
    tile_floor_meshes.append(box(2.00, 3.85, -3.25, -0.85, -0.12, 0.0))   # 厨房地面
    tile_floor_meshes.append(box(2.00, 3.15, -4.25, -3.25, -0.12, 0.0))   # 右下过渡区
    tile_floor_meshes.append(box(2.00, 3.15, -0.85, 1.15, -0.12, 0.0))    # 右中采光走廊区
    tile_floor_meshes.append(box(2.00, 3.85, 1.15, 3.15, -0.12, 0.0))     # 工作阳台地面
    tile_floor_meshes.append(box(2.00, 3.70, 3.15, 4.45, -0.12, 0.0))     # 右上景观阳台地面

    # =========================================================================
    # 2. 建筑承重柱与外墙 (Concrete Structural Columns & Exterior Walls)
    # =========================================================================
    # 四大承重柱 (对应平面图深灰色实心块)
    concrete_meshes.append(box(-2.75, -1.70, 4.10, 4.60, 0.0, H))   # 左上承重柱
    concrete_meshes.append(box(1.95, 3.10, 4.00, 4.60, 0.0, H))     # 右上承重柱
    concrete_meshes.append(box(-2.65, -1.85, -4.60, -3.90, 0.0, H)) # 左下入户门旁承重柱
    concrete_meshes.append(box(1.95, 3.10, -4.60, -3.95, 0.0, H))   # 右下承重柱

    # 北侧卧室大窗外墙 (X: -1.70 ~ 1.95, Y: 4.25 ~ 4.45)
    n_wall_parts, n_glass = wall_with_window(
        -1.70, 1.95, 4.25, 4.45, win_start=-1.45, win_end=1.70,
        axis="x", wall_h=H, sill_h=0.65, head_h=2.55
    )
    concrete_meshes.extend(n_wall_parts)
    glass_meshes.append(n_glass)

    # 南侧客厅电视背景外墙 (X: -1.85 ~ 1.95, Y: -4.50 ~ -4.25)
    concrete_meshes.append(box(-1.85, 1.95, -4.50, -4.25, 0.0, H))

    # 左下玄关入户门外墙 (X: -3.95 ~ -2.65, Y: -4.35 ~ -4.15, 留出入户门洞)
    concrete_meshes.extend(
        wall_with_door(-3.95, -2.65, -4.35, -4.15, door_start=-3.75, door_end=-2.80, axis="x", wall_h=H, door_h=2.20)
    )
    # 玄关西墙 (X: -3.95 ~ -3.75, Y: -4.35 ~ -2.05)
    concrete_meshes.append(box(-3.95, -3.75, -4.35, -2.05, 0.0, H))

    # 更衣室西外墙 (X: -4.25 ~ -4.05, Y: -2.05 ~ 0.20)
    concrete_meshes.append(box(-4.25, -4.05, -2.05, 0.20, 0.0, H))
    concrete_meshes.append(box(-4.25, -3.75, -2.20, -2.05, 0.0, H)) # 转角连接

    # 卫浴间洗手台西外墙与北外墙
    concrete_meshes.append(box(-4.35, -4.15, 0.20, 1.65, 0.0, H))   # 洗手台西侧外墙
    concrete_meshes.append(box(-4.35, -3.75, 1.50, 1.70, 0.0, H))   # 洗手台北侧折角
    concrete_meshes.append(box(-3.95, -3.75, 1.65, 4.30, 0.0, H))   # 马桶与淋浴区西侧外墙
    concrete_meshes.append(box(-3.95, -2.75, 4.10, 4.30, 0.0, H))   # 淋浴区北侧外墙

    # 右侧翼外墙（厨房、采光区、工作阳台、阳台）
    # 厨房南侧与北侧厚墙体 (对应平面图厨房上下灰色墙墩)
    concrete_meshes.append(box(1.95, 3.75, -3.35, -3.05, 0.0, H))   # 厨房南侧厚墙
    concrete_meshes.append(box(1.95, 3.75, -1.05, -0.75, 0.0, H))   # 厨房北侧厚墙
    # 厨房东侧外凸窗墙 (X: 3.75 ~ 3.92, Y: -3.20 ~ -0.90)
    k_wall_parts, k_glass = wall_with_window(
        3.75, 3.92, -3.20, -0.90, win_start=-2.85, win_end=-1.25,
        axis="y", wall_h=H, sill_h=0.95, head_h=2.40
    )
    concrete_meshes.extend(k_wall_parts)
    glass_meshes.append(k_glass)

    # 工作阳台南侧与北侧厚墙体 (对应平面图工作阳台上下灰色墙墩)
    concrete_meshes.append(box(1.95, 3.75, 1.00, 1.30, 0.0, H))     # 工作阳台南侧厚墙
    concrete_meshes.append(box(1.95, 3.75, 3.00, 3.30, 0.0, H))     # 工作阳台北侧厚墙
    # 工作阳台东侧外凸飘窗墙 (X: 3.75 ~ 3.92, Y: 1.15 ~ 3.15)
    wb_wall_parts, wb_glass = wall_with_window(
        3.75, 3.92, 1.15, 3.15, win_start=1.40, win_end=2.90,
        axis="y", wall_h=H, sill_h=0.90, head_h=2.45
    )
    concrete_meshes.extend(wb_wall_parts)
    glass_meshes.append(wb_glass)

    # 右中采光隔断墙墩与外侧玻璃幕墙
    concrete_meshes.append(box(1.95, 2.85, 0.02, 0.25, 0.0, H))     # 右中横向小隔墙墩
    glass_meshes.append(box(3.05, 3.10, -0.75, 1.00, 0.0, H))       # 采光区东侧落地玻璃
    glass_meshes.append(box(3.05, 3.10, -3.95, -3.35, 0.0, H))      # 右下侧窗玻璃

    # 右上角阳台矮墙与玻璃栏杆 (X: 2.00 ~ 3.70, Y: 3.30 ~ 4.45)
    concrete_meshes.append(box(3.58, 3.72, 3.30, 4.45, 0.0, 0.45))  # 阳台东侧矮基座
    concrete_meshes.append(box(3.10, 3.72, 4.32, 4.45, 0.0, 0.45))  # 阳台东北矮基座
    glass_meshes.append(box(3.62, 3.68, 3.30, 4.42, 0.45, 1.15))    # 阳台东侧玻璃栏杆
    glass_meshes.append(box(3.10, 3.68, 4.36, 4.42, 0.45, 1.15))    # 阳台东北玻璃栏杆

    # =========================================================================
    # 3. 室内轻质隔断墙与门洞 (Interior Partition Walls - Plasterboard)
    # =========================================================================
    # 左侧与客厅/餐厅/卧室之间的主纵墙 (X: -2.35 ~ -2.20, Y: -3.20 ~ 4.10)
    # 在 Y: 0.35 ~ 1.25 处留出卫浴间通往餐厅的门洞
    plaster_meshes.extend(
        wall_with_door(-2.35, -2.20, -3.20, 4.10, door_start=0.35, door_end=1.25, axis="y", wall_h=H, door_h=2.15)
    )

    # 玄关与更衣室之间的隔墙 (Y: -2.15 ~ -2.00, X: -3.75 ~ -2.35)
    plaster_meshes.append(box(-3.75, -2.35, -2.15, -2.00, 0.0, H))

    # 更衣室与卫浴间之间的隔墙 (Y: 0.15 ~ 0.30, X: -4.15 ~ -2.35, 含门洞 X: -3.65 ~ -2.90)
    plaster_meshes.extend(
        wall_with_door(-4.15, -2.35, 0.15, 0.30, door_start=-3.65, door_end=-2.90, axis="x", wall_h=H, door_h=2.15)
    )

    # 卫浴间干湿分离玻璃淋浴隔断 (Y: 2.50 ~ 2.54, X: -3.75 ~ -2.35)
    glass_meshes.append(box(-3.75, -2.35, 2.50, 2.54, 0.0, 2.10))

    # 右侧主空间与厨房/工作阳台/阳台之间的纵墙 (X: 1.92 ~ 2.08)
    # (a) 右下门洞区 (Y: -3.95 ~ -3.25)
    plaster_meshes.extend(
        wall_with_door(1.92, 2.08, -3.95, -3.25, door_start=-3.90, door_end=-3.30, axis="y", wall_h=H, door_h=2.15)
    )
    glass_meshes.append(box(1.98, 2.02, -3.90, -3.30, 0.0, 2.15))
    # (b) 厨房西隔墙（含通往厨房的平开门洞 Y: -2.05 ~ -1.25）
    plaster_meshes.extend(
        wall_with_door(1.92, 2.08, -3.10, -0.95, door_start=-2.05, door_end=-1.25, axis="y", wall_h=H, door_h=2.15)
    )
    # (c) 右中两扇采光玻璃门/落地窗 (Y: -0.75 ~ 1.00)
    glass_meshes.append(box(1.98, 2.02, -0.75, 0.02, 0.0, 2.30))
    glass_meshes.append(box(1.98, 2.02, 0.25, 1.00, 0.0, 2.30))
    plaster_meshes.append(box(1.92, 2.08, -0.75, 1.00, 2.30, H))
    # (d) 工作阳台西隔墙（含玻璃推拉窗/门 Y: 1.45 ~ 2.75）
    wb_in_parts, wb_in_glass = wall_with_window(
        1.92, 2.08, 1.25, 3.05, win_start=1.45, win_end=2.75,
        axis="y", wall_h=H, sill_h=0.40, head_h=2.25
    )
    plaster_meshes.extend(wb_in_parts)
    glass_meshes.append(wb_in_glass)
    # (e) 右上景观阳台玻璃门 (Y: 3.25 ~ 4.00)
    plaster_meshes.extend(
        wall_with_door(1.92, 2.08, 3.25, 4.00, door_start=3.30, door_end=3.95, axis="y", wall_h=H, door_h=2.20)
    )
    glass_meshes.append(box(1.98, 2.02, 3.30, 3.95, 0.0, 2.20))

    # =========================================================================
    # 4. 室内全屋家具与设备 (Furniture & Appliances)
    # =========================================================================
    # --- A. 卧室 (Bedroom, 中北区) ---
    # 双人床架与床头板 (北墙居中偏右 X: -0.55 ~ 1.05, Y: 2.05 ~ 4.22)
    wood_furniture_meshes.append(box(-0.55, 1.05, 4.10, 4.22, 0.0, 1.10))  # 实木床头板
    wood_furniture_meshes.append(box(-0.55, 1.05, 2.05, 4.10, 0.0, 0.28))  # 床架底座
    soft_furniture_meshes.append(box(-0.50, 1.00, 2.10, 4.08, 0.28, 0.52)) # 软床垫
    soft_furniture_meshes.append(box(-0.48, 0.98, 2.10, 3.35, 0.52, 0.58)) # 被子
    # 枕头 x 2
    soft_furniture_meshes.append(box(-0.38, 0.18, 3.62, 4.02, 0.52, 0.64))
    soft_furniture_meshes.append(box(0.30, 0.86, 3.62, 4.02, 0.52, 0.64))
    # 左右床头柜
    wood_furniture_meshes.append(box(-1.55, -0.62, 3.75, 4.22, 0.0, 0.50)) # 左床头柜
    wood_furniture_meshes.append(box(1.12, 1.90, 3.75, 4.22, 0.0, 0.50))   # 右床头柜
    # 卧室左侧整排大衣柜 (X: -2.20 ~ -1.60, Y: 1.40 ~ 4.10)
    wood_furniture_meshes.append(box(-2.20, -1.60, 1.40, 4.10, 0.0, 2.45))

    # --- B. 餐厅 (Dining Area, 正中区) ---
    # 餐桌 (X: -0.75 ~ 0.65, Y: -0.15 ~ 0.70, 高 0.76m)
    wood_furniture_meshes.append(box(-0.75, 0.65, -0.15, 0.70, 0.70, 0.76)) # 桌面
    wood_furniture_meshes.append(box(-0.68, -0.58, -0.08, 0.02, 0.0, 0.70)) # 桌腿1
    wood_furniture_meshes.append(box(0.50, 0.60, -0.08, 0.02, 0.0, 0.70))   # 桌腿2
    wood_furniture_meshes.append(box(-0.68, -0.58, 0.53, 0.63, 0.0, 0.70))  # 桌腿3
    wood_furniture_meshes.append(box(0.50, 0.60, 0.53, 0.63, 0.0, 0.70))    # 桌腿4
    # 4 把餐椅 (北侧 2 把，南侧 2 把)
    for cx in (-0.38, 0.28):
        # 北侧餐椅
        soft_furniture_meshes.append(box(cx - 0.22, cx + 0.22, 0.72, 1.12, 0.42, 0.48))
        wood_furniture_meshes.append(box(cx - 0.22, cx + 0.22, 1.05, 1.13, 0.48, 0.88))
        wood_furniture_meshes.append(box(cx - 0.18, cx + 0.18, 0.76, 1.08, 0.0, 0.42))
        # 南侧餐椅
        soft_furniture_meshes.append(box(cx - 0.22, cx + 0.22, -0.57, -0.17, 0.42, 0.48))
        wood_furniture_meshes.append(box(cx - 0.22, cx + 0.22, -0.58, -0.50, 0.48, 0.88))
        wood_furniture_meshes.append(box(cx - 0.18, cx + 0.18, -0.53, -0.21, 0.0, 0.42))

    # --- C. 客厅 (Living Room, 中南区) ---
    # 三人位沙发 (面向南侧电视墙, X: -0.95 ~ 0.85, Y: -1.85 ~ -0.98)
    soft_furniture_meshes.append(box(-0.95, 0.85, -1.85, -0.98, 0.0, 0.42))  # 沙发坐垫与底座
    soft_furniture_meshes.append(box(-0.95, 0.85, -1.16, -0.98, 0.42, 0.86)) # 沙发靠背
    soft_furniture_meshes.append(box(-0.95, -0.77, -1.85, -0.98, 0.42, 0.68))# 左扶手
    soft_furniture_meshes.append(box(0.67, 0.85, -1.85, -0.98, 0.42, 0.68))  # 右扶手
    # 长方形茶几 (X: -0.62 ~ 0.52, Y: -2.85 ~ -2.30)
    wood_furniture_meshes.append(box(-0.62, 0.52, -2.85, -2.30, 0.0, 0.38))
    glass_meshes.append(box(-0.58, 0.48, -2.81, -2.34, 0.38, 0.42))          # 茶几钢化玻璃台面
    # 南墙整排电视地柜 (X: -1.80 ~ 1.15, Y: -4.25 ~ -3.72)
    wood_furniture_meshes.append(box(-1.80, 1.15, -4.25, -3.72, 0.0, 0.45))
    # 65寸液晶电视 (金属反射面, X: -0.80 ~ 0.65, Y: -4.12 ~ -4.04, Z: 0.65 ~ 1.48)
    metal_meshes.append(box(-0.80, 0.65, -4.12, -4.04, 0.65, 1.48))
    # 电视柜右侧立式双门冰箱 (X: 1.20 ~ 1.90, Y: -4.22 ~ -3.45, Z: 0.0 ~ 1.82)
    metal_meshes.append(box(1.20, 1.90, -4.22, -3.45, 0.0, 1.82))

    # --- D. 玄关与更衣室 (Lobby & Dressing) ---
    # 玄关北侧鞋柜 (X: -3.75 ~ -2.35, Y: -2.60 ~ -2.15)
    wood_furniture_meshes.append(box(-3.75, -2.35, -2.60, -2.15, 0.0, 1.15))
    # 更衣室左右两侧衣柜
    wood_furniture_meshes.append(box(-4.05, -3.55, -2.00, 0.15, 0.0, 2.40))  # 更衣室西侧衣柜
    wood_furniture_meshes.append(box(-2.85, -2.35, -2.00, -0.05, 0.0, 2.40)) # 更衣室东侧衣柜

    # --- E. 卫浴间 (Bathroom) ---
    # 洗手台柜与台盆 (X: -4.15 ~ -3.62, Y: 0.35 ~ 1.50)
    ceramic_meshes.append(box(-4.15, -3.62, 0.35, 1.50, 0.0, 0.82))
    # 马桶 (X: -3.75 ~ -3.10, Y: 1.75 ~ 2.25)
    ceramic_meshes.append(box(-3.75, -3.52, 1.78, 2.22, 0.0, 0.78))          # 马桶水箱
    ceramic_meshes.append(box(-3.52, -3.10, 1.75, 2.25, 0.0, 0.42))          # 马桶座圈

    # --- F. 厨房与工作阳台 (Kitchen & Working Balcony) ---
    # 厨房南侧操作台 (含水槽与燃气灶, X: 2.10 ~ 3.75, Y: -3.05 ~ -2.42)
    ceramic_meshes.append(box(2.10, 3.75, -3.05, -2.42, 0.0, 0.85))
    metal_meshes.append(box(2.38, 2.90, -2.95, -2.52, 0.85, 0.88))           # 不锈钢水槽面板
    metal_meshes.append(box(3.15, 3.62, -2.95, -2.52, 0.85, 0.90))           # 双眼燃气灶与锅架
    # 厨房北侧储物高柜/吊柜 (X: 2.20 ~ 3.75, Y: -1.45 ~ -1.05)
    wood_furniture_meshes.append(box(2.20, 3.75, -1.45, -1.05, 0.0, 0.85))
    wood_furniture_meshes.append(box(2.20, 3.75, -1.40, -1.05, 1.45, 2.25))
    # 工作阳台洗衣机与洗手池
    metal_meshes.append(box(2.95, 3.65, 1.35, 2.05, 0.0, 0.90))              # 滚筒洗衣机
    ceramic_meshes.append(box(2.18, 2.75, 1.35, 1.90, 0.0, 0.82))            # 阳台洗涤池

    # =========================================================================
    # 5. 导出分组 PLY 网格并生成 Mitsuba XML
    # =========================================================================
    groups = [
        ("concrete_structure", concrete_meshes, "mat-concrete"),
        ("interior_walls", plaster_meshes, "mat-plasterboard"),
        ("wood_floor", wood_floor_meshes, "mat-floorboard"),
        ("tile_floor", tile_floor_meshes, "mat-marble"),
        ("wood_furniture", wood_furniture_meshes, "mat-wood"),
        ("soft_furniture", soft_furniture_meshes, "mat-ceiling-board"),
        ("glass_windows_doors", glass_meshes, "mat-glass"),
        ("metal_appliances", metal_meshes, "mat-metal"),
        ("ceramic_fixtures", ceramic_meshes, "mat-ceramic"),
    ]

    shapes_xml_lines = []
    for name, mesh_list, mat_id in groups:
        if not mesh_list:
            continue
        combined = trimesh.util.concatenate(mesh_list)
        combined.merge_vertices()
        ply_path = meshes_dir / f"{name}.ply"
        combined.export(ply_path)
        shapes_xml_lines.append(
            f"""    <shape type="ply" id="mesh-{name}" name="mesh-{name}">
        <string name="filename" value="meshes/{name}.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="{mat_id}" name="bsdf"/>
    </shape>"""
        )

    xml_content = f"""<scene version="2.1.0">
    <!-- ================================================================== -->
    <!-- 室内公寓电磁材质与视觉配色定义 (ITU-R P.2040-3 / Sionna RT 1.2.2)  -->
    <!-- ================================================================== -->

    <!-- 钢筋混凝土承重墙/外墙 -->
    <bsdf type="itu-radio-material" id="mat-concrete">
        <string name="type" value="concrete"/>
        <float name="thickness" value="0.24"/>
        <rgb name="color" value="0.52, 0.54, 0.56"/>
    </bsdf>

    <!-- 室内石膏板/轻质砖隔断墙 -->
    <bsdf type="itu-radio-material" id="mat-plasterboard">
        <string name="type" value="plasterboard"/>
        <float name="thickness" value="0.12"/>
        <rgb name="color" value="0.88, 0.87, 0.84"/>
    </bsdf>

    <!-- 室内实木复合地板 -->
    <bsdf type="itu-radio-material" id="mat-floorboard">
        <string name="type" value="plywood"/>
        <float name="thickness" value="0.08"/>
        <rgb name="color" value="0.72, 0.56, 0.38"/>
    </bsdf>

    <!-- 厨卫与阳台大理石/瓷砖地面 -->
    <bsdf type="itu-radio-material" id="mat-marble">
        <string name="type" value="marble"/>
        <float name="thickness" value="0.08"/>
        <rgb name="color" value="0.82, 0.83, 0.85"/>
    </bsdf>

    <!-- 实木家具（衣柜、餐桌、床架、电视柜） -->
    <bsdf type="itu-radio-material" id="mat-wood">
        <string name="type" value="wood"/>
        <float name="thickness" value="0.04"/>
        <rgb name="color" value="0.48, 0.32, 0.18"/>
    </bsdf>

    <!-- 软包家具（沙发、床垫、被褥、靠垫） -->
    <bsdf type="itu-radio-material" id="mat-ceiling-board">
        <string name="type" value="ceiling_board"/>
        <float name="thickness" value="0.10"/>
        <rgb name="color" value="0.32, 0.52, 0.68"/>
    </bsdf>

    <!-- 门窗玻璃、淋浴房隔断、阳台护栏 -->
    <bsdf type="itu-radio-material" id="mat-glass">
        <string name="type" value="glass"/>
        <float name="thickness" value="0.012"/>
        <rgb name="color" value="0.45, 0.78, 0.92"/>
    </bsdf>

    <!-- 家电金属表面（冰箱、电视机、洗衣机、燃气灶水槽） -->
    <bsdf type="itu-radio-material" id="mat-metal">
        <string name="type" value="metal"/>
        <float name="thickness" value="0.02"/>
        <rgb name="color" value="0.25, 0.27, 0.30"/>
    </bsdf>

    <!-- 卫浴洁具与厨房石材台面 -->
    <bsdf type="itu-radio-material" id="mat-ceramic">
        <string name="type" value="marble"/>
        <float name="thickness" value="0.05"/>
        <rgb name="color" value="0.93, 0.94, 0.95"/>
    </bsdf>

    <!-- ================================================================== -->
    <!-- 3D 房间网格组件                                                    -->
    <!-- ================================================================== -->
{chr(10).join(shapes_xml_lines)}
</scene>
"""

    room_xml = out_dir / "room.xml"
    apt_xml = out_dir / "apartment.xml"
    room_xml.write_text(xml_content, encoding="utf-8")
    apt_xml.write_text(xml_content, encoding="utf-8")
    return room_xml


if __name__ == "__main__":
    out = Path(__file__).parent / "scenes"
    xml_file = build_apartment(out)
    print(f"[OK] 户型图 1:1 室内 3D 场景已生成: {xml_file}")
