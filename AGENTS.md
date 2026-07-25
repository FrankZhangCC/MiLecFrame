# AGENTS.md

## 最高优先级指令

- 使用简体中文（zh-CN）呈现思维链。
- 当发现指令不清晰时，不要擅自揣测，而是向用户发送问题。
- 所有代码应当详细注释。
- 新增代码时，除非必要，不要删除旧有注释。
- 每次执行任务后都要执行语法检查：`python -m py_compile` 校验所有被修改的 `.py` 文件。
- 在执行任务后，可以通过写测试代码的方式，检查新增或修改的代码是否真实起作用，特别是在涉及到GUI窗口修改的时候。
- 在排查问题时，积极使用debug log的方式进行问题定位，必要时让用户执行操作后再读取debug log。
- 所有命令在虚拟环境中执行：先运行 `.\venv\Scripts\activate`（Windows PowerShell）。

## 架构速览

```
src/
  main.py              ← CLI 入口（单张 / 批量；默认启动 PySide6 GUI）
  core/                ← ImageProcessor → FrameRenderer / HDRHandler / Decorator / BatchProcessor
  gui_legacy/          ← Streamlit GUI（已封存）
  gui_pyside/          ← PySide6 + QFluentWidgets 原生桌面 GUI（当前默认）
  utils/               ← 工具层（ExifHelper, DeviceMapper, FontManager, LayoutEngine,
                         BackgroundFillManager, RenderContext, logging_config）
  frame_styles/
    style_manager.py   ← 样式加载 & 变体匹配
    configs/           ← YAML/JSON/TOML 样式配置文件；_STYLE_TEMPLATE.txt 是新建样式的填空模板
```

### 关键入口点

| 场景        | 命令                                                                            |
| ----------- | ------------------------------------------------------------------------------- |
| 单张处理    | `python src/main.py -i <in> -o <out> -s <style> --author "..." --bg-fill ...` |
| 批量处理    | `python src/main.py --batch -i <dir> -o <dir> --recursive`                    |
| GUI（默认） | `python src/main.py`（启动 PySide6 桌面窗口）                                 |
| 环境搭建    | `python setup_env.py`（创建 venv + 安装依赖）                                 |

## 没有测试/检查框架

- **`tests/` 目录为空**，无 pytest、unittest 或其他测试框架。不要尝试运行测试。
- **无 lint / typecheck / formatter 配置**：没有 pyproject.toml、setup.cfg、.flake8、pre-commit 等。
- 唯一可执行的校验是 `python -m py_compile <file>` 检查 Python 语法。

## 必须知道的约定

### 版本标记规范

- `src/_version.py` 是版本号**单点入口**。
- 公开 Release 版：标记为 `v0.x.x`（如 `v0.1.0`）。
- 内部开发版：标记为 `v1.x.x-dev`（如 `v1.9.0-dev`）。
- 版本号变更时，修改 `src/_version.py` 并同步更新 `README.md` 徽标和 `CHANGELOG.md`。

### Git 分支工作流

采用三线分支模型：

```
mainline ─── v1.0.1-dev ─── v1.1.0-dev ─── ... ─── v2.3.0-dev ──→  (干净版本线)
                ↑ squash                        ↑ squash
dev ─────── A---B---C---D---E---F---G---H---I── ... ──────────────→  (日常开发)
                                                                      ↓ 稳定后 cherry-pick
release ─── v0.1.0 ─── v1.0.0 ─── v1.1.0-release ──→               (公开发行)
```

| 分支 | 用途 | 规则 |
|------|------|------|
| `dev` | **日常小功能开发** | 提交可松散。**不在此分支打 tag**。只在本机，不推送到 `origin`。 |
| `mainline` | **版本里程碑线** | 每 commit = 一版本，带 `v*.*.*-dev` tag。推送到 `origin`，历史不可改写（force push 需谨慎）。 |
| `release` | **稳定公开发行** | GitHub 默认分支，受保护。推送到 `origin`，仅接收 cherry-pick 来的稳定版本。 |

#### 日常操作流程

```bash
# 1. 日常在 dev 上工作
git checkout dev
# ...多次提交 A, B, C, D ...

# 2. 凑够一个版本后 → squash 到 mainline 并打 tag
git checkout mainline
git merge --squash dev
VERSION="v2.4.0-dev"  # 根据 src/_version.py 决定
git commit -m "$VERSION: <功能简述>"
git tag $VERSION
git checkout dev

# 3. 推送到 GitHub
git push origin mainline --follow-tags    # 推送分支 + 新 tag
# 若 --follow-tags 未推送轻量 tag，补推：
git push origin --tags

# 4. mainline 上某版本准备公开发布 → 给 release
git checkout release
git cherry-pick <mainline上对应版本的commit-hash>
git tag v2.4.0
git push origin release --tags
```

#### 推送规则

| 分支 | 推送到 origin | 方式 |
|------|--------------|------|
| `dev` | ❌ 否（仅本地） | - |
| `mainline` | ✅ 是 | `git push origin mainline --follow-tags` |
| `release` | ✅ 是（默认分支） | `git push origin release` |

- **`release` 是 GitHub 默认分支**，受保护，禁止 force push。
- `mainline` 的 `*-dev` tag 在推送时会被 `--follow-tags` 自动带到远端。
- 推送 tag 时如遇 `--follow-tags` 未生效（轻量 tag），补 `git push origin --tags`。
- 历史管理注意事项

### Git 忽略规则

- `data/` 目录下除 `camera_map.csv` 和 `lens_map.csv` 外均被 gitignore。
- `assets/fonts/*` 被 gitignore（除 `.gitkeep`），字体文件需自行放置。
- `test_images/`、`debug_log.txt`、`output_test*.jpg` 被 gitignore。
- `.vscode/` 被 gitignore。

### 核心设计模式

- **BackgroundFillManager**（`src/utils/background_fill.py`）是背景填充类型的**唯一入口**。新增填充类型只需在 `FILL_TYPES` 注册表中注册，GUI 下拉和 CLI 自动同步。不要在 renderer.py 或 GUI 中硬编码 bg 选项。
- **RenderContext**（`src/utils/render_context.py`）是渲染文本数据的**统一入口**。渲染器只调用 `context.get_text(key)`，不直接接触 EXIF 数据。
- **样式变体系统**：样式可组织为文件夹（文件夹名 = 样式名），内含 `default.yaml`、`no_location.yaml` 等变体。`StyleManager._resolve_style_variant()` 自动根据数据可用性选择最佳变体。
- **`_STYLE_TEMPLATE.txt`**（`src/frame_styles/configs/`）覆盖全部配置项，填写后交给 AI 即可生成 YAML 配置文件。

### ExpandGroupSettingCard 开发铁律

在往 `ExpandGroupSettingCard` 内添加自定义内容时，必须逐条检查：

1. **必须通过 `addGroupWidget()` 或 `addGroup()` 添加子控件。**
   禁止直接操作 `self.viewLayout.addWidget()`。
   否则 `_adjustViewSize()` 中的 `self.widgets` 列表为空，卡片无法正常展开/收回。

2. **子控件的 `sizeHint().height()` 必须能反映其真实视觉高度。**
   - `QScrollArea` / `SmoothScrollArea` 的 `sizeHint()` **不反映** `setFixedHeight()`。
   - `FlowLayout` 的 `sizeHint()` 仅取最大子控件尺寸，非网格总高度。
   - 若子控件用了 `setFixedHeight()` 或非标准布局，必须覆盖 `_adjustViewSize()`。

3. **覆盖 `_adjustViewSize()` 时，使用子控件的实际高度来源：**
   - QScrollArea → `maximumHeight()`（而非 `sizeHint().height()`）。
   - FlowLayout → `heightForWidth(w)`（而非 `sizeHint().height()`）。

4. **覆盖模板（必须带注释说明为何覆盖）：**
   ```python
   def _adjustViewSize(self):
       # QScrollArea.sizeHint() 不反映 setFixedHeight()，手动指定
       h = self._my_widget.maximumHeight() + 3
       self.spaceWidget.setFixedHeight(h)
       if self.isExpand:
           self.setFixedHeight(self.card.height() + h)
   ```

5. **动态添加/删除子控件后调用 `QTimer.singleShot(0, self._adjustViewSize)`。**

6. **开发完成后调用 `layout_debug.dump_expand_card(self)` 验证：**
   - 收起时 `card.height() == card.card.height()`（无底部间隙）。
   - 展开时 `spaceWidget.h >= view.h`（滚动范围充足）。

### 配置与数据

- `config.json`：保存用户偏好（作者名自动记忆）。
- `project_master_spec.json`：**最高优先级**的底层需求规范，所有开发必须严格遵循。
- `data/camera_map.csv` ⟷ `data/lens_map.csv`：设备映射数据库，CSV 格式，GUI 中可编辑。

### 日志

- DEBUG 级别 → `debug_log.txt`（项目根目录）
- INFO 及以上 → 控制台 stderr
- 入口点（CLI/GUI）均已调用 `setup_logging()`，带幂等守卫。

### GUI 重构计划

- PySide6 + QFluentWidgets 重构计划详见 **[`docs/GUI_REFACTORING_PLAN.md`](./docs/GUI_REFACTORING_PLAN.md)**。
- 该文档包含：原 GUI 功能逻辑总结、重构架构设计、QFluentWidgets 组件映射表、数据模型设计、内存管理方案、实施步骤等全部规划内容。
- 开发 GUI 时必须严格遵循该文档，特别是 **全面使用 QFluentWidgets 组件、禁用 Qt 原生界面组件** 的规则。
- 阅读 [https://qfluentwidgets.com/zh/pages/componentlist](https://qfluentwidgets.com/zh/pages/componentlist) 了解QFluentWidgets包含的可用组件列表。
- 阅读官方API文档 [https://pyqt-fluent-widgets.readthedocs.io/zh-cn/latest/autoapi/qfluentwidgets/index.html](https://pyqt-fluent-widgets.readthedocs.io/zh-cn/latest/autoapi/qfluentwidgets/index.html) 了解组件详细说明。

### 命令执行环境

- Shell 是 **Windows PowerShell 5.1**，不支持 `&&` 连接命令。使用 `; if ($?) { ... }` 替代。
- 所有 Python 命令必须在 venv 激活后执行。
- 使用绝对路径执行 Python 脚本，避免路径混淆。
