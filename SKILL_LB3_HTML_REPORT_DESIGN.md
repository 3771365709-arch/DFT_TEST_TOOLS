# SKILL: LB3 测试数据 HTML 报告设计规范

> 本 skill 文档记录 LB3 测试数据 HTML 网页报告的**设计规范**与**实现要点**，供后续修改、复刻或扩展该报告时参考。设计风格参考公司 DFT 测试结果可视化总结页（深色科技风）。
>
> **版本 v2.1（2026-09-09）**：新增项目适配层 `lb3tools_project.py`——移植到其他项目只需改这一个文件（列名别名/单位换算/结果词表/正则/标称条件/向量分类），分析渲染逻辑零改动。：与 `lb3tools_html.py` 当前实现同步——新增 向量分类总结 / 测试条件一览 / 悬停频压明细 / 窗口法着色与异常判据 / 双模式热力图 / 温度分图规则。

---

## 一、设计定位

- **用途**：将 LB3 芯片 MBIST 测试批次数据可视化为单文件 HTML 看板，用于团队共享与交付。
- **风格**：深色科技风（Dark Tech），高对比度、低饱和强调色，专业数据报告质感。
- **交互**：单页自上而下滚动，无页签切换；图表支持悬停、缩放；热力图格子悬停展开频压明细。
- **依赖**：ECharts（内嵌，离线可用）；纯 HTML + CSS + JS，无框架。
- **入口**：`lb3tools_html.py` 直接运行 与 `lb3tools_cli.py report` 子命令**共用 `run_report_cli()`**，参数/输出/报告内容完全一致。

---

## 二、配色系统（CSS 变量）

所有颜色集中在 `:root` 变量，修改一处全局生效：

```css
:root{
  --bg:#0b1220;          /* 页面背景：深蓝黑 */
  --panel:#121c30;       /* 面板背景：深海军蓝 */
  --panel2:#0f1830;      /* 次级面板/表头：更深蓝 */
  --line:#1e2c4a;        /* 边框/分割线 */
  --txt:#e8eefb;         /* 主文字：浅灰白 */
  --sub:#8fa3c8;         /* 次要文字：灰蓝 */
  --dim:#5b6c8f;         /* 暗淡文字：脚注/提示 */
  --green:#22c07a;       /* Pass / 好：绿 */
  --red:#f4515c;         /* Fail / 差：红 */
  --amber:#f5a623;       /* 警告/边缘：琥珀 */
  --blue:#3d8bff;        /* 强调/信息：蓝 */
  --gray:#3a4a6b;        /* 无数据/中性：灰 */
}
```

**配色原则**：
- 背景用冷深色系（蓝黑），营造科技感；
- 强调色仅 4 个：绿（好）、红（差）、琥珀（警告/异常）、蓝（信息），不混用其他色相；
- 文字三级对比：主文字 `--txt` > 次要 `--sub` > 暗淡 `--dim`。

---

## 三、字体与排版

```css
font-family:"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;
```

| 元素 | 字号 | 字重 | 颜色 |
|------|------|------|------|
| h1 标题 | 26px | 700 | `--txt` |
| h1 标签 | 12px | 500 | `--blue`（边框同色） |
| KPI value | 30px（温度卡 22px） | 700 | 按语义着色 |
| KPI label | 13px | 400 | `--sub` |
| KPI foot | 12px | 400 | `--dim` |
| panel h2 | 15px | 600 | `--txt` |
| panel hint | 12px | 400 | `--dim` |
| 向量分类卡 h4 / num | 13px / 26px | 600 / 700 | `--sub` / `--blue` |
| 表格 | 12.5px | 400 | `--txt`（表头 `--sub`） |
| meta 信息 | 13px | 400 | `--sub`（`<b>` 用 `--txt`） |
| footer | 12px | 400 | `--dim` |

数字列使用 `font-variant-numeric:tabular-nums` 保证等宽对齐；向量名用 `Consolas,Menlo,monospace` 等宽字体。

---

## 四、页面布局结构

单页自上而下，`max-width:1440px` 居中，`padding:28px 32px 48px`：

