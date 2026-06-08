#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abaqus 后处理脚本 — 支持两种运行模式 + 批量处理：
  [2A] 在 Abaqus/CAE 内运行 (利用 visualization 模块)
  [2B] 脱离 Abaqus/CAE，用外部 Python 环境 (odbAccess + matplotlib/pyvista)

功能：
  1. 批量处理：多个 ODB × 多个场分量 → 自动生成全部组合的视频
  2. 遍历所有 step / frame，保存固定图例范围的云图 PNG
  3. 提取历史输出 (X-Y 数据)
  4. 生成累积 X-Y 曲线图 (当前点高亮)
  5. 云图 + 曲线图左右拼接
  6. ffmpeg 合成视频（可选）

用法：
  # 单个 ODB 单分量：
  $ python abaqus_postprocess.py --odb Job-4.odb --components S11

  # 批量：3 工况 × 2 应力分量 = 6 个视频
  $ python abaqus_postprocess.py \\
      --odb Job-4.odb Job-5.odb Job-6.odb \\
      --components S11 S22

  # 指定图例范围（所有视频统一）
  $ python abaqus_postprocess.py \\
      --odb Job-4.odb Job-5.odb Job-6.odb \\
      --components S11 S22 \\
      --legend-min 0 --legend-max 50

配置文件：
  同目录下的 FEM_config.py（可选），定义 abaqus_run_dir / model_name / base_dir

Author: Auto-generated post-processor
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict

# ---------------------------------------------------------------------------
# 全局开关：在 Abaqus/CAE 内运行时为 True，否则为 False
# ---------------------------------------------------------------------------
IN_CAE = False
try:
    from abaqus import *          # 仅在 Abaqus/CAE 内核进程中可用（abaqus python 不行）
    from abaqusConstants import *
    from caeModules import *
    from driverUtils import executeOnCaeStartup
    IN_CAE = True
except ImportError:
    pass

# 在 Abaqus CAE 内核中避免 Unicode 编码错误（Windows 控制台）
if IN_CAE and sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 安全 print：在 CAE 内核中自动转 ASCII 避免编码错误
_SAFE_PRINT = True
def _safe(s):
    """Convert to ASCII, replacing non-ASCII chars."""
    if _SAFE_PRINT:
        return s.encode('ascii', errors='replace').decode('ascii')
    return s


# ===================================================================
# 配置
# ===================================================================

@dataclass
class PostProcessConfig:
    """后处理配置 — 集中管理所有可调参数"""

    # --- ODB 路径 ---
    odb_path: str = "Job-4.odb"

    # --- 输出目录 ---
    output_dir: str = "postprocess_output"
    contour_dir: str = ""          # 自动设为 output_dir/contour
    curve_dir: str = ""            # 自动设为 output_dir/curve
    composite_dir: str = ""        # 自动设为 output_dir/composite

    # --- 场变量 (云图) ---
    field_variable: str = "S"                    # 默认 Mises 应力，也可用 "SDV1" 等
    field_position: str = "ELEMENT_NODAL"        # ELEMENT_NODAL / INTEGRATION_POINT / NODAL
    field_component: Optional[str] = None        # None = 不变量 (Mises)；"S11" = 分量
    field_refinement: str = "COMPONENT"          # 当 component 非 None 时的精炼方式

    # --- 图例范围 (固定以保证动画颜色一致) ---
    legend_min: float = 0.0
    legend_max: float = 100.0
    legend_auto_min: bool = False
    legend_auto_max: bool = False

    # --- 步骤 / 帧选择 ---
    step_indices: Optional[List[int]] = None     # None = 全部 step
    frame_step: int = 1                          # 每隔多少帧取一张 (1 = 全部)

    # --- 历史输出 (X-Y 数据) ---
    # 根据 ODB 内实际 historyRegions 配置；运行 _debug_history.py 可查看可用项
    history_queries: List[dict] = field(default_factory=lambda: [
        {
            "name": "RF2",
            "region": "ASSEMBLY.6",          # 在 historyRegions key 中匹配
            "variable": "RF2",
        },
        {
            "name": "U2",
            "region": "ASSEMBLY.6",
            "variable": "U2",
        },
    ])

    # --- 绘图 ---
    figure_dpi: int = 150
    figure_width_inch: float = 18.0
    figure_height_inch: float = 6.0
    highlight_marker_size: int = 80
    highlight_color: str = "red"

    # --- 视频 ---
    make_video: bool = True
    video_fps: int = 10
    video_name: str = "animation.mp4"
    cleanup_frames_after_video: bool = False

    # --- 2D 模型几何 (standalone 云图) ---
    # 从 ODB 自动推断；也可手动指定
    deform_scale_factor: float = 1.0             # 变形缩放因子

    # --- 图像格式 ---
    image_format: str = "PNG"                    # PNG / JPG / TIFF


# ===================================================================
# 工具函数
# ===================================================================

