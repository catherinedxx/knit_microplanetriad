#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Abaqus ODB 3D post-process: deformed solid + contour + force-displacement curve + MP4.

Usage:
  abq2022 python code/abaqus_postprocess.py --odb results/Job-4.odb --components S11 S22 --legend-min 0 --legend-max 300000
  abq2022 python code/abaqus_postprocess.py --odb results/Job-4.odb results/Job-5.odb results/Job-6.odb --components S11 S22 --output results/postprocess
"""
from __future__ import print_function

import os
import sys
import argparse

# ===================================================================
# Config
# ===================================================================

class Config(object):
    def __init__(self, **kw):
        self.odb_path = kw.get("odb_path", "Job-4.odb")
        self.output_dir = kw.get("output_dir", "postprocess_output")
        self.field_variable = kw.get("field_variable", "S")
        self.field_component = kw.get("field_component", None)
        self.legend_min = kw.get("legend_min", None)
        self.legend_max = kw.get("legend_max", None)
        self.frame_step = kw.get("frame_step", 1)
        self.step_indices = kw.get("step_indices", None)
        self.step_filter = kw.get("step_filter", None)  # resolved in run()
        # History
        self.history_queries = kw.get("history_queries", [
            {"name": "RF2", "region": "ASSEMBLY.6", "variable": "RF2"},
            {"name": "U2",  "region": "ASSEMBLY.6", "variable": "U2"},
        ])
        # Plot
        self.figure_dpi = kw.get("figure_dpi", 150)
        self.figure_width_inch = kw.get("figure_width_inch", 18.0)
        self.figure_height_inch = kw.get("figure_height_inch", 6.0)
        self.highlight_marker_size = kw.get("highlight_marker_size", 80)
        self.highlight_color = kw.get("highlight_color", "red")
        # View
        self.deform_scale = kw.get("deform_scale", 1.0)
        self.view_elev = kw.get("view_elev", 20.0)
        self.view_azim = kw.get("view_azim", -60.0)
        # Video
        self.make_video = kw.get("make_video", True)
        self.video_fps = kw.get("video_fps", 10)
        self.video_name = kw.get("video_name", "animation.mp4")

    def setup_dirs(self):
        self.contour_dir = os.path.join(self.output_dir, "contour")
        self.curve_dir = os.path.join(self.output_dir, "curve")
        self.composite_dir = os.path.join(self.output_dir, "composite")


# ===================================================================
# CLI
# ===================================================================

def parse_args():
    p = argparse.ArgumentParser(description="Abaqus ODB 3D post-process")
    p.add_argument("--odb", type=str, nargs="+", default=["Job-4.odb"])
    p.add_argument("--components", type=str, nargs="+", default=["S11"])
    p.add_argument("--output", type=str, default="postprocess_output")
    p.add_argument("--field", type=str, default="S")
    p.add_argument("--legend-min", type=float, default=None)
    p.add_argument("--legend-max", type=float, default=None)
    p.add_argument("--frame-step", type=int, default=1)
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--deform-scale", type=float, default=1.0)
    p.add_argument("--view-elev", type=float, default=20.0)
    p.add_argument("--view-azim", type=float, default=-60.0)
    p.add_argument("--step", type=str, nargs="+", default=None,
                   help="Step filter: index (1-based) or name, e.g. --step 2 or --step Step-2")
    args, _ = p.parse_known_args()
    return args


def build_configs(args):
    odb_paths = args.odb if isinstance(args.odb, list) else [args.odb]
    components = args.components if isinstance(args.components, list) else [args.components]

    # Resolve --step to indices (deferred: need ODB to match names)
    step_filter = None
    if args.step is not None:
        step_filter = args.step  # list of str, resolved in run()

    combos = []
    for odb_path in odb_paths:
        stem = os.path.splitext(os.path.basename(odb_path))[0]
        for comp in components:
            cfg = Config(
                odb_path=odb_path,
                output_dir=os.path.join(args.output, stem, comp),
                field_variable=args.field,
                field_component=comp,
                legend_min=args.legend_min,
                legend_max=args.legend_max,
                frame_step=args.frame_step,
                video_fps=args.fps,
                make_video=not args.no_video,
                figure_dpi=args.dpi,
                video_name="{}_{}_animation.mp4".format(stem, comp),
                deform_scale=args.deform_scale,
                view_elev=args.view_elev,
                view_azim=args.view_azim,
                step_filter=step_filter,
            )
            cfg.setup_dirs()
            combos.append((odb_path, comp, cfg))
    return combos


# ===================================================================
# History extraction
# ===================================================================

def _find_history_region(step, region_desc):
    for key, region in step.historyRegions.items():
        if region_desc == key:
            return region
    for key, region in step.historyRegions.items():
        if region_desc in key:
            return region
    rlower = region_desc.lower()
    for key, region in step.historyRegions.items():
        if rlower in key.lower():
            return region
    parts = region_desc.split()
    for key, region in step.historyRegions.items():
        if all(p.lower() in key.lower() for p in parts if len(p) > 1):
            return region
    return None


def extract_history(odb, cfg):
    result = {}
    for q in cfg.history_queries:
        name, rdesc, vname = q["name"], q["region"], q["variable"]
        data = []
        for _, step in odb.steps.items():
            reg = _find_history_region(step, rdesc)
            if reg and vname in reg.historyOutputs:
                ho = reg.historyOutputs[vname]
                sd = list(ho.data)
                if sd:
                    data.extend(sd)
                    print("  [HIST] {} @ {}: {} pts, t=[{:.4f}..{:.4f}]".format(
                        name, step.name, len(sd), sd[0][0], sd[-1][0]))
        result[name] = sorted(data, key=lambda x: x[0]) if data else []
    return result


# ===================================================================
# 3D mesh
# ===================================================================

_HEX_FACES = [
    [0, 1, 2, 3], [4, 7, 6, 5],
    [0, 4, 5, 1], [1, 5, 6, 2],
    [2, 6, 7, 3], [3, 7, 4, 0],
]


def build_hex_mesh(odb):
    import numpy as np
    inst = odb.rootAssembly.instances[list(odb.rootAssembly.instances.keys())[0]]
    all_nodes, elements = inst.nodes, inst.elements
    label_to_idx = {n.label: i for i, n in enumerate(all_nodes)}
    nodes_coords = np.array([[n.coordinates[0], n.coordinates[1], n.coordinates[2]]
                             for n in all_nodes])
    elem_labels, elem_node_idxs = [], []
    for el in elements:
        conn = list(el.connectivity)
        if len(conn) < 4:
            continue
        elem_labels.append(el.label)
        elem_node_idxs.append(tuple(label_to_idx[lb] for lb in conn))
    print("[Mesh] nodes={}, elements={}".format(len(all_nodes), len(elem_labels)))
    return {"nodes_coords": nodes_coords, "elem_labels": elem_labels,
            "elem_node_idxs": elem_node_idxs, "label_to_idx": label_to_idx}


# ===================================================================
# Coordinate transform: 90° around X, then Z-rotate CCW
# ===================================================================

def _rotate_coords(points, z_rotate_deg=45.0):
    """Rotate 90 deg around X: (X,Y,Z) -> (X, Z, -Y),
    then z_rotate_deg CCW around the new Z axis."""
    import numpy as np
    r = points.copy()
    # Step 1: 90 deg around X
    x1 = r[:, 0].copy()
    y1 = r[:, 2].copy()
    z1 = -r[:, 1].copy()
    # Step 2: z_rotate_deg CCW around Z
    theta = np.radians(z_rotate_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    r[:, 0] = x1 * cos_t - y1 * sin_t
    r[:, 1] = x1 * sin_t + y1 * cos_t
    r[:, 2] = z1
    return r


# ===================================================================
# Global bounding box (fixed axes)
# ===================================================================

def compute_global_bbox(odb, steps, nodes_coords, label_to_idx, cfg, global_frames):
    import numpy as np

    all_def = [_rotate_coords(nodes_coords)]
    indices = sorted(set([0, 1, len(global_frames) - 2, len(global_frames) - 1] +
                         list(range(2, len(global_frames) - 2, max(len(global_frames) // 5, 1)))))[:12]

    for idx in indices:
        _, si, fi = global_frames[idx]
        frame = steps[si].frames[fi]
        deformed = nodes_coords.copy()
        if "U" in frame.fieldOutputs:
            for v in frame.fieldOutputs["U"].values:
                nl = v.nodeLabel
                if nl in label_to_idx:
                    try:
                        d = v.dataDouble
                    except Exception:
                        d = v.data
                    if hasattr(d, '__getitem__') and len(d) >= 3:
                        i = label_to_idx[nl]
                        deformed[i] += cfg.deform_scale * np.array([float(d[0]), float(d[1]), float(d[2])])
        all_def.append(_rotate_coords(deformed))

    x = np.concatenate([d[:, 0] for d in all_def])
    y = np.concatenate([d[:, 1] for d in all_def])
    z = np.concatenate([d[:, 2] for d in all_def])
    pad = 0.05
    bbox = (x.min() - (x.max() - x.min()) * pad, x.max() + (x.max() - x.min()) * pad,
            y.min() - (y.max() - y.min()) * pad, y.max() + (y.max() - y.min()) * pad,
            z.min() - (z.max() - z.min()) * pad, z.max() + (z.max() - z.min()) * pad)
    print("[BBox] x=[{:.3f}..{:.3f}] y=[{:.3f}..{:.3f}] z=[{:.3f}..{:.3f}]".format(*bbox))
    return bbox


# ===================================================================
# 3D contour plot
# ===================================================================

def plot_contour_3d(frame, cfg, output_path, hex_mesh, step_name, bbox):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    nodes_coords = hex_mesh["nodes_coords"]
    elem_labels = hex_mesh["elem_labels"]
    elem_node_idxs = hex_mesh["elem_node_idxs"]
    label_to_idx = hex_mesh["label_to_idx"]

    # --- Deform ---
    deformed = nodes_coords.copy()
    if "U" in frame.fieldOutputs:
        for v in frame.fieldOutputs["U"].values:
            nl = v.nodeLabel
            if nl in label_to_idx:
                try:
                    d = v.dataDouble
                except Exception:
                    d = v.data
                if hasattr(d, '__getitem__') and len(d) >= 3:
                    i = label_to_idx[nl]
                    deformed[i] += cfg.deform_scale * np.array([float(d[0]), float(d[1]), float(d[2])])

    # Rotate 90 deg around X + 45 deg CCW around Z
    rotated = _rotate_coords(deformed)

    # --- Field values ---
    comp = cfg.field_component
    stress_comps = ['S11', 'S22', 'S33', 'S12', 'S13', 'S23']
    comp_idx = stress_comps.index(comp) if comp in stress_comps else None

    elem_values = np.zeros(len(elem_labels))
    if cfg.field_variable in frame.fieldOutputs:
        fo = frame.fieldOutputs[cfg.field_variable]
        elabel_to_val = {}
        for v in fo.values:
            el = v.elementLabel
            try:
                d = v.data
                if comp_idx is not None and hasattr(d, '__getitem__'):
                    vv = float(d[comp_idx])
                elif hasattr(v, 'mises'):
                    vv = float(v.mises)
                elif hasattr(d, '__float__'):
                    vv = float(d)
                elif hasattr(d, '__getitem__') and len(d) > 0:
                    vv = float(d[0])
                else:
                    vv = float(d)
            except Exception:
                try:
                    d = v.dataDouble
                    if comp_idx is not None and hasattr(d, '__getitem__'):
                        vv = float(d[comp_idx])
                    elif hasattr(v, 'mises'):
                        vv = float(v.mises)
                    else:
                        vv = float(d)
                except Exception:
                    vv = 0.0
            elabel_to_val[el] = vv
        for i, el in enumerate(elem_labels):
            elem_values[i] = elabel_to_val.get(el, 0.0)

    mask = np.isnan(elem_values)
    elem_values[mask] = 0.0
    mask = np.isinf(elem_values)
    elem_values[mask] = 0.0
    if cfg.legend_min is not None and cfg.legend_max is not None:
        elem_values = np.clip(elem_values, cfg.legend_min, cfg.legend_max)

    # --- Build faces ---
    faces, face_colors = [], []
    cmap = plt.cm.jet
    vmin, vmax = cfg.legend_min, cfg.legend_max
    vr = vmax - vmin if vmax != vmin else 1.0

    for ei in range(len(elem_labels)):
        norm = max(0.0, min(1.0, (elem_values[ei] - vmin) / vr))
        color = cmap(norm)
        nidx = list(elem_node_idxs[ei])
        for fl in _HEX_FACES:
            faces.append([rotated[nidx[fi]] for fi in fl])
            face_colors.append(color)

    # --- Figure (size computed from bbox for correct proportions) ---
    dx = bbox[1] - bbox[0] or 1.0
    dy = bbox[3] - bbox[2] or 1.0
    dz = bbox[5] - bbox[4] or 1.0
    fig_w = 12.0
    fig_h = fig_w * (dz + 0.4 * dy) / (dx + 0.4 * dy)
    fig_h = max(4.0, min(16.0, fig_h))
    fig = plt.figure(figsize=(fig_w, fig_h))
    ax = fig.add_subplot(111, projection='3d')
    ax.add_collection3d(Poly3DCollection(faces, facecolors=face_colors,
                                         edgecolors='k', linewidths=0.1, alpha=1.0))
    ax.view_init(elev=cfg.view_elev, azim=cfg.view_azim)
    ax.set_xlim(bbox[0], bbox[1])
    ax.set_ylim(bbox[2], bbox[3])
    ax.set_zlim(bbox[4], bbox[5])
    try:
        ax.set_box_aspect([dx, dy, dz])
    except AttributeError:
        pass  # older matplotlib — figsize approximation above
    # --- Clean view: no axes, panes, or background ---
    ax.set_axis_off()
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor('none')
    ax.yaxis.pane.set_edgecolor('none')
    ax.zaxis.pane.set_edgecolor('none')
    ax.grid(False)

    # Label
    if comp and comp in stress_comps:
        clabel = "{} (Pa)".format(comp)
    elif cfg.field_variable.startswith("S"):
        clabel = "{} (Pa)".format(cfg.field_variable)
    elif cfg.field_variable.startswith("SDV"):
        clabel = cfg.field_variable
    else:
        clabel = "{} (mm)".format(cfg.field_variable)

    ax.set_title("{}\nStep: {}  Frame: {}  Time={:.4f}  ".format(
        comp if comp else cfg.field_variable,
        step_name, frame.frameId, frame.frameValue),
        fontsize=24, y=0.85)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.40, aspect=20, pad=-0.5)
    cbar.set_label(clabel, fontsize=20)
    cbar.ax.tick_params(labelsize=16)
    # Shift colorbar upward vertically
    cpos = cbar.ax.get_position()
    cbar.ax.set_position([cpos.x0, cpos.y0 + 0.3, cpos.width, cpos.height])
    fig.tight_layout(pad=0.05)
    fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)


# ===================================================================
# Force-displacement curve
# ===================================================================

def plot_curve(global_frames, current_idx, history_data, cfg, output_path,
               step_name="", frame=None):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['font.serif'] = ['Times New Roman']

    current_time = global_frames[current_idx][0]
    disp_data = history_data.get("U2", [])
    force_data = history_data.get("RF2", [])

    if not disp_data or not force_data:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "No U2+RF2 data", ha='center', va='center')
        fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight')
        plt.close(fig)
        return

    disp_dict, force_dict = {t: v for t, v in disp_data}, {t: v for t, v in force_data}
    common = sorted(set(disp_dict) & set(force_dict))
    if not common:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "No overlapping time", ha='center', va='center')
        fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight')
        plt.close(fig)
        return

    dv, fv = np.array([disp_dict[t] for t in common]), np.array([force_dict[t] for t in common])
    mask = np.array([t <= current_time + 1e-12 for t in common])
    dc, fc = dv[mask], fv[mask]

    fig, ax = plt.subplots(figsize=(cfg.figure_width_inch * 0.55, cfg.figure_height_inch))
    ax.set_xlabel("U2 (mm)", fontsize=28)
    ax.set_ylabel("RF2 (N)", fontsize=28)
    ax.set_title("Force-Displacement\nStep: {}  Frame: {}  Time={:.4f}".format(
        step_name, frame.frameId if frame else "?", current_time), fontsize=26)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis='both', labelsize=24)

    if len(dc) > 0:
        if len(dc) > 1:
            ax.plot(dc[:-1], fc[:-1], '-', color='gray', lw=0.8, alpha=0.5)
        if len(dc) >= 2:
            ax.plot(dc[-2:], fc[-2:], 'b-', lw=1.5)
        ax.scatter([dc[-1]], [fc[-1]], s=cfg.highlight_marker_size,
                   c=cfg.highlight_color, zorder=5, edgecolors='darkred',
                   linewidths=1.0, label="t={:.4f}s".format(current_time))
        dr = dv.max() - dv.min() or 0.001
        fr = fv.max() - fv.min() or 1.0
        ax.set_xlim(0, dv.max() + dr * 0.05)
        ax.set_ylim(0, max(0, fv.max()) + abs(fr) * 0.05)
        # ax.set_ylim(min(0, fv.min()) - abs(fr) * 0.05,
        #             max(0, fv.max()) + abs(fr) * 0.05)
    ax.legend(loc='lower right', fontsize=24)
    fig.tight_layout()
    fig.savefig(output_path, dpi=cfg.figure_dpi, bbox_inches='tight')
    plt.close(fig)


# ===================================================================
# Composite (left-right): curve left, contour right
# ===================================================================

def composite_vertical(curve_path, contour_path, output_path):
    try:
        from PIL import Image
        img_curve = Image.open(curve_path)
        img_contour = Image.open(contour_path)

        # Scale curve: match contour height, then shrink width to 30%
        curve_h = img_contour.height
        curve_ratio = float(img_curve.width) / max(img_curve.height, 1)
        curve_w = int(curve_h * curve_ratio)
        img_curve = img_curve.resize((curve_w, curve_h), Image.LANCZOS)
        # Further shrink curve width to ~30% of contour width
        target_cw = int(img_contour.width * 0.30)
        if curve_w > target_cw:
            curve_h2 = int(curve_h * float(target_cw) / curve_w)
            img_curve = img_curve.resize((target_cw, curve_h2), Image.LANCZOS)

        total_w = img_curve.width + img_contour.width
        total_h = max(img_curve.height, img_contour.height)
        out = Image.new("RGB", (total_w, total_h), (255, 255, 255))
        # Curve on left, vertically centered
        out.paste(img_curve, (0, (total_h - img_curve.height) // 2))
        out.paste(img_contour, (img_curve.width, 0))
        out.save(output_path)
    except ImportError:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        plt.rcParams['font.family'] = 'serif'
        plt.rcParams['font.serif'] = ['Times New Roman']
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8),
                                       gridspec_kw={'width_ratios': [0.25, 0.75]})
        for ax, path in [(ax1, curve_path), (ax2, contour_path)]:
            try:
                ax.imshow(mpimg.imread(path))
            except Exception:
                ax.text(0.5, 0.5, "?", ha='center', va='center')
            ax.axis('off')
        fig.tight_layout(pad=0.5)
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)


# ===================================================================
# Video
# ===================================================================

def make_video(frames_dir, pattern, output_path, fps=10):
    import subprocess
    try:
        subprocess.call(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception:
        print("[WARN] ffmpeg not found, skip video.")
        return
    cmd = ["ffmpeg", "-y", "-framerate", str(fps),
           "-i", os.path.join(frames_dir, pattern),
           "-c:v", "mpeg4", "-q:v", "5", "-crf", "18",
           "-pix_fmt", "yuv420p", output_path]
    print("[Video] {}".format(" ".join(cmd)))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = proc.communicate()
    if proc.returncode == 0:
        print("[Video] {}".format(output_path))
    else:
        print("[ERROR] ffmpeg: {}".format(stderr))


# ===================================================================
# Main
# ===================================================================

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def _compute_field_range(steps, global_frames, cfg):
    """Pre-scan all frames to compute global field min/max for consistent colorbar."""
    import numpy as np

    comp = cfg.field_component
    stress_comps = ['S11', 'S22', 'S33', 'S12', 'S13', 'S23']
    comp_idx = stress_comps.index(comp) if comp in stress_comps else None

    all_vals = []
    for _, si, fi in global_frames:
        frame = steps[si].frames[fi]
        if cfg.field_variable in frame.fieldOutputs:
            fo = frame.fieldOutputs[cfg.field_variable]
            for v in fo.values:
                try:
                    d = v.data
                    if comp_idx is not None and hasattr(d, '__getitem__'):
                        vv = float(d[comp_idx])
                    elif hasattr(v, 'mises'):
                        vv = float(v.mises)
                    elif hasattr(d, '__float__'):
                        vv = float(d)
                    elif hasattr(d, '__getitem__') and len(d) > 0:
                        vv = float(d[0])
                    else:
                        vv = float(d)
                except Exception:
                    try:
                        d = v.dataDouble
                        if comp_idx is not None and hasattr(d, '__getitem__'):
                            vv = float(d[comp_idx])
                        elif hasattr(v, 'mises'):
                            vv = float(v.mises)
                        else:
                            vv = float(d)
                    except Exception:
                        continue
                all_vals.append(vv)

    if all_vals:
        arr = np.array(all_vals)
        arr = arr[np.isfinite(arr)]
        if len(arr) > 0:
            arr.sort()
            # Use 2nd-98th percentile to exclude stress-concentration outliers
            lo = float(arr[int(len(arr) * 0.02)])
            hi = float(arr[int(len(arr) * 0.98)])
            # If range is zero (uniform field), expand slightly
            if abs(hi - lo) < 1e-12:
                lo -= 1.0
                hi += 1.0
            return lo, hi
    return 0.0, 1.0


def run(cfg):
    from odbAccess import openOdb

    ensure_dir(cfg.contour_dir)
    ensure_dir(cfg.curve_dir)
    ensure_dir(cfg.composite_dir)

    print("[ODB] {}".format(cfg.odb_path))
    odb = openOdb(cfg.odb_path, readOnly=True)

    mesh = build_hex_mesh(odb)

    steps = list(odb.steps.values())
    # Resolve --step filter (indices or names)
    if cfg.step_filter is not None:
        step_names = [s.name for s in steps]
        indices = []
        for token in cfg.step_filter:
            try:
                # 1-based index: --step 2
                idx = int(token) - 1
                if 0 <= idx < len(steps):
                    indices.append(idx)
            except ValueError:
                # Name match: --step Step-2
                for i, nm in enumerate(step_names):
                    if token.lower() in nm.lower():
                        indices.append(i)
        if indices:
            steps = [steps[i] for i in sorted(set(indices))]
            print("[Step filter] {}".format([s.name for s in steps]))
    elif cfg.step_indices is not None:
        steps = [steps[i] for i in cfg.step_indices if i < len(steps)]

    global_frames = []
    for si, step in enumerate(steps):
        for fi in range(0, len(step.frames), cfg.frame_step):
            global_frames.append((step.frames[fi].frameValue, si, fi))
    # Keep step grouping: process Step-1 all frames first, then Step-2, etc.

    total = len(global_frames)
    print("[Frames] {}".format(total))
    if total == 0:
        odb.close()
        return

    bbox = compute_global_bbox(odb, steps, mesh["nodes_coords"],
                               mesh["label_to_idx"], cfg, global_frames)
    hist = extract_history(odb, cfg)

    # --- Pre-scan: compute global field range for consistent colorbar ---
    if cfg.legend_min is None or cfg.legend_max is None:
        gmin, gmax = _compute_field_range(steps, global_frames, cfg)
        if cfg.legend_min is None:
            cfg.legend_min = gmin
        if cfg.legend_max is None:
            cfg.legend_max = gmax
        print("[Legend] auto range: [{:.4f}, {:.4f}]".format(cfg.legend_min, cfg.legend_max))

    for idx, (t, si, fi) in enumerate(global_frames):
        step = steps[si]
        frame = step.frames[fi]
        print("  [{}/{}] {} frame={} t={:.6f}".format(idx + 1, total, step.name, fi, t))

        cpng = os.path.join(cfg.contour_dir, "contour_{:05d}.png".format(idx))
        plot_contour_3d(frame, cfg, cpng, mesh, step.name, bbox)

        kpng = os.path.join(cfg.curve_dir, "curve_{:05d}.png".format(idx))
        plot_curve(global_frames, idx, hist, cfg, kpng, step.name, frame)

        epng = os.path.join(cfg.composite_dir, "composite_{:05d}.png".format(idx))
        composite_vertical(kpng, cpng, epng)

    if cfg.make_video and total > 0:
        make_video(cfg.contour_dir, "contour_%05d.png",
                   os.path.join(cfg.output_dir, "contour_" + cfg.video_name), fps=cfg.video_fps)
        make_video(cfg.curve_dir, "curve_%05d.png",
                   os.path.join(cfg.output_dir, "curve_" + cfg.video_name), fps=cfg.video_fps)
        make_video(cfg.composite_dir, "composite_%05d.png",
                   os.path.join(cfg.output_dir, cfg.video_name), fps=cfg.video_fps)

    odb.close()
    print("[Done] {}".format(cfg.output_dir))


if __name__ == "__main__":
    args = parse_args()
    combos = build_configs(args)
    print("=== {} combinations ===".format(len(combos)))
    for odb_p, comp, cfg in combos:
        print("  {} / {} -> {}".format(odb_p, comp, cfg.output_dir))
    print()
    for odb_p, comp, cfg in combos:
        print("\n=== {} / {} ===".format(odb_p, comp))
        run(cfg)
