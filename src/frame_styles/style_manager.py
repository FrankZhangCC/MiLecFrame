# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式管理器模块
负责管理相框样式配置文件
"""
import os
import json
import copy
import yaml
import toml
from pathlib import Path
from typing import Dict, Optional, List
import logging

# 统一的路径定位工具：
# - 内置样式目录为只读资源，随程序打包（_MEIPASS/src/frame_styles/configs）
# - 打包环境下用户新建样式保存在 exe 同目录 styles/（可写，升级不丢失）
from src.utils.app_paths import get_resource_root, get_app_dir, is_frozen
# 竖图旋转适配样式默认值校验（可选顶层字段，方案 §5.5 双层校验的第 1 层）
from src.utils.orientation_adaptation import validate_style_default
# 定位语义校验已拆分至独立纯函数模块（计划 §4.0：StyleManager 只保留
# 薄包装做日志输出；本文件不再直接依赖 layout_engine 定位枚举）
from src.frame_styles import style_validator
from src.frame_styles import style_rules
# 共享变体规则与数据结构（计划 §4.1/§4.2：来源定位结果与选择逻辑的
# 单一实现；GUI 能力查询与渲染加载共用同一套候选与选择规则）
from src.frame_styles.style_rules import (
    VariantCandidate,
    StyleSource,
    parse_missing_fields,
    select_variant_candidate,
)


class StyleManager:
    """相框样式管理器"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化样式管理器
        
        Args:
            config_dir: 样式配置文件目录
        """
        if config_dir:
            # 显式指定目录时保持原有行为（不附加额外目录）
            self.config_dir = config_dir
            self.extra_dirs: List[str] = []
        else:
            # 内置样式目录：开发环境与打包环境统一指向资源目录
            self.config_dir = str(get_resource_root() / 'src' / 'frame_styles' / 'configs')
            # 打包环境下附加用户样式目录（exe 同目录 styles/），用户自建样式可持久保存
            self.extra_dirs = []
            if is_frozen():
                self.extra_dirs.append(str(get_app_dir() / 'styles'))
        
        self.logger = logging.getLogger(__name__)

        # ── 文件级加载缓存（计划 §4.4：减少重复 parse 与重复调用）──
        # 键 = os.path.normcase 规范化的绝对路径（Windows 大小写不敏感，
        # 防止同一文件产生两个缓存键）；值 = 已校验且已注入默认值的配置。
        # 读取一律返回 deepcopy：ImageProcessor 会修改本次配置的
        # fonts.weight，返回缓存对象本身会被跨调用污染（C16 断言）。
        # 当前全部调用方为单线程（GUI 主线程 / CLI 串行批量），不加锁；
        # 若未来引入后台线程访问，必须先补并发评估。
        self._config_cache: Dict[str, Dict] = {}
        # 来源与候选枚举缓存：键 = (样式名, extra_dirs 序列, config_dir)。
        # extra_dirs 参与键构造：测试/运行期动态调整目录列表时自动失效，
        # 不依赖调用方记得清缓存（防脏缓存的防御性设计）。
        self._source_cache: Dict[tuple, StyleSource] = {}

    def _iter_style_dirs(self, style_name: str):
        """
        按优先级依次产出可能存在指定样式的目录（用户目录优先于内置目录）

        Args:
            style_name: 样式名称

        Yields:
            样式目录路径（仅产出实际存在的目录）
        """
        for base in self.extra_dirs + [self.config_dir]:
            d = os.path.join(base, style_name)
            if os.path.isdir(d):
                yield d

    def get_available_styles(self) -> List[str]:
        """
        获取所有可用的样式名称
        
        同时扫描单文件样式和文件夹样式（文件夹内包含变体配置），
        并合并内置目录与用户目录（用户目录同名样式优先，内置同名自动隐藏）
        
        Returns:
            样式名称列表
        """
        styles = []
        hidden = set()  # 用户目录已提供的内置同名样式
        
        for base in [*self.extra_dirs, self.config_dir]:
            if not os.path.exists(base):
                continue
            
            for entry_name in os.listdir(base):
                entry_path = os.path.join(base, entry_name)
                
                if os.path.isdir(entry_path):
                    # 文件夹样式：文件夹名即为样式名
                    if entry_name in hidden:
                        continue
                    if base != self.config_dir:
                        hidden.add(entry_name)  # 用户目录样式屏蔽内置同名
                    if entry_name not in styles:
                        styles.append(entry_name)
                elif entry_name.endswith(('.json', '.yaml', '.yml', '.toml')):
                    # 单文件样式：文件名（去扩展名）即为样式名
                    style_name = os.path.splitext(entry_name)[0]
                    if style_name in hidden:
                        continue
                    if base != self.config_dir:
                        hidden.add(style_name)
                    if style_name not in styles:
                        styles.append(style_name)
        
        return sorted(styles)
    

    def list_style_files(self, extensions=('.yaml',),
                         include_hidden: bool = False) -> List[str]:
        """
        枚举样式文件的相对路径（G9：样式编辑器枚举单点）

        与 get_available_styles() 的样式名枚举互补：本方法返回文件级
        相对路径——文件夹样式含变体文件（如 'FilmClip/default.yaml'），
        单文件样式为 'Xxx.yaml'。目录优先级与 get_available_styles()
        一致：用户目录（extra_dirs）在前，同名条目屏蔽内置同名。

        契约说明：样式编辑器当前只实现 YAML 的加载与保存，默认
        extensions 仅 '.yaml'；json/toml 等其他支持格式的编辑属后续
        扩展，编辑器不做静默格式转换。

        Args:
            extensions: 接受的扩展名集合（小写、含点）
            include_hidden: 是否包含 '_' 前缀条目（编辑器语义默认
                过滤——临时/内部文件不入可选列表）

        Returns:
            排序后的相对路径列表（正斜杠分隔，跨平台一致）
        """
        exts = tuple(e.lower() for e in extensions)
        results = []
        seen = set()
        for base in [*self.extra_dirs, self.config_dir]:
            base_path = Path(base)
            if not base_path.exists():
                continue
            for entry in sorted(os.listdir(base)):
                if entry.startswith('_') and not include_hidden:
                    continue
                full = base_path / entry
                if full.is_dir():
                    if entry in seen:
                        continue
                    seen.add(entry)
                    for variant in sorted(os.listdir(str(full))):
                        if variant.lower().endswith(exts)                                 and not variant.startswith('_'):
                            results.append(f'{entry}/{variant}')
                elif entry.lower().endswith(exts):
                    if entry in seen:
                        continue
                    seen.add(entry)
                    results.append(entry)
        return sorted(results)

    def resolve_style_file(self, rel_path: str) -> str:
        """
        按用户目录优先级解析样式文件相对路径（G9：GUI 解析单点）

        顺序与 get_style_config 一致：extra_dirs 优先，回退内置
        config_dir；都不存在时返回第一个用户可写目录下的拼接结果
        （供保存使用，调用方自行判断存在性）。

        Args:
            rel_path: 样式文件相对路径（如 'FilmClip/default.yaml'）

        Returns:
            实际文件绝对路径（正斜杠分隔）
        """
        bases = self.extra_dirs or [self.config_dir]
        for base in [*bases, self.config_dir]:
            candidate = Path(base) / rel_path
            if candidate.exists():
                return str(candidate)
        return str(Path(bases[0]) / rel_path)

    def _load_config_file(self, config_path: str) -> Optional[Dict]:
        """加载单个配置文件（带文件级缓存，计划 §4.4）

        实测（T6 记录）：加载成本 99.8% 在文件读取 + parse，校验仅 0.01 ms；
        缓存命中返回 deepcopy（0.03 ms）替代重复 parse（4.2 ms），约百倍。
        必须深拷贝：ImageProcessor 会修改本次配置的 fonts.weight，返回
        缓存对象本身会被跨调用污染（C16 断言）。
        加载失败（语法错误/校验拒绝）不缓存：坏文件修复后无需显式失效
        即恢复，且每次重读持续暴露错误日志便于定位。

        Returns:
            已通过校验并注入默认字段的配置深拷贝；失败返回 None
        """
        cache_key = os.path.normcase(os.path.abspath(config_path))
        cached = self._config_cache.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)

        ext = os.path.splitext(config_path)[1].lower()
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if ext == '.json':
                    config = json.load(f)
                elif ext in ('.yaml', '.yml'):
                    config = yaml.safe_load(f)
                elif ext == '.toml':
                    config = toml.load(f)
                else:
                    return None

            if not isinstance(config, dict):
                self.logger.error(f"配置文件格式错误，应为字典类型: {config_path}")
                return None

            if self._validate_config(config, config_path):
                # 注入默认字段后的配置进入缓存；返回深拷贝隔离本次调用
                self._config_cache[cache_key] = config
                return copy.deepcopy(config)
            else:
                self.logger.error(f"样式配置无效: {config_path}")
                return None

        except Exception as e:
            self.logger.error(f"读取样式配置失败 {config_path}: {str(e)}")
            return None

    def invalidate(self, path: Optional[str] = None) -> None:
        """失效缓存（计划 §4.4：新鲜度由显式失效点保证，不做 mtime/监听）

        Args:
            path: 给定文件路径时仅失效该文件的配置缓存；因同目录内容
                  可能已变化，来源枚举缓存一并整体失效。None（或缺省）
                  时全部失效。
        """
        if path is None:
            self._config_cache.clear()
            self._source_cache.clear()
            return
        self._config_cache.pop(os.path.normcase(os.path.abspath(path)), None)
        self._source_cache.clear()

    def invalidate_all(self) -> None:
        """失效全部文件与来源缓存（GUI refresh/showEvent/生成前调用）"""
        self.invalidate(None)

    def _scan_directory_candidates(self, style_dir: str, style_name: str) -> StyleSource:
        """枚举目录内配置文件候选（计划 §4.1/§4.2）

        保持拆分前行为：四种小写后缀（.json/.yaml/.yml/.toml，大小写
        敏感的 endswith）、不递归、不过滤 '_' 前缀隐藏文件、保持原始
        listdir 顺序（default 兜底与首文件兜底都依赖该顺序）。
        空目录产出空候选序列并给出诊断。
        """
        names = [f for f in os.listdir(style_dir)
                 if f.endswith(('.json', '.yaml', '.yml', '.toml'))]
        diagnostics = []
        if not names:
            diagnostics.append(f"样式文件夹内无有效配置文件: {style_name}")
        candidates = tuple(
            VariantCandidate(
                path=os.path.join(style_dir, fname),
                filename=fname,
                ordinal=ordinal,
                required_missing=parse_missing_fields(fname),
            )
            for ordinal, fname in enumerate(names)
        )
        return StyleSource(kind='directory', path=style_dir,
                           candidates=candidates, diagnostics=tuple(diagnostics))

    def resolve_style_source(self, style_name: str) -> StyleSource:
        """定位样式的最终配置来源（计划 §4.1：能力查询与加载共用同一位置）

        查找顺序与拆分前 get_style_config 逐字一致：
        1. 目录样式优先：按 extra_dirs 现有顺序检查，再查 config_dir；
           高优先级目录一旦存在即采用——目录为空或选中的文件损坏也
           不转向其他同名来源；
        2. 无目录样式才查单文件：每个目录内按 .json/.yaml/.yml/.toml
           顺序查找；
        3. 都不存在 → kind='missing'。

        只分析最终来源，不合并其他目录或同名单文件的能力。结果缓存：
        键含 (extra_dirs 序列, config_dir)，目录列表动态变化时自动
        失效（防脏缓存的防御性设计）；显式失效走 invalidate/invalidate_all。
        """
        cache_key = (style_name, tuple(self.extra_dirs), self.config_dir)
        cached = self._source_cache.get(cache_key)
        if cached is not None:
            return cached

        # 1. 目录样式（用户目录优先于内置目录）
        for base in [*self.extra_dirs, self.config_dir]:
            style_dir = os.path.join(base, style_name)
            if os.path.isdir(style_dir):
                source = self._scan_directory_candidates(style_dir, style_name)
                self._source_cache[cache_key] = source
                return source

        # 2. 单文件样式（向后兼容，用户目录优先）
        for base in [*self.extra_dirs, self.config_dir]:
            for ext in ('.json', '.yaml', '.yml', '.toml'):
                config_path = os.path.join(base, f"{style_name}{ext}")
                if os.path.exists(config_path):
                    source = StyleSource(kind='single_file', path=config_path)
                    self._source_cache[cache_key] = source
                    return source

        source = StyleSource(
            kind='missing', path='',
            diagnostics=(f"样式配置文件不存在: {style_name}",))
        self._source_cache[cache_key] = source
        return source

    def _resolve_style_variant(self, style_dir: str, context: Optional[Dict]) -> Optional[str]:
        """（兼容包装）根据上下文从文件夹中选取最佳变体配置文件

        选择逻辑已收敛至 style_rules.select_variant_candidate（计划 §4.2
        单一实现：条件候选按文件名排序、同分取排序后首个；default 兜底
        与首文件兜底均按原始枚举顺序；组合条件评分展开见 IMPLIED_MISSING）。
        本包装每次独立扫描目录（不走路由缓存），供既有调用方与 T0 基线
        比对使用；渲染加载路径经 get_style_config → resolve_style_source。
        """
        if not os.path.isdir(style_dir):
            return None
        source = self._scan_directory_candidates(
            style_dir, style_name=os.path.basename(style_dir))
        picked = select_variant_candidate(source.candidates, context)
        return picked.path if picked else None

    def get_style_config(self, style_name: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """获取指定样式的配置，支持文件夹变体选择（共享来源与选择规则）

        Args:
            style_name: 样式名称
            context: 上下文信息，如 {'location': '北京', 'author': '张三'}
                     用于从文件夹样式中选取最佳变体配置

        Returns:
            样式配置字典，如果不存在则返回 None
        """
        source = self.resolve_style_source(style_name)
        if source.kind == 'directory':
            if not source.candidates:
                # 高优先级目录存在但为空：与拆分前一致，报错且不跨来源回退
                for diag in source.diagnostics:
                    self.logger.error(diag)
                return None
            picked = select_variant_candidate(source.candidates, context)
            return self._load_config_file(picked.path)
        if source.kind == 'single_file':
            return self._load_config_file(source.path)
        # missing
        self.logger.error(f"样式配置文件不存在: {style_name}")
        return None

    def get_style_capabilities(self, style_name: str):
        """获取样式家族能力快照（计划 §5.1；GUI 选项启禁的数据来源）

        由门面层负责取得来源、逐候选调用现有 _load_config_file（命中
        4.4 缓存时为深拷贝、无重复 parse），再交给 style_rules 能力分析
        区提取结果——分析区不反向导入本类，也不接触 GUI。加载失败的
        候选仍保留身份与文件名条件（§5.3），让共享选择器照常选择。

        Returns:
            StyleCapabilitySnapshot（不可变）；样式不存在时 candidates
            为空、diagnostics 说明原因
        """
        source = self.resolve_style_source(style_name)
        facts_seq = []
        extra_diags = list(source.diagnostics)
        if source.kind == 'missing':
            extra_diags.append(f"样式配置文件不存在: {style_name}")
        else:
            facts_iter = source.candidates if source.kind == 'directory' else (
                # 单文件样式：构造单候选（无文件名条件）
                (VariantCandidate(
                    path=source.path,
                    filename=os.path.basename(source.path),
                    ordinal=0,
                    required_missing=parse_missing_fields(
                        os.path.basename(source.path)),
                ),)
            )
            for cand in facts_iter:
                config = self._load_config_file(cand.path)
                load_diag = () if config is not None else (
                    f'配置加载失败（语法或校验错误）: {cand.filename}，'
                    '详见 debug 日志',)
                facts_seq.append(
                    style_rules.analyze_variant(config, cand, load_diag))
        return style_rules.build_capability_snapshot(
            style_name, source, tuple(facts_seq), tuple(extra_diags))

    # ── 定位语义校验（position / alignment / cross_alignment）──
    # 校验逻辑已拆分至 style_validator（计划 §4.0：纯函数、无日志副作用）；
    # 此处只保留薄包装：输出 `[StyleValidation]` 前缀日志并返回布尔值，
    # 错误文本与顺序与拆分前逐字一致（T0 基线逐条比对验收）。

    def _validate_positioning(self, config: Dict, source: str = "") -> bool:
        """遍历五类定位元素执行新语义校验（委托 style_validator 共享实现）"""
        all_errors = style_validator.validate_positioning(config, source)
        for err in all_errors:
            src = f"[{source}] " if source else ""
            self.logger.error(f"[StyleValidation] {src}{err}")
        return not all_errors


    def _validate_config(self, config: Dict, source: str = '') -> bool:
        """
        验证配置是否有效
        
        Args:
            config: 配置字典
            
        Returns:
            配置是否有效
        """
        # 检查必需字段
        required_keys = ['name', 'layout']
        for key in required_keys:
            if key not in config:
                self.logger.error(f"配置缺少必需字段: {key}")
                return False
        
        # 确保layout是字典类型
        if not isinstance(config['layout'], dict):
            self.logger.error("layout字段应为字典类型")
            return False
            
        layout = config['layout']
        
        # 检查布局配置
        if 'expand_canvas' not in layout or not isinstance(layout['expand_canvas'], dict):
            layout['expand_canvas'] = {
                'enabled': False,
                'top': 0,
                'bottom': 0,
                'left': 0,
                'right': 0
            }
        
        # 检查信息位置配置
        if 'info_position' not in layout or not isinstance(layout['info_position'], dict):
            # 代码内默认配置直接使用唯一新 schema（九点 position + 九点 alignment）
            layout['info_position'] = {
                'exif': {'placement': 'outside', 'position': 'bottom-center', 'alignment': 'top-center', 'margin': 10},
                'author': {'placement': 'outside', 'position': 'bottom-center', 'alignment': 'top-center', 'margin': 10},
                'location': {'placement': 'outside', 'position': 'bottom-center', 'alignment': 'top-center', 'margin': 10}
            }
        else:
            # info_position 已有配置，不再注入默认条目
            # 渲染器按 info_position 中实际配置的元素驱动渲染
            pass
        
        # 检查颜色配置
        if 'colors' not in config or not isinstance(config['colors'], dict):
            config['colors'] = {
                'text': '#000000'
            }
        
        # 检查字体配置
        if 'fonts' not in config or not isinstance(config['fonts'], dict):
            config['fonts'] = {}
        else:
            # 确保字体大小配置存在
            if 'sizes' not in config['fonts'] or not isinstance(config['fonts']['sizes'], dict):
                config['fonts']['sizes'] = {}
            # 确保行间距配置存在
            if 'line_spacing_ratio' not in config['fonts']:
                config['fonts']['line_spacing_ratio'] = 0.005

        # 竖图旋转适配默认值校验（可选顶层字段；缺失=none，非法值
        # 如布尔/null/大小写变体/未知字符串时拒绝加载该样式）
        try:
            validate_style_default(config)
        except ValueError as e:
            self.logger.error(f"配置字段非法: {e}")
            return False

        # 语义版本开关检查：positioning_semantics 已随旧算法一并删除，
        # 出现即拒绝（不启用任何旧路径，提示直接删除该字段并迁移到新语义）
        if 'positioning_semantics' in config:
            self.logger.error(
                f"[StyleValidation] positioning_semantics="
                f"{config.get('positioning_semantics')!r}: "
                f"该语义版本开关字段已删除，运行时只有唯一一套定位算法；"
                f"请删除此字段并按新 schema 迁移 position/alignment"
                f"（参见 docs/plans/POSITION_ALIGNMENT_REPAIR_EXECUTION_PLAN.md §2）")
            return False

        # 定位语义校验：五类定位元素的 position/alignment/cross_alignment
        # 枚举与组合；旧别名不归一化、不猜测，直接拒绝并给迁移建议
        if not self._validate_positioning(config, source):
            return False

        return True
    
    def get_style_thumbnail(self, style_name: str) -> Optional[str]:
        """
        获取指定样式的缩略图路径
        
        在样式配置文件夹中查找 thumbnail.png / thumbnail.jpg / thumbnail.jpeg。
        
        Args:
            style_name: 样式名称
            
        Returns:
            缩略图文件绝对路径，不存在则返回 None
        """
        style_dirs = list(self._iter_style_dirs(style_name))
        if not style_dirs:
            return None
        
        for style_dir in style_dirs:
            for ext in ('.png', '.jpg', '.jpeg'):
                thumb_path = os.path.join(style_dir, f'thumbnail{ext}')
                if os.path.isfile(thumb_path):
                    return thumb_path
        
        return None

    def get_default_style(self) -> Optional[Dict]:
        """
        获取默认样式配置
        
        Returns:
            默认样式配置
        """
        # 尝试获取第一个可用样式作为默认样式
        available_styles = self.get_available_styles()
        if available_styles:
            return self.get_style_config(available_styles[0])
        
        return None
    
    def create_sample_styles(self):
        """创建示例样式配置文件"""
        # 创建configs目录（如果不存在）
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 示例样式配置
        sample_config = {
            "name": "Classic",
            "description": "经典相框样式",
            "version": "1.0",
            "layout": {
                "expand_canvas": {
                    "enabled": True,
                    "top": 0.05,
                    "bottom": 0.1,
                    "left": 0.05,
                    "right": 0.05
                },
                "info_position": {
                    "exif": {
                        "placement": "outside",
                        "position": "bottom-center",
                        "alignment": "top-center",
                        "margin": 10
                    },
                    "author": {
                        "placement": "outside",
                        "position": "center-left",
                        "alignment": "center-right",
                        "margin": 10
                    },
                    "location": {
                        "placement": "outside",
                        "position": "center-right",
                        "alignment": "center-left",
                        "margin": 10
                    }
                }
            },
            "colors": {
                "text": "#000000"
            },
            "fonts": {
                "family": "Gotham",
                "weight": "medium",
                "size_ratio": 0.02,
                "sizes": {
                    "exif": 0.02,
                    "author": 0.018,
                    "location": 0.018
                }
            }
        }
        
        # 保存示例配置
        sample_path = os.path.join(self.config_dir, 'Default_TestFrame.json')
        with open(sample_path, 'w', encoding='utf-8') as f:
            json.dump(sample_config, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"示例样式配置已创建: {sample_path}")


# 创建默认样式管理器实例
default_style_manager = StyleManager()