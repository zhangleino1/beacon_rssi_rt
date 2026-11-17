"""
Depth Anything 3 (DA3) 点云/网格 -> Sionna RT 1.2.2 (Mitsuba XML) 场景转换脚本

功能：
1. 支持将 DA3 导出的 .ply / .glb / .obj 网格或点云通过 Open3D 进行网格修复、尺度校准、底面对齐（Z=0）。
2. 自动生成兼容 Sionna RT 1.2.2 与 Sionna RT GUI 的 Mitsuba XML 场景文件（含 ITU 无线电材质定义）。
3. 支持 `--demo` 生成一个带隔断墙与桌子的标准测试房间（6m x 5m x 2.8m），用于快速验证 GUI。
"""

import argparse
from pathlib import Path
import numpy as np
import open3d as o3d
import trimesh


XML_TEMPLATE = """<scene version="2.1.0">
    <!-- ITU 无线电材质定义 (Sionna RT 1.2.2) -->
    <bsdf type="itu-radio-material" id="mat-concrete">
        <string name="type" value="concrete"/>
        <float name="thickness" value="0.20"/>
    </bsdf>

    <bsdf type="itu-radio-material" id="mat-wood">
        <string name="type" value="wood"/>
        <float name="thickness" value="0.04"/>
    </bsdf>

    <bsdf type="itu-radio-material" id="mat-glass">
        <string name="type" value="glass"/>
        <float name="thickness" value="0.01"/>
    </bsdf>

    <bsdf type="itu-radio-material" id="mat-plasterboard">
        <string name="type" value="plasterboard"/>
        <float name="thickness" value="0.10"/>
    </bsdf>

{shapes_xml}
</scene>
"""


def build_demo_room(out_dir: Path) -> Path:
    """生成一个 6m x 5m x 2.8m 的室内测试房间（外墙+地板+室内隔断墙+木桌）"""
    meshes_dir = out_dir / "meshes"
    meshes_dir.mkdir(parents=True, exist_ok=True)

    # 1. 房间外壳（地板+四周墙壁，无顶盖以便直接俯视或配合 Slice Plane 观察）
    floor = trimesh.creation.box(extents=[6.0, 5.0, 0.15])
    floor.apply_translation([0.0, 0.0, -0.075])

    wall_n = trimesh.creation.box(extents=[6.0, 0.15, 2.8])
    wall_n.apply_translation([0.0, 2.425, 1.4])

    wall_s = trimesh.creation.box(extents=[6.0, 0.15, 2.8])
    wall_s.apply_translation([0.0, -2.425, 1.4])

    wall_w = trimesh.creation.box(extents=[0.15, 5.0, 2.8])
    wall_w.apply_translation([-2.925, 0.0, 1.4])

    wall_e = trimesh.creation.box(extents=[0.15, 5.0, 2.8])
    wall_e.apply_translation([2.925, 0.0, 1.4])

    room_shell = trimesh.util.concatenate([floor, wall_n, wall_s, wall_w, wall_e])
    shell_ply = meshes_dir / "room_shell.ply"
    room_shell.export(shell_ply)

    # 2. 室内石膏板隔断墙（模拟 NLOS 遮挡与多径反射）
    partition = trimesh.creation.box(extents=[0.12, 2.6, 2.4])
    partition.apply_translation([0.2, 0.8, 1.2])
    partition_ply = meshes_dir / "partition_wall.ply"
    partition.export(partition_ply)

    # 3. 室内木桌
    table = trimesh.creation.box(extents=[1.6, 0.9, 0.75])
    table.apply_translation([-1.2, -0.8, 0.375])
    table_ply = meshes_dir / "wood_table.ply"
    table.export(table_ply)

    shapes_xml = """    <shape type="ply" id="mesh-room-shell">
        <string name="filename" value="meshes/room_shell.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-concrete" name="bsdf"/>
    </shape>

    <shape type="ply" id="mesh-partition-wall">
        <string name="filename" value="meshes/partition_wall.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-plasterboard" name="bsdf"/>
    </shape>

    <shape type="ply" id="mesh-wood-table">
        <string name="filename" value="meshes/wood_table.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-wood" name="bsdf"/>
    </shape>"""

    xml_path = out_dir / "room.xml"
    xml_path.write_text(XML_TEMPLATE.format(shapes_xml=shapes_xml), encoding="utf-8")
    return xml_path


def convert_da3_mesh(
    input_path: Path,
    out_dir: Path,
    scale: float = 1.0,
    material: str = "concrete",
    poisson_depth: int = 8,
) -> Path:
    """将 DA3 重建的点云或网格修复并导出为 Sionna RT XML 场景"""
    meshes_dir = out_dir / "meshes"
    meshes_dir.mkdir(parents=True, exist_ok=True)

    mesh = o3d.io.read_triangle_mesh(str(input_path))
    if len(mesh.triangles) == 0:
        print(f"[INFO] {input_path.name} 不含三角面片，作为点云执行 Poisson 表面重建...")
        pcd = o3d.io.read_point_cloud(str(input_path))
        pcd.estimate_normals()
        pcd.orient_normals_consistent_tangent_plane(30)
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=poisson_depth
        )
        densities = np.asarray(densities)
        mesh.remove_vertices_by_mask(densities < np.quantile(densities, 0.02))

    # 1. 尺度校准
    if scale != 1.0:
        mesh.scale(scale, center=(0.0, 0.0, 0.0))

    # 2. 网格清洗与修复
    mesh.remove_duplicated_vertices()
    mesh.remove_duplicated_triangles()
    mesh.remove_degenerate_triangles()
    mesh.remove_unreferenced_vertices()
    mesh.compute_vertex_normals()

    # 3. 居中 XY 并将最低点对齐到 Z = 0
    verts = np.asarray(mesh.vertices)
    xy_center = verts[:, :2].mean(axis=0)
    z_min = verts[:, 2].min()
    mesh.translate([-xy_center[0], -xy_center[1], -z_min])

    out_ply = meshes_dir / "da3_room.ply"
    o3d.io.write_triangle_mesh(str(out_ply), mesh, write_ascii=False)

    shapes_xml = f"""    <shape type="ply" id="mesh-da3-room">
        <string name="filename" value="meshes/da3_room.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-{material}" name="bsdf"/>
    </shape>"""

    xml_path = out_dir / "room.xml"
    xml_path.write_text(XML_TEMPLATE.format(shapes_xml=shapes_xml), encoding="utf-8")
    return xml_path


def main():
    parser = argparse.ArgumentParser(description="Convert DA3 3D output to Sionna RT XML scene")
    parser.add_argument("--input", "-i", type=str, help="DA3 导出的 .ply/.glb/.obj 文件路径")
    parser.add_argument("--out-dir", "-o", type=str, default="scenes", help="输出场景目录")
    parser.add_argument("--scale", "-s", type=float, default=1.0, help="尺度缩放系数（对齐真实米制单位）")
    parser.add_argument(
        "--material",
        "-m",
        type=str,
        default="concrete",
        choices=["concrete", "wood", "glass", "plasterboard"],
        help="默认 ITU 无线电材质",
    )
    parser.add_argument("--demo", action="store_true", help="生成示例室内房间 scenes/room.xml")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if args.demo or not args.input:
        xml_path = build_demo_room(out_dir)
        print(f"[OK] 已生成示例室内房间场景: {xml_path.resolve()}")
    else:
        xml_path = convert_da3_mesh(
            Path(args.input),
            out_dir=out_dir,
            scale=args.scale,
            material=args.material,
        )
        print(f"[OK] 已转换 DA3 房间场景: {xml_path.resolve()}")


if __name__ == "__main__":
    main()
