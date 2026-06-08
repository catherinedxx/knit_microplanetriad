# Abaqus Post-Process Script

`abaqus_postprocess.py` — 从 Abaqus ODB 文件批量生成**云图 + 力-位移曲线**合成动画。

## 功能

1. 遍历所有 step / frame，保存**固定图例范围**的云图 PNG（保证动画颜色一致）
2. 提取历史输出，生成**累积力-位移曲线**（当前点红色高亮）
3. 云图 + 曲线**左右拼接**为合成图
4. **ffmpeg 合成 MP4 视频**（可选）
5. **批量处理**：多个 ODB × 多个场分量 → 自动笛卡尔积

## 依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Abaqus | ODB 读取 / CAE 渲染 | 已安装的 Abaqus |
| matplotlib | standalone 模式云图 + 曲线 | Abaqus 内置 Python 自带 |
| numpy | 数值计算 | Abaqus 内置 Python 自带 |
| Pillow | 图像拼接 | Abaqus 内置 Python 自带 |
| ffmpeg | 合成 MP4 视频 | [ffmpeg.org](https://ffmpeg.org) 下载，放入 PATH |

## 两种运行模式

### 模式 2A：Abaqus/CAE 内运行（推荐，云图质量最好）

**使用 Abaqus Python 内核**（`abaqus cae`），由 Abaqus 原生渲染云图。

```bash
# 单个 ODB，单个分量
abaqus cae noGUI=code/abaqus_postprocess.py -- \
    --odb results/Job-4_upgraded.odb \
    --components S11 \
    --output results/postprocess \
    --legend-min 0 --legend-max 50

# 批量：3 工况 × 2 应力分量 = 6 个视频
abaqus cae noGUI=code/abaqus_postprocess.py -- \
    --odb results/Job-4_upgraded.odb results/Job-5_upgraded.odb results/Job-6_upgraded.odb \
    --components S11 S22 \
    --output results/postprocess \
    --legend-min 0 --legend-max 50
```

**特点**：
- 云图由 Abaqus 渲染（高质量、完整图例）
- 需要 Abaqus CAE license
- S/S11/S22 要求 ODB 输出 `position=CENTROID` 或 `ELEMENT_NODAL`（C3D8R 默认 `INTEGRATION_POINT` 不支持）

### 模式 2B：Abaqus Python 环境（无需 CAE license）

**使用 Abaqus Python 解释器**（`abaqus python`），matplotlib 绘制云图。

```bash
# 单个 ODB
abaqus python code/abaqus_postprocess.py \
    --odb results/Job-4_upgraded.odb \
    --components S11 \
    --output results/postprocess \
    --legend-min 0 --legend-max 50

# 批量
abaqus python code/abaqus_postprocess.py \
    --odb results/Job-4_upgraded.odb results/Job-5_upgraded.odb results/Job-6_upgraded.odb \
    --components S11 S22 \
    --output results/postprocess \
    --legend-min 0 --legend-max 50
```

**特点**：
- 无需 CAE license（只需要 Abaqus Solver license）
- C3D8R 减缩积分单元的 S/S11/S22 可以正常提取（从 `INTEGRATION_POINT` 外推）
- 云图为 matplotlib 渲染（质量略低于 Abaqus 原生）

## 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--odb` | 多值 | `Job-4.odb` | ODB 文件路径，空格分隔多个 |
| `--components` | 多值 | `S11` | 应力/场分量，每个生成独立视频 |
| `--output` | 字符串 | `postprocess_output` | 输出根目录 |
| `--field` | 字符串 | `S` | 场变量名（S / SDV1 / U 等） |
| `--legend-min` | 浮点 | `0.0` | 图例下限（固定以保证动画颜色一致） |
| `--legend-max` | 浮点 | `100.0` | 图例上限 |
| `--frame-step` | 整数 | `1` | 每隔几帧取一张（1=全部） |
| `--fps` | 整数 | `10` | 视频帧率 |
| `--no-video` | 标志 | false | 仅生成帧图，不合成视频 |
| `--dpi` | 整数 | `150` | 曲线图 DPI（仅 standalone 模式） |

## 输出结构

每个 (ODB, 分量) 组合生成独立子目录：

```
postprocess_output/
├── Job-4/
│   ├── S11/
│   │   ├── contour/          ← 云图 PNG 序列
│   │   │   contour_00000.png
│   │   │   contour_00001.png
│   │   │   ...
│   │   ├── curve/            ← 力-位移曲线 PNG 序列
│   │   │   curve_00000.png
│   │   │   curve_00001.png
│   │   │   ...
│   │   ├── composite/        ← 左右合成图 PNG 序列
│   │   │   composite_00000.png
│   │   │   ...
│   │   └── Job-4_S11_animation.mp4   ← 合成视频
│   └── S22/
│       └── Job-4_S22_animation.mp4
├── Job-5/
│   ├── S11/ → Job-5_S11_animation.mp4
│   └── S22/ → Job-5_S22_animation.mp4
└── Job-6/
    ├── S11/ → Job-6_S11_animation.mp4
    └── S22/ → Job-6_S22_animation.mp4
```

## 配置历史输出

脚本通过 `history_queries` 配置提取哪些 X-Y 数据。默认为力-位移曲线：

```python
history_queries: [
    {"name": "RF2", "region": "ASSEMBLY.6", "variable": "RF2"},
    {"name": "U2",  "region": "ASSEMBLY.6", "variable": "U2"},
]
```

**如果历史输出提取失败**，先运行诊断脚本查看可用数据：

```bash
abaqus python code/_debug_history.py
```

然后修改脚本中 `PostProcessConfig` 的 `history_queries` 列表。

## 常见问题

### ODB 版本太旧

```
OdbError: The database is from a previous release of Abaqus.
```

解决方法：升级 ODB

```bash
abaqus -upgrade -job results/Job-4_upgraded -odb results/Job-4.odb
```

### CAE 模式 S/S11 渲染失败

```
VisError: Primary Variable not available: 'S' at element nodes.
```

原因：C3D8R 减缩积分单元默认只在 `INTEGRATION_POINT` 输出应力，CAE 无法渲染。

解决方案：
1. **修改 inp 文件**，添加 `position=CENTROID`：
   ```diff
   - *Output, field
   + *Output, field, position=CENTROID
   ```
2. **或用模式 2B**（`abaqus python`），matplotlib 可以从积分点外推。
3. **或用 SDV 变量**：`--field SDV1 --components ""`

### CAE 模式 Unicode 编码错误

```
Failed to encode Unicode object to locale
```

脚本已将所有运行时 print 转为 ASCII，此问题已修复。

### ffmpeg 未找到

```
[WARN] ffmpeg not found, skip video.
```

下载 ffmpeg 并加入 PATH，或用 `--no-video` 跳过视频合成。

### 找不到历史输出

```
[WARN] history 'RF2' (RF2 in ASSEMBLY.6): not found in any step
```

运行诊断脚本检查实际可用的 history regions：

```bash
abaqus python code/_debug_history.py
```

根据输出修改 `history_queries` 配置。

## 诊断工具

| 脚本 | 用途 |
|------|------|
| `code/_debug_odb.py` | 查看 ODB 结构（instance、单元类型、steps、field outputs） |
| `code/_debug_history.py` | 查看所有 history regions 和 outputs |
| `code/_debug_s.py` | 查看 S 和 SDV1 字段详情（位置、分量、数值范围） |

## 图例范围建议

| 场变量 | 推荐范围 | 说明 |
|--------|----------|------|
| S Mises | 0 ~ 50 | 应力（MPa），根据实际调整 |
| S11 / S22 | -20 ~ 20 | 正应力分量（拉为正，压为负） |
| SDV1 | 0 ~ 1 | 损伤变量 |
| SDV1 ~ SDV40 | 查看 VUMAT 定义 | 用户自定义状态变量 |