def ensure_dir(path: str) -> Path:
    """确保目录存在。"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_args():
    """命令行参数解析 (2B 模式)。"""
    parser = argparse.ArgumentParser(
        description="Abaqus ODB 后处理 — 批量 ODB × 场分量 → 云图+X-Y曲线合成图及动画"
    )
    parser.add_argument("--odb", type=str, nargs="+", default=["Job-4.odb"],
                        help="ODB 文件路径（可多个）")
    parser.add_argument("--components", type=str, nargs="+", default=["S11"],
                        help="应力/场分量 (如 S11 S22)——每个分量生成独立视频")
    parser.add_argument("--output", type=str, default="postprocess_output",
                        help="输出根目录")
    parser.add_argument("--field", type=str, default="S",
                        help="场变量名 (S, SDV1, U, etc.)")
    parser.add_argument("--legend-min", type=float, default=0.0)
    parser.add_argument("--legend-max", type=float, default=100.0)
    parser.add_argument("--frame-step", type=int, default=1,
                        help="每隔几帧取一张")
    parser.add_argument("--fps", type=int, default=10,
                        help="视频帧率")
    parser.add_argument("--no-video", action="store_true",
                        help="不合成视频")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--mode", type=str, default="standalone",
                        choices=["standalone", "cae"],
                        help="运行模式")
    parser.add_argument("--sequential", action="store_true",
                        help="顺序处理（默认）")
    # parse_known_args 忽略 Abaqus 内核传入的 -cae -noGUI 等内部参数
    args, _unknown = parser.parse_known_args()
    return args


def build_config_from_args(args) -> PostProcessConfig:
    """从命令行参数构造单次配置（单个 ODB + 单个分量）。"""
    cfg = PostProcessConfig(
        odb_path=args.odb[0] if isinstance(args.odb, list) else args.odb,
        output_dir=args.output,
        field_variable=args.field,
        field_component=args.components[0] if isinstance(args.components, list) else args.components,
        legend_min=args.legend_min,
        legend_max=args.legend_max,
        frame_step=args.frame_step,
        video_fps=args.fps,
        make_video=not args.no_video,
        figure_dpi=args.dpi,
    )
    cfg.contour_dir = os.path.join(cfg.output_dir, "contour")
    cfg.curve_dir = os.path.join(cfg.output_dir, "curve")
    cfg.composite_dir = os.path.join(cfg.output_dir, "composite")
    return cfg


def build_configs_for_batch(args) -> List[Tuple[str, str, PostProcessConfig]]:
    """
    从命令行参数生成所有 (odb_path, component, config) 组合。

    Returns:
        [(odb_path, component, cfg), ...] — 每个组合对应一个视频
    """
    odb_paths = args.odb if isinstance(args.odb, list) else [args.odb]
    components = args.components if isinstance(args.components, list) else [args.components]

    combos = []
    for odb_path in odb_paths:
        odb_stem = Path(odb_path).stem  # e.g. "Job-4"
        for comp in components:
            # 每个组合独立输出目录
            combo_dir = os.path.join(args.output, odb_stem, comp)
            video_name = f"{odb_stem}_{comp}_animation.mp4"

            cfg = PostProcessConfig(
                odb_path=odb_path,
                output_dir=combo_dir,
                field_variable=args.field,
                field_component=comp,
                legend_min=args.legend_min,
                legend_max=args.legend_max,
                frame_step=args.frame_step,
                video_fps=args.fps,
                make_video=not args.no_video,
                figure_dpi=args.dpi,
                video_name=video_name,
            )
            cfg.contour_dir = os.path.join(cfg.output_dir, "contour")
            cfg.curve_dir = os.path.join(cfg.output_dir, "curve")
            cfg.composite_dir = os.path.join(cfg.output_dir, "composite")

            combos.append((odb_path, comp, cfg))

    return combos


# ===================================================================
# 模式 2A：Abaqus/CAE 内运行
# ===================================================================

# CAE 模块已在 IN_CAE 检测时一并导入，此处不再重复


def run_cae_mode(
    odb_path: str,
    config: Optional[PostProcessConfig] = None,
):
    """
    模式 2A — 在 Abaqus/CAE 内运行。

    步骤：
      1. 打开 ODB
      2. 创建 Viewport 用于云图
      3. 固定图例范围
      4. 循环 step / frame:
         a. setFrame 切换到当前帧
         b. session.printToFile 保存云图 PNG
         c. 提取 X-Y 数据并绘图
         d. 合成云图 + 曲线图
      5. ffmpeg 合成视频
    """
    if not IN_CAE:
        raise RuntimeError(
            "run_cae_mode() 必须在 Abaqus/CAE 内运行。"
            "请用 standalone 模式：python abaqus_postprocess.py --mode standalone"
        )

    if config is None:
        config = PostProcessConfig(odb_path=odb_path)

    cfg = config
    executeOnCaeStartup()

    # --- 创建输出目录 ---
    contour_dir = ensure_dir(cfg.contour_dir or os.path.join(cfg.output_dir, "contour"))
    curve_dir = ensure_dir(cfg.curve_dir or os.path.join(cfg.output_dir, "curve"))
    composite_dir = ensure_dir(cfg.composite_dir or os.path.join(cfg.output_dir, "composite"))

    # --- 打开 ODB ---
    print(f"[CAE] Open ODB: {odb_path}")
    odb = session.openOdb(name=odb_path, readOnly=True)

    # --- 设置 Viewport ---
    viewport_name = "PostProcess Viewport"
    if viewport_name in session.viewports:
        my_viewport = session.viewports[viewport_name]
    else:
        my_viewport = session.Viewport(name=viewport_name)
    my_viewport.setValues(displayedObject=odb)

    # 可选：设置视图切割、显示组等（按原脚本习惯）
    # my_viewport.odbDisplay.viewCuts["Z-Plane"].setValues(
    #     showFreeBodyCut=True, showModelOnCut=False
    # )
    # my_viewport.odbDisplay.setValues(viewCutNames=("Z-Plane",), viewCut=ON)

    # --- 设定场变量 ---
    odb_display = my_viewport.odbDisplay
    # 先列出可用变量辅助调试
    first_step = list(odb.steps.values())[0]
    avail = list(first_step.frames[0].fieldOutputs.keys())
    print(f"[CAE] Available fields: {avail[:8]}...")
    # 设置主变量 — 顺序尝试 S/SDV1/U，指定积分点位置
    var_ok = False
    candidates = []
    if cfg.field_component and cfg.field_component in ['S11','S22','S33','S12','S13','S23']:
        candidates = [('S', COMPONENT, cfg.field_component), ('S', None, None), ('SDV1', None, None), ('U', None, None)]
    else:
        candidates = [(cfg.field_variable, None, None), ('S', None, None), ('SDV1', None, None), ('U', None, None)]
    for var_label, ref_type, ref_val in candidates:
        try:
            if ref_type:
                odb_display.setPrimaryVariable(
                    variableLabel=var_label,
                    outputPosition=INTEGRATION_POINT,
                    refinement=(ref_type, ref_val),
                )
            else:
                odb_display.setPrimaryVariable(
                    variableLabel=var_label,
                    outputPosition=INTEGRATION_POINT,
                )
            var_ok = True
            print(f"[CAE] Primary variable: {var_label}" + (f" ({ref_val})" if ref_val else ""))
            break
        except Exception:
            continue
    if not var_ok:
        raise RuntimeError(f"Could not set any primary variable. Available: {avail}")

    # --- 固定图例范围 ---
    contour_opts = odb_display.contourOptions
    contour_opts.setValues(
        minAutoCompute=OFF if not cfg.legend_auto_min else ON,
        maxAutoCompute=OFF if not cfg.legend_auto_max else ON,
    )
    if not cfg.legend_auto_min:
        contour_opts.setValues(minValue=cfg.legend_min)
    if not cfg.legend_auto_max:
        contour_opts.setValues(maxValue=cfg.legend_max)
    print(f"[CAE] Legend range: [{cfg.legend_min}, {cfg.legend_max}]")

    # --- 收集要处理的步骤和帧 ---
    steps = list(odb.steps.values())
    if cfg.step_indices is not None:
        steps = [steps[i] for i in cfg.step_indices if i < len(steps)]

    # --- 提取全部历史输出的 (时间, 值) 数据 (供 X-Y 绘图) ---
    history_data_raw = _extract_history_data_cae(odb, cfg)

    # --- 建立 全局帧列表 (时间, step_idx, frame_idx) ---
    global_frames: List[Tuple[float, int, int]] = []
    for si, step in enumerate(steps):
        for fi in range(0, len(step.frames), cfg.frame_step):
            t = step.frames[fi].frameValue
            global_frames.append((t, si, fi))
    # 按时间排序
    global_frames.sort(key=lambda x: x[0])

    print(f"[CAE] {len(global_frames)} frames to process")
    total = len(global_frames)

    # --- 主循环 ---
    for idx, (t, si, fi) in enumerate(global_frames):
        step = steps[si]
        step_name = step.name
        frame_count = fi

        print(f"  [{idx+1}/{total}] Step={step_name}, Frame={fi}, Time={t:.6f}")

        # (a) 切换帧 → 保存云图（Abaqus 自动加 .png 后缀）
        odb_display.setFrame(step=si, frame=fi)
        contour_base = os.path.join(str(contour_dir), f"contour_{idx:05d}")  # 不带扩展名
        session.printToFile(
            fileName=contour_base,
            format=PNG,
            canvasObjects=(my_viewport,),
        )
        contour_png = contour_base + ".png"
        print(f"      contour -> {contour_png}")

        # (b) 绘制累积 X-Y 曲线
        curve_png = os.path.join(str(curve_dir), f"curve_{idx:05d}.png")
        _plot_cumulative_curve_matplotlib(
            global_frames, idx, history_data_raw, cfg,
            output_path=curve_png,
        )
        print(f"      curve   -> {curve_png}")

        # (c) 合成
        composite_png = os.path.join(str(composite_dir), f"composite_{idx:05d}.png")
        _composite_images(contour_png, curve_png, composite_png)
        print(f"      composite -> {composite_png}")

    # --- 合成视频 ---
    if cfg.make_video and total > 0:
        _make_video_ffmpeg(
            str(composite_dir), "composite_%05d.png",
            os.path.join(cfg.output_dir, cfg.video_name),
            fps=cfg.video_fps,
            cleanup=cfg.cleanup_frames_after_video,
        )

    # --- 关闭 ODB ---
    odb.close()
    print(f"[CAE] Done! Output: {cfg.output_dir}")


def _extract_history_data_cae(odb, cfg: PostProcessConfig) -> Dict[str, List[Tuple[float, float]]]:
    """
    从 ODB 提取全部历史输出数据（CAE 模式下直接遍历 odb.steps，与 standalone 共用逻辑）。
    """
    return _extract_history_data_standalone(odb, cfg)


# ===================================================================
# 模式 2B：脱离 Abaqus/CAE，外部 Python 环境
# ===================================================================

def run_standalone_mode(config: PostProcessConfig):
    """
    模式 2B — 脱离 Abaqus/CAE 运行。

    依赖：
      - odbAccess (Abaqus Python API)
      - matplotlib
      - numpy
      - Pillow (可选，用于合成)
    """
    # 在函数内导入，这样 import 脚本时不会报错
    from odbAccess import openOdb
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")  # 无头后端
    import matplotlib.pyplot as plt
    import matplotlib.tri as tri

    cfg = config

    # --- 创建输出目录 ---
    contour_dir = ensure_dir(cfg.contour_dir or os.path.join(cfg.output_dir, "contour"))
    curve_dir = ensure_dir(cfg.curve_dir or os.path.join(cfg.output_dir, "curve"))
    composite_dir = ensure_dir(cfg.composite_dir or os.path.join(cfg.output_dir, "composite"))

    # --- 打开 ODB ---
    print(f"[Standalone] Open ODB: {cfg.odb_path}")
    odb = openOdb(cfg.odb_path, readOnly=True)

    # --- 收集步骤和帧 ---
    steps = list(odb.steps.values())
    if cfg.step_indices is not None:
        steps = [steps[i] for i in cfg.step_indices if i < len(steps)]

    global_frames: List[Tuple[float, int, int]] = []
    for si, step in enumerate(steps):
        for fi in range(0, len(step.frames), cfg.frame_step):
            t = step.frames[fi].frameValue
            global_frames.append((t, si, fi))
    global_frames.sort(key=lambda x: x[0])

    print(f"[Standalone] {len(global_frames)} frames to process")
    total = len(global_frames)

    # --- 提取历史输出 ---
    history_data = _extract_history_data_standalone(odb, cfg)

    # --- 预提取所有帧的节点坐标 + 场值 (Trie 网格) ---
    # 假设网格拓扑不变，只提取第一帧的坐标
    first_step = steps[0]
    first_frame = first_step.frames[0]

    # 获取节点坐标（未变形）
    instance_names = list(odb.rootAssembly.instances.keys())
    if not instance_names:
        raise RuntimeError("ODB 中没有找到任何 instance。")

    # 取第一个 instance 的节点和单元
    inst = odb.rootAssembly.instances[instance_names[0]]
    all_nodes = inst.nodes
    elements = inst.elements
    surface_nodes = None  # 默认：用于 2D 单元

    # --- 对于 C3D8R 等 3D 单元：提取 z≈0 表面用于 2D 云图 ---
    # 判断是否 3D 单元（connectivity > 4）
    if len(elements) > 0 and len(elements[0].connectivity) > 4:
        print("[Standalone] 3D elements -> extracting z~0 surface for 2D plot")

        # 找 z 最小值（模型底面）
        z_coords = np.array([n.coordinates[2] for n in all_nodes])
        z_min = z_coords.min()
        z_tol = (z_coords.max() - z_min) * 0.1 + 1e-9

        # 取 z≈z_min 的节点
        surface_node_labels = set()
        for el in elements:
            conn = list(el.connectivity)
            # 找每个单元中 z 坐标最小的 4 个节点（构成底面四边形）
            node_z = [(lb, all_nodes[lb-1].coordinates[2]) for lb in conn]  # label 1-based
            node_z.sort(key=lambda x: x[1])
            face_nodes = [lb for lb, z in node_z[:4]]
            surface_node_labels.update(face_nodes)

        # 建立 z≈0 表面节点的映射
        surface_nodes = [n for n in all_nodes if n.label in surface_node_labels]
        node_label_to_idx = {n.label: i for i, n in enumerate(surface_nodes)}
        coords_xy = np.array([[n.coordinates[0], n.coordinates[1]] for n in surface_nodes])

        # 从每个 3D 单元提取底面四边形 → 2 个三角形
        triangles = []
        for el in elements:
            conn = list(el.connectivity)
            node_z = [(lb, all_nodes[lb-1].coordinates[2]) for lb in conn]
            node_z.sort(key=lambda x: x[1])
            face_lbs = [lb for lb, z in node_z[:4]]  # 4 surface node labels
            if all(lb in node_label_to_idx for lb in face_lbs):
                a, b, c, d = [node_label_to_idx[lb] for lb in face_lbs]
                triangles.append([a, b, c])
                triangles.append([a, c, d])

        print(f"[Standalone] surface nodes: {len(surface_nodes)}, triangles: {len(triangles)}")
    else:
        # 2D 单元：直接使用全部节点
        node_label_to_idx = {n.label: i for i, n in enumerate(all_nodes)}
        coords_xy = np.array([[n.coordinates[0], n.coordinates[1]] for n in all_nodes])

        triangles = []
        for el in elements:
            conn = list(el.connectivity)
            if len(conn) == 3:
                triangles.append([node_label_to_idx[lb] for lb in conn])
            elif len(conn) == 4:
                triangles.append([node_label_to_idx[conn[0]], node_label_to_idx[conn[1]], node_label_to_idx[conn[2]]])
                triangles.append([node_label_to_idx[conn[0]], node_label_to_idx[conn[2]], node_label_to_idx[conn[3]]])

    triangles = np.array(triangles, dtype=int)
    triangulation = tri.Triangulation(coords_xy[:, 0], coords_xy[:, 1], triangles)

    # --- 主循环 ---
    for idx, (t, si, fi) in enumerate(global_frames):
        step = steps[si]
        step_name = step.name
        frame = step.frames[fi]

        print(f"  [{idx+1}/{total}] Step={step_name}, Frame={fi}, Time={t:.6f}")

        # (a) 云图 — 提取当前帧的场输出并绘制
        contour_png = os.path.join(str(contour_dir), f"contour_{idx:05d}.png")
        _plot_contour_standalone(
            frame, triangulation, cfg, contour_png,
            coords_xy=coords_xy,
            surface_nodes=surface_nodes,
            step_name=step_name,
        )
        print(f"      contour -> {contour_png}")

        # (b) X-Y 曲线
        curve_png = os.path.join(str(curve_dir), f"curve_{idx:05d}.png")
        _plot_cumulative_curve_matplotlib(
            global_frames, idx, history_data, cfg,
            output_path=curve_png,
        )
        print(f"      curve   -> {curve_png}")

        # (c) 合成
        composite_png = os.path.join(str(composite_dir), f"composite_{idx:05d}.png")
        _composite_images(contour_png, curve_png, composite_png)
        print(f"      composite -> {composite_png}")

    # --- 合成视频 ---
    if cfg.make_video and total > 0:
        _make_video_ffmpeg(
            str(composite_dir), "composite_%05d.png",
            os.path.join(cfg.output_dir, cfg.video_name),
            fps=cfg.video_fps,
            cleanup=cfg.cleanup_frames_after_video,
        )

    odb.close()
    print(f"[Standalone] Done! Output: {cfg.output_dir}")


def _extract_history_data_standalone(odb, cfg: PostProcessConfig) -> Dict[str, List[Tuple[float, float]]]:
    """
    从 ODB 提取历史输出 (脱离 CAE) — 并打印数值摘要供校验。
    """
    result: Dict[str, List[Tuple[float, float]]] = {}
    for query in cfg.history_queries:
        name = query["name"]
        region_desc = query["region"]
        var_name = query["variable"]

        data = []
        try:
            for step_name, step in odb.steps.items():
                region = _find_history_region(step, region_desc)
                if region is None:
                    continue
                if var_name in region.historyOutputs:
                    ho = region.historyOutputs[var_name]
                    step_data = list(ho.data)
                    if step_data:
                        data.extend(step_data)
                        print(f"  [HIST] {name} @ {step_name}: {len(step_data)} pts, "
                              f"t=[{step_data[0][0]:.4f}..{step_data[-1][0]:.4f}], "
                              f"val=[{step_data[0][1]:.4e}..{step_data[-1][1]:.4e}]")
            if data:
                result[name] = sorted(data, key=lambda x: x[0])
            else:
                print(f"  [WARN] history '{name}' ({var_name} in {region_desc}): not found in any step")
                # 列出可用的 history regions 帮助排查
                for step_name, step in odb.steps.items():
                    for key in step.historyRegions.keys():
                        if region_desc.lower() in key.lower():
                            ho_keys = list(step.historyRegions[key].historyOutputs.keys())
                            print(f"        candidate {step_name}/{key}: {ho_keys}")
                result[name] = []
        except Exception as e:
            print(f"  [WARN] history extraction '{name}' failed: {e}")
            result[name] = []
    return result


def _find_history_region(step, region_desc: str):
    """
    根据描述字符串在 step.historyRegions 中查找对应的 region。

    region_desc 示例:
      "ASSEMBLY.6"  → 匹配 "Node ASSEMBLY.6"
      "Node rootAssembly Node 1 in NSET RF_TOP"
      "Node PART-1-1.1000"
    """
    # 精确匹配
    for key, region in step.historyRegions.items():
        if region_desc == key:
            return region
    # 子串匹配
    for key, region in step.historyRegions.items():
        if region_desc in key:
            return region
    # 不区分大小写
    region_lower = region_desc.lower()
    for key, region in step.historyRegions.items():
        if region_lower in key.lower():
            return region
    # 模糊匹配：每个单词都在 key 中
    parts = region_desc.split()
    for key, region in step.historyRegions.items():
        if all(p.lower() in key.lower() for p in parts if len(p) > 1):
            return region
    return None


# ===================================================================
# 绘图函数 — 与模式无关
# ===================================================================

def _plot_contour_standalone(
    frame, triangulation, cfg: PostProcessConfig,
    output_path: str, coords_xy,
    surface_nodes=None,  # list of ODB node objects, one per vertex
    step_name="",         # step display name
):
    """
    使用 matplotlib 绘制云图 (standalone 模式) — 支持 2D & 3D 单元（提取表面）。
    通过节点平均法将 ELEMENT_NODAL 位置的场值映射到三角剖分顶点。
    """
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # --- 提取场变量 ---
    try:
        fo = frame.fieldOutputs[cfg.field_variable]
    except KeyError:
        print(f"  [WARN] Field '{cfg.field_variable}' not found, available: {list(frame.fieldOutputs.keys())}")
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, f"No field '{cfg.field_variable}'", ha='center', va='center')
        fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight')
        plt.close(fig)
        return

    # --- 转到 ELEMENT_NODAL 位置 ---
    if hasattr(fo, 'getSubset'):
        try:
            fo_nodal = fo.getSubset(position=ELEMENT_NODAL)
        except Exception:
            fo_nodal = fo
    else:
        fo_nodal = fo

    # --- 确定分量索引 ---
    comp = cfg.field_component  # e.g. "S11", "S22", or None (Mises)
    stress_components = ['S11', 'S22', 'S33', 'S12', 'S13', 'S23']
    if comp and comp in stress_components:
        comp_idx = stress_components.index(comp)
    else:
        comp_idx = None  # → 用 magnitude (Mises)

    # --- 节点平均：累积每个 nodeLabel 的场值 ---
    from collections import defaultdict
    node_vals = defaultdict(list)

    for val in fo_nodal.values:
        nl = val.nodeLabel
        if comp_idx is not None:
            # 提取应力张量的指定分量
            d = val.data
            if hasattr(d, '__getitem__') and len(d) > comp_idx:
                node_vals[nl].append(d[comp_idx])
            elif hasattr(val, 'data') and not hasattr(val.data, '__getitem__'):
                # scalar SDV
                node_vals[nl].append(val.data)
            else:
                node_vals[nl].append(0.0)
        else:
            # Mises / magnitude
            if hasattr(val, 'mises'):
                node_vals[nl].append(val.mises)
            elif hasattr(val, 'magnitude'):
                node_vals[nl].append(val.magnitude)
            elif hasattr(val, 'data'):
                d = val.data
                if hasattr(d, '__getitem__') and not hasattr(d, '__len__'):
                    node_vals[nl].append(float(d))
                else:
                    node_vals[nl].append(float(d) if not hasattr(d, '__getitem__') else 0.0)
            else:
                node_vals[nl].append(0.0)

    # 平均每个节点的值
    node_avg = {nl: np.mean(vals) for nl, vals in node_vals.items()}

    # --- 映射到三角剖分的顶点 ---
    n_vertices = len(coords_xy)
    vertex_values = np.zeros(n_vertices)

    if surface_nodes is not None:
        # 顶点 i → surface_nodes[i].label → node_avg[label]
        for i, node in enumerate(surface_nodes):
            vertex_values[i] = node_avg.get(node.label, 0.0)
    else:
        # 回退：用坐标匹配 (不可靠但作为备选)
        for nl, avg in node_avg.items():
            for i, node in enumerate(surface_nodes if surface_nodes else []):
                if node.label == nl:
                    vertex_values[i] = avg
                    break

    # 如果有顶点值为 0，尝试用非零均值填充
    nonzero = vertex_values != 0
    if not np.any(nonzero):
        all_avg = np.mean(list(node_avg.values())) if node_avg else 0.0
        vertex_values.fill(all_avg)
    else:
        # 为 0 值的顶点用邻居均值填充
        zero_mask = ~nonzero
        if np.any(zero_mask):
            neighbor_avg = np.mean(vertex_values[nonzero])
            vertex_values[zero_mask] = neighbor_avg

    # --- 绘图 (使用顶点值) ---
    fig, ax = plt.subplots(figsize=(10, 7))
    tcf = ax.tricontourf(
        triangulation, vertex_values,
        levels=50,
        vmin=cfg.legend_min,
        vmax=cfg.legend_max,
        cmap='jet',
        extend='both',
    )
    cbar = plt.colorbar(tcf, ax=ax, label=cfg.field_variable, fraction=0.046)
    ax.set_aspect('equal')
    comp_label = f" ({comp})" if comp else ""
    ax.set_title(f"Step: {step_name}, Frame: {frame.frameId}, Time={frame.frameValue:.4f}{comp_label}")

    fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight')
    plt.close(fig)


def _plot_cumulative_curve_matplotlib(
    global_frames: List[Tuple[float, int, int]],
    current_idx: int,
    history_data: Dict[str, List[Tuple[float, float]]],
    cfg: PostProcessConfig,
    output_path: str,
):
    """
    绘制力-位移曲线（累积动画用）。
    横轴 = 位移 (U2)，纵轴 = 反力 (RF2)。
    从 t₀ 到当前帧 tᵢ 累积绘制，当前点红色高亮。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    current_time = global_frames[current_idx][0]

    # --- 从 history_data 中取 U2（位移）和 RF2（反力） ---
    disp_data = history_data.get("U2", [])
    force_data = history_data.get("RF2", [])

    if not disp_data or not force_data:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "No force-displacement data\n(need U2 + RF2)", ha='center', va='center')
        fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight')
        plt.close(fig)
        return

    # 按时间对齐 U2 和 RF2（取交集时间点）
    disp_dict = {t: v for t, v in disp_data}
    force_dict = {t: v for t, v in force_data}
    common_times = sorted(set(disp_dict.keys()) & set(force_dict.keys()))

    if not common_times:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "No overlapping time points", ha='center', va='center')
        fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight')
        plt.close(fig)
        return

    disp_vals = np.array([disp_dict[t] for t in common_times])
    force_vals = np.array([force_dict[t] for t in common_times])

    # 累积：只取时间 ≤ current_time 的数据
    mask = np.array([t <= current_time + 1e-12 for t in common_times])
    d_cum = disp_vals[mask]
    f_cum = force_vals[mask]

    # --- 绘图 ---
    fig, ax = plt.subplots(figsize=(cfg.figure_width_inch * 0.55, cfg.figure_height_inch))
    ax.set_xlabel("Displacement U2 (mm)")
    ax.set_ylabel("Reaction Force RF2 (N)")
    ax.set_title(f"Force–Displacement  (t ≤ {current_time:.4f} s)")
    ax.grid(True, alpha=0.3)

    if len(d_cum) > 0:
        # 历史累积曲线（灰色虚线）
        ax.plot(d_cum[:-1], f_cum[:-1], '-', color='gray', linewidth=0.8, alpha=0.5)
        # 最后一段到当前点（蓝色实线）
        if len(d_cum) >= 2:
            ax.plot(d_cum[-2:], f_cum[-2:], 'b-', linewidth=1.5)
        elif len(d_cum) == 1:
            pass  # 只有一个点，不画线

        # 当前点红色高亮
        ax.scatter(
            [d_cum[-1]], [f_cum[-1]],
            s=cfg.highlight_marker_size,
            c=cfg.highlight_color,
            zorder=5,
            edgecolors='darkred',
            linewidths=1.0,
            label=f"t={current_time:.4f}s",
        )

    # 坐标原点固定在 (0, 0)，上下限各留 5% 余量
    if len(d_cum) > 0:
        f_min, f_max = force_vals.min(), force_vals.max()
        d_min, d_max = disp_vals.min(), disp_vals.max()
        f_range = f_max - f_min or 1.0
        d_range = d_max - d_min or 0.001
        # x 轴: 0 到最大位移 + 5%
        ax.set_xlim(0, d_max + d_range * 0.05)
        # y 轴: 包含 0 和全部力值 + 5%
        y_lo = min(0, f_min) - abs(f_range) * 0.05
        y_hi = max(0, f_max) + abs(f_range) * 0.05
        ax.set_ylim(y_lo, y_hi)

    ax.legend(loc='lower right', fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight')
    plt.close(fig)


def _composite_images(
    contour_path: str,
    curve_path: str,
    output_path: str,
):
    """
    将云图 PNG 和曲线图 PNG 左右拼接成一张图。
    优先使用 Pillow，失败则回退到 matplotlib。
    """
    try:
        from PIL import Image

        img1 = Image.open(contour_path)
        img2 = Image.open(curve_path)

        # 统一高度
        h = max(img1.height, img2.height)
        if img1.height != h:
            ratio = h / img1.height
            new_w = int(img1.width * ratio)
            img1 = img1.resize((new_w, h), Image.LANCZOS)
        if img2.height != h:
            ratio = h / img2.height
            new_w = int(img2.width * ratio)
            img2 = img2.resize((new_w, h), Image.LANCZOS)

        composite = Image.new("RGB", (img1.width + img2.width, h))
        composite.paste(img1, (0, 0))
        composite.paste(img2, (img1.width, 0))
        composite.save(output_path)

    except ImportError:
        # 回退：matplotlib
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7))
        for ax, path in [(ax1, contour_path), (ax2, curve_path)]:
            try:
                img = mpimg.imread(path)
                ax.imshow(img)
            except Exception:
                ax.text(0.5, 0.5, "Image not found", ha='center', va='center')
            ax.axis('off')
        fig.tight_layout(pad=0)
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)


def _make_video_ffmpeg(
    frames_dir: str,
    pattern: str,
    output_path: str,
    fps: int = 10,
    crf: int = 18,
    cleanup: bool = False,
):
    """
    调用 ffmpeg 将图片序列合成为 MP4 视频。
    """
    import subprocess
    import shutil

    # 检查 ffmpeg 是否可用
    if not shutil.which("ffmpeg"):
        print("[WARN] ffmpeg not found, skip video. Install ffmpeg first.")
        return

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, pattern),
        "-c:v", "mpeg4", "-q:v", "5",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    print(f"[Video] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[Video] generated: {output_path}")
    else:
        print(f"[ERROR] ffmpeg failed:\n{result.stderr}")

    if cleanup:
        import glob
        frames = glob.glob(os.path.join(frames_dir, pattern.replace("%05d", "*")))
        for f in frames:
            os.remove(f)
        print(f"[Video] cleaned {len(frames)} frame files")


# ===================================================================
# 便捷入口
# ===================================================================

def quick_run_cae(odb_name: str = "Job-4"):
    """
    在 Abaqus/CAE 中快速运行的便捷函数。
    从同目录 FEM_config.py 读取路径配置（如果存在）。

    用法 (在 CAE 命令行中):
        >>> exec(open('abaqus_postprocess.py').read())
        >>> quick_run_cae('Job-4')
    """
    # 尝试从 FEM_config 读取目录
    try:
        from FEM_config import abaqus_run_dir, model_name, base_dir
        odb_path = os.path.join(abaqus_run_dir, f"{odb_name}.odb")
        output_dir = os.path.join(base_dir, "postprocess", odb_name)
    except ImportError:
        odb_path = f"{odb_name}.odb"
        output_dir = f"postprocess_{odb_name}"

    print(f"ODB: {odb_path}")
    print(f"Output: {output_dir}")

    # 从模型推断合理的图例范围
    # SDV1 = 损伤变量，范围 [0, 1]
    # S Mises = 应力
    cfg = PostProcessConfig(
        odb_path=odb_path,
        output_dir=output_dir,
        field_variable="SDV1",        # 损伤变量
        field_component=None,         # 标量
        legend_min=0.0,
        legend_max=1.0,
        frame_step=1,
        video_fps=15,
        figure_dpi=150,
    )
    cfg.contour_dir = os.path.join(cfg.output_dir, "contour")
    cfg.curve_dir = os.path.join(cfg.output_dir, "curve")
    cfg.composite_dir = os.path.join(cfg.output_dir, "composite")

    # 配置历史输出查询
    cfg.history_queries = [
        {
            "name": "RF3",
            "region": "Node rootAssembly Node 1 in NSET RF_TOP",
            "variable": "RF3",
        },
        {
            "name": "U3",
            "region": "Node rootAssembly Node 1 in NSET RF_TOP",
            "variable": "U3",
        },
    ]

    run_cae_mode(odb_path, cfg)