```
┌─────────────────────────────────────────────────┐
│  Header（flex 左右分布）                          │
│  左：h1 标题 + 蓝色标签      右：meta 数据源信息    │
├─────────────────────────────────────────────────┤
│  KPI 卡片（grid 6 列）                            │
│  [芯片数][测试温度][测试点][全Pass芯片][Fail芯片][良率]│
├─────────────────────────────────────────────────┤
│  Alert 提示框（红 / 绿，渐变背景）                  │
├─────────────────────────────────────────────────┤
│  向量分类总结（grid 4 卡片，未覆盖置灰）             │
│  [Mbist_标称][SHM_Default][SHM_EMC][SHM_ALGO]     │
├─────────────────────────────────────────────────┤
│  Grid 双栏（7fr : 5fr）                           │
│  ┌──────────────┬──────────────┐                 │
│  │ 柱状图        │ 环形图        │                 │
│  │ 各芯片Fail数  │ 芯片级构成    │                 │
│  └──────────────┴──────────────┘                 │
│  向量×芯片热力图（全宽，按温度分图，悬停频压明细）    │
├─────────────────────────────────────────────────┤
│  测试条件一览（静态表：每芯片温度/频率点/电压点/标称） │
├─────────────────────────────────────────────────┤
│  失败向量 TOP 横向柱状图（全宽）                    │
├─────────────────────────────────────────────────┤
│  Fail 明细表（全宽，sticky 表头 + 滚动）            │
│  数据总结（文字化：概要 + 细则）                    │
├─────────────────────────────────────────────────┤
│  Footer（居中，数据来源 + 判定条件 + 良率）         │
└─────────────────────────────────────────────────┘
```

### 响应式断点

```css
@media(max-width:1000px){
  .kpis{grid-template-columns:repeat(2,1fr)}
  .grid{grid-template-columns:1fr}
  .cats{grid-template-columns:1fr}
  .vcats{grid-template-columns:repeat(2,1fr)}
}
```

---

## 五、组件样式规范

### 5.1 Header

```css
header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;
       gap:12px;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:20px}
```
- 左右分布，底部对齐；底部分割线；右侧 meta 右对齐，`<b>` 高亮关键字段。

### 5.2 KPI 卡片（6 张）

```css
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}
.kpi{background:linear-gradient(160deg,var(--panel),var(--panel2));
     border:1px solid var(--line);border-radius:12px;padding:18px 20px}
```
- 三层结构：`.label` → `.value` → `.foot`；
- 6 张：芯片数量 / 测试温度 / 测试点总数 / 全向量 Pass 芯片 / 存在 Fail 芯片 / 调整良率（颜色分级：绿≥80% / 琥珀≥50% / 红<50%）。

### 5.3 Alert 提示框

```css
.alert{display:flex;gap:16px;align-items:flex-start;
       background:linear-gradient(90deg,rgba(244,81,92,.14),rgba(244,81,92,.03));
       border:1px solid rgba(244,81,92,.45);border-radius:12px;padding:16px 20px}
```
- 红色版（默认）/ 绿色版（`.alert.ok`）。

### 5.4 向量分类总结卡片（.vcats / .vcat）

```css
.vcats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.vcat{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.vcat.dim{opacity:.45}                     /* 未覆盖类别置灰 */
.vcat .num{font-size:26px;font-weight:700;color:var(--blue)}
.vcat .badge{display:inline-block;font-size:11px;border-radius:4px;padding:2px 8px}
.vcat li{display:flex;justify-content:space-between;border-top:1px dashed var(--line)}
```
- 4 张卡片对应《LB3测试进度汇总》：**Mbist_标称(171条) / SHM_Default(13) / SHM_EMC(91) / SHM_ALGO(24)**；
- 大数字 = 本批次已测 / 库内总数；徽章 = 全部 Pass(绿) / N 条存在 Fail(琥珀，含 N 条窗口异常) / 未测(灰)；
- nominal 模式标称卡片附细分行：Default 类 X/13、EMC 类 X/91、ALGO 类 X/24、标称独有 X/43；
- sweep 模式卡片统计行含"窗口异常 X 条"。

### 5.5 Panel 面板 / Grid / 表格 / Legend

```css
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.grid{display:grid;grid-template-columns:7fr 5fr;gap:14px}
.tbl-wrap{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:8px}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--sub)}
```
- `.full` 跨满列宽；`.chart` 高 340px、`.chart.tall` 420px、`[id^="heatmap_"]` 高 560px；
- 表头 sticky、向量名等宽字体、数字右对齐等宽。

---

## 六、图表配置规范（ECharts）

### 6.1 通用深色配置

```javascript
axisLabel:{color:'#8fa3c8'} axisLine:{lineStyle:{color:'#1e2c4a'}}
splitLine:{lineStyle:{color:'#1e2c4a'}} label:{color:'#e8eefb'}
```

### 6.2 柱状图（各芯片 Fail 向量数）

- 柱色：最差芯片红、有 fail 琥珀、全 pass 深灰蓝；顶部 label 仅显示 >0。

### 6.3 环形图（芯片级结果构成）

- 中心显示 `"{pass数} / {总数}\n全向量通过"` + 良率；扇区按失效类别配色。

### 6.4 热力图（向量 × 芯片，双模式 + 悬停明细）★核心

**模式自动判定**（`--heatmap-mode auto/nominal/sweep`，默认 auto）：统计 csv 频压组合数，≤3 组（750mV×20/25MHz）→ nominal；>3 组（500-950mV×10-45MHz=80 组）→ sweep。

**格子 = 向量×芯片，按温度分图**（85°C/125°C 各一张，温度排序 低→常温→高）：

| 模式 | 格子着色 | 悬停明细 |
|---|---|---|
| nominal | 离散：绿=Pass / 红=Fail（visualMap 0-2） | 2~3 个频压点小格 |
| sweep | **窗口法**：绿=正常窗口(含部分Fail角点) / 琥珀=窗口异常 / 红=全Fail / 空白=无数据 | 80 小格矩阵（列=电压、行=频率）+ "格内 X/Y Pass" |

**窗口异常判定（与数据总结三判据一致）**：
- ① 低频异常：该向量 15MHz 失败率 >50%（跨芯片/温度聚合；低频应更易通过，基线 ≤11%）
- ② Fmax@750mV 掉档：格子 Fmax 比该向量批次内最好成绩低 ≥10MHz（2 档）
- 判据③ 单格失败率 >80% 的格子列表输出到"数据总结"（定位最差点位）

**明细渲染**：悬停格子才在 tooltip 中渲染 频率×电压 HTML 小格矩阵（13px 色块：绿=Pass/红=Fail/琥珀=设备侧异常/灰=无数据），平时不显示。琥珀格悬停附加"⚠窗口异常"标注。

**Y 轴 dataZoom**：右侧 slider + inside，向量多时（171 条）初始只显示 ~40 行。

### 6.5 失败向量 TOP 柱状图

- 横向柱状图，按失败芯片数降序，系统性失败向量排前。

---

## 七、数据到可视化的映射

### 7.1 核心数据结构（JS 端）

```javascript
var CHIPS = [...];            // 芯片列表
var VECTORS = [...];          // 标称向量列表
var CHIPFAILS = [...];        // 每芯片 fail 向量数(仅芯片相关 FAIL)
var CATS = {...};             // 失效类别分布
var VFAILS = [...];           // 失败向量排行
var SCATTERED = [...];        // 标称 fail 明细 [向量,芯片,频率,电压,温度]
var WORST = "TT50";           // 最差芯片
var FULL = [{                 // 每温度一张热力图
  label:'85°C', chips:[...], vecs:[...],   // vecs 为短名(G0/ROM_G1_EMC00000)
  freqs:['10',...], volts:['500',...], mode:'sweep',
  status:[[0|1|2|3]],        // 格聚合: 0全Pass 1全Fail 2无数据 3部分Fail(sweep)
  ratio:[[0~1|null]],        // 格通过率(sweep着色/判据用), 无数据=null
  pts:[[[...]]],             // 格内频压点状态数组(频率主序, 与freqs×volts对应)
  fmax750:[[..]], low15:[[0|1]], anom:[[0|1]]  // 窗口法判据中间量与异常标记
}];
```

### 7.2 构建逻辑（Python 端）

```
load_inputs → 芯片名归一 + 温度解析(芯片文件夹后缀 > 批次名单温度 > 常温, 歧义警告)
  → 模式判定(频压组合数 ≤3→nominal / >3→sweep)
  → 按温度分图循环: (向量,芯片,频率,电压)→结果集合
     status/ratio/pts/anom(窗口法) → FULL
  → 良率/失效分类: 只取标称条件点(扫频扫压角点 Fail 是扫描预期, 不计入)
```

### 7.3 向量分类总结的分类规则（`_vec_family`，已对 VECTOR 四文件夹全量校准）

优先级从上到下（兼容完整名与短名）：

```
ICLNetwork→iclnet │ _RT_TYPE→rt │ _PW$→pw │ SMarch/LVWalkingPat→algo
_EMC00000→default │ _EMC[01]{4,5}$→emc │ ROM开头/_ROM_→rombase
(^|_)G\d+$→default │ 其他→other
```

库总数：标称(TEST_FINAL)=171、Default=13、EMC=91、ALGO=24；标称独有=43。

### 7.4 温度规则（前置条件）

- 来源优先级：芯片子文件夹名后缀（TT10_85）> 批次名单一温度标记（85c/temp-25）> 无标记=常温；
- 批次名含多温度但芯片无后缀 = 歧义 → 按常温并打印 stderr 警告；
- 分图排序：低温(0/-25) → 常温(视作25°C) → 高温(85/125)；每温度独立一张图，不合并。

---

## 八、HTML 模板结构

模板函数 `_html_page(title, echarts_js, echarts_mode, meta_html, body, footer_html, script)`：单文件结构（内嵌 echarts + 数据变量 + 图表 IIFE + 表格渲染），详见 `lb3tools_html.py`。

---

## 九、实现要点与注意事项（含踩坑记录）

1. **ECharts 三级回退**：本地内嵌 → 自动下载缓存 → CDN，保证离线可用。
2. **单文件交付**：无外部依赖，可直接发邮件/钉钉。
3. **判定逻辑复用 core**：网页与 xlsx 用同一套 core 函数。
4. **口径分离**：良率/失效分类只取标称条件点；扫频扫压角点 Fail 是扫描预期（16 批次标称全 Pass → 边缘失败/分组级失效=0 是正确口径）。扫频扫压异常通过"窗口法判据 + 琥珀格 + 数据总结"暴露，不计入良率。
5. **% 格式化转义坑**：body/summary 等 `%` 格式化模板内的字面 `%`（如 `80%`）必须写 `%%`，否则触发 `ValueError: unsupported format character` / `TypeError: format requires a mapping`（`80%)`、`80%(` 都踩过）。
6. **分类轴按位置展开**：ECharts category 轴长度=类目数组长度。分组轴（芯片×电压）必须逐列展开标签数组（长度=芯片数×电压数），只传去重值会把图截断成第一组。
7. **短名正则锚点**：向量短名 `G0` 无下划线前缀，`_G\d+$` 匹配不到，需 `(?:^|_)G\d+$`。
8. **dataZoom 必要性**：向量多时（171 条）纵轴超长，slider+inside 缩放。
9. **数字等宽对齐**：`tabular-nums` / 等宽字体。
10. **颜色语义一致**：绿=好/红=差/琥珀=异常/蓝=信息；无数据统一灰/空白。

---

## 十、修改指南

| 需求 | 修改位置 |
|------|----------|
| 换配色 | `:root` CSS 变量 |
| 改 KPI 数量/内容 | `write_html_report` 的 `kpis` 变量 |
| 改向量分类规则/库总数 | `_vec_family()` / `_LIB_TOTAL` |
| 改窗口异常判据 | Python `low15`/`fmax750`/`anom` 计算 + 数据总结 detail_items |
| 改格子着色 | JS `sweepColor`（已并入 hm 构建分支）/ nominal `visualMap` |
| 改悬停明细样式 | JS `tipGrid()` |
| 改判定条件/强制模式 | `--nominal-v/--nominal-f/--heatmap-mode` |
| 新增区块 | `body` 字符串插 HTML + `script` 加对应 IIFE（注意 §九-5 的 % 转义） |

---

## 十一、移植到其他项目（v2.1）

- **唯一适配点**：`lb3tools_project.py` 的 `PROJECT` 字典（core 启动时加载，缺省键回落内置默认值；删掉该文件 = LB3 默认行为）。
- **配置键**：`columns`(csv 列名别名) / `clock_scale`,`voltage_scale`(单位换算) / `pass_values`,`chip_fail_values`,`equip_fail_values`(结果词表) / `chip_name_pattern`,`temp_chip_pattern`,`temp_batch_patterns`(芯片名与温度正则) / `nominal_v_priority`,`nominal_freqs`(标称条件) / `vector_categories`(分类卡片: key/display/lib/cond/match/order/hidden/count_shared_from)。
- **本 skill 中 LB3 专属内容**的对应关系：§7.3 分类规则 → `vector_categories.match`；§7.4 温度规则 → 三个正则；结果词表 → 三个词表键。
- **行为**：未适配时缺列会 ValueError 并打印实际表头引导配置；向量分类未命中 → 兜底"标称"卡，模块不崩。
- 详细步骤见 README 第 9 节。

---

*本文档随 `lb3tools_html.py` 同步更新（v2.1, 2026-09-09）。设计基准：公司 DFT 测试结果可视化总结页（深色科技风）。*