def quick_run_standalone(odb_name: str = "Job-4"):
    """
    脱离 CAE 的便捷入口。
    用法:
        $ abaqus python abaqus_postprocess.py  # 或
        $ python abaqus_postprocess.py --odb Job-4.odb --mode standalone
    """
    # 尝试从 FEM_config 读取
    try:
        from FEM_config import abaqus_run_dir, model_name, base_dir
        odb_path = os.path.join(abaqus_run_dir, f"{odb_name}.odb")
        output_dir = os.path.join(base_dir, "postprocess", odb_name)
    except ImportError:
        odb_path = f"{odb_name}.odb"
        output_dir = f"postprocess_{odb_name}"

    cfg = PostProcessConfig(
        odb_path=odb_path,
        output_dir=output_dir,
        field_variable="SDV1",
        field_component=None,
        legend_min=0.0,
        legend_max=1.0,
        frame_step=1,
        video_fps=15,
    )
    cfg.contour_dir = os.path.join(cfg.output_dir, "contour")
    cfg.curve_dir = os.path.join(cfg.output_dir, "curve")
    cfg.composite_dir = os.path.join(cfg.output_dir, "composite")

    run_standalone_mode(cfg)


# ===================================================================
# __main__
# ===================================================================

if __name__ == "__main__":
    if IN_CAE:
        # Abaqus/CAE 内运行
        # 用法: abaqus cae noGUI=abaqus_postprocess.py -- --odb Job-4.odb --components S11
        args = parse_args()
        odb_paths = args.odb if isinstance(args.odb, list) else [args.odb]
        components = args.components if isinstance(args.components, list) else [args.components]
        if len(odb_paths) > 1 or len(components) > 1:
            # 批量
            from pathlib import Path as _Path
            for odb_path in odb_paths:
                odb_stem = _Path(odb_path).stem
                for comp in components:
                    combo_dir = os.path.join(args.output, odb_stem, comp)
                    video_name = f"{odb_stem}_{comp}_animation.mp4"
                    cfg = PostProcessConfig(
                        odb_path=odb_path, output_dir=combo_dir,
                        field_variable=args.field, field_component=comp,
                        legend_min=args.legend_min, legend_max=args.legend_max,
                        frame_step=args.frame_step, video_fps=args.fps,
                        make_video=not args.no_video, figure_dpi=args.dpi,
                        video_name=video_name,
                    )
                    cfg.contour_dir = os.path.join(cfg.output_dir, "contour")
                    cfg.curve_dir = os.path.join(cfg.output_dir, "curve")
                    cfg.composite_dir = os.path.join(cfg.output_dir, "composite")
                    print(f"\n=== [CAE] {odb_path} / {comp} ===")
                    run_cae_mode(odb_path, cfg)
        else:
            # 单个 ODB + 单个分量
            odb_stem = Path(odb_paths[0]).stem
            comp = components[0]
            combo_dir = os.path.join(args.output, odb_stem, comp)
            cfg = PostProcessConfig(
                odb_path=odb_paths[0], output_dir=combo_dir,
                field_variable=args.field, field_component=comp,
                legend_min=args.legend_min, legend_max=args.legend_max,
                frame_step=args.frame_step, video_fps=args.fps,
                make_video=not args.no_video, figure_dpi=args.dpi,
                video_name=f"{odb_stem}_{comp}_animation.mp4",
            )
            cfg.contour_dir = os.path.join(cfg.output_dir, "contour")
            cfg.curve_dir = os.path.join(cfg.output_dir, "curve")
            cfg.composite_dir = os.path.join(cfg.output_dir, "composite")
            run_cae_mode(odb_paths[0], cfg)
    else:
        # 外部 Python (abaqus python) — 解析参数
        args = parse_args()
        cfg = build_config_from_args(args)
        run_standalone_mode(cfg)


# ===================================================================
# 附录：3D 模型备选方案 (pyvista)
# ===================================================================
#
# 如果模型是 3D，matplotlib 三角剖分不再适用。推荐 pyvista：
#
#   pip install pyvista
#
#   import pyvista as pv
#   import numpy as np
#
#   def plot_contour_3d(frame, cfg, output_path):
#       '''用 pyvista 渲染 3D 云图'''
#       fo = frame.fieldOutputs[cfg.field_variable]
#       fo_nodal = fo.getSubset(position=ELEMENT_NODAL)
#
#       # 构建 pyvista 网格
#       inst = frame.odb.rootAssembly.instances[list(frame.odb.rootAssembly.instances.keys())[0]]
#       nodes = np.array([[n.coordinates[0], n.coordinates[1], n.coordinates[2]]
#                          for n in inst.nodes])
#       # 单元连接 ...
#       # (此处省略完整 3D 网格构建，项目为 2D 故不展开)
#
#       plotter = pv.Plotter(off_screen=True, window_size=[1600, 1200])
#       plotter.add_mesh(mesh, scalars=values, cmap='jet',
#                        clim=[cfg.legend_min, cfg.legend_max])
#       plotter.screenshot(output_path)
#       plotter.close()
