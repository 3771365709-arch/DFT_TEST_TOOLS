# 移植指南 —— 将 tools_for_LB3 适配到新项目

> 本指南涵盖从复制目录到验证输出的完整流程，重点说明 **lb3tools_project.py 可配置项** 与 **不可配置的硬编码值** 两部分。
> 移植到新项目后，推荐将 `lb3tools_project.py` 重命名为 `<project>_project.py` 并同步修改 core.py 中的 import 路径，或保持原名但替换内容。

---

## 0. 总览：哪些需要改

```
┌─────────────────────────────────────────────────────────────────────┐
│  lb3tools_project.py          ← ✅ 90% 的改动在这里（配置字典）       │
│  ├─ columns                    csv 列名别名映射                       │
│  ├─ clock_scale / voltage_scale  单位换算系数                         │
│  ├─ pass_values / chip_fail_values / equip_fail_values  结果词表       │
│  ├─ chip_name_pattern / temp_*_pattern  芯片名/温度正则               │
│  ├─ nominal_v_priority / nominal_freqs  标称工作点                    │
│  └─ vector_categories          HTML 向量分类卡片                       │
│                                                                     │
│  以下文件中存在 ❌ 不可配置的硬编码值，需手动编辑：                     │
│  lb3tools_core.py              ← 失效阈值 / 向量库参数 / 分组规则       │
│  lb3tools_html.py              ← 向量名前缀 / 频率基准 / 窗口异常判据   │
│  lb3tools_cli.py              ← 仅改 argparse description（可选）      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. 复制目录

```bash
# 新项目根目录下
cp -r tools_for_LB3 tools_for_<NEWPROJECT>
cd tools_for_<NEWPROJECT>
```

可选：将文件名中的 `lb3tools_` 重命名为 `<newproj>tools_`，并修改三个 .py 的 import 语句。

---

## 2. 配置 lb3tools_project.py（核心步骤）

### 2.1 columns —— CSV 列名别名映射

**问题**：不同测试机台导出的 csv 列名不同（OCT → `Vector Name`，STD → `Pattern`，中文机台 → `向量名`）。

**LB3 原值**：
```python
'vector':      ['Vector Name', 'Vector', 'Pattern', 'Pattern Name',
                'Test Name', '向量名'],
'clock':       ['Clock/MHz', 'Clock', 'Frequency/MHz', 'Frequency',
                'Freq', '频率/MHz'],
'voltage':     ['Set Voltage/mV', 'Voltage/mV', 'Set Voltage', 'Voltage',
                '电压/mV'],
'read_vddl':   ['Read VDDL/mV', 'Read VDDL', 'VDDL/mV'],
'error_count': ['Error Count', 'ErrorCount', '错误计数'],
'result':      ['Test Result', 'Result', 'Status', '结果'],
```

**新项目示例**（假设某机台 csv 表头为 `Pattern, Freq_MHz, Vout_mV, Count, Status`）：
```python
'vector':      ['Pattern', 'Vector', '向量名'],
'clock':       ['Freq_MHz', 'Clock', '频率'],
'voltage':     ['Vout_mV', 'Voltage', '电压'],
'read_vddl':   [],                         # 无此列 → 留空
'error_count': ['Count', 'Error Count'],
'result':      ['Status', 'Result'],
```

**注意**：
- 匹配时**忽略大小写和空格**（core 层做了 `re.sub(r'\s+', '', ...).lower()` 归一化）
- `vector` / `clock` / `voltage` / `result` 是**必需字段**，缺失会抛带指引的 `ValueError`
- `read_vddl` / `error_count` 是可选的，无则留空列表或删除键

### 2.2 clock_scale / voltage_scale —— 单位换算

**问题**：有些项目电压列单位是 V（0.75）而非 mV（750），频率列是 Hz 而非 MHz。

**LB3 原值**：
```python
'clock_scale':   1.0,    # 已为 MHz
'voltage_scale': 1.0,    # 已为 mV
```

**新项目示例**（电压列单位为 V，频率列单位为 Hz）：
```python
'clock_scale':   1e-6,   # Hz → MHz
'voltage_scale': 1000.0, # V → mV
```

换算公式：`实际值 = csv值 × scale`。

### 2.3 结果词表 —— 三态分类

**LB3 原值**：
```python
'pass_values':       ['PASS'],
'chip_fail_values':  ['FAIL'],
'equip_fail_values': ['CLOCKSETFAIL', 'READERROR'],
```

**新项目示例**（假设机台输出 `OK`/`NG`/`HWERR`/`TIMEOUT`）：
```python
'pass_values':       ['OK', 'PASS'],
'chip_fail_values':  ['NG'],
'equip_fail_values': ['HWERR', 'TIMEOUT'],
```

**关键语义**：
| 词表 | 计入良率？ | 含义 |
|------|-----------|------|
| `pass_values` | ✅ 计 Pass | 测试通过 |
| `chip_fail_values` | ✅ 计 Fail | 芯片本身的问题 |
| `equip_fail_values` | ❌ 不计 | 设备/环境异常（应剔除，不污染良率） |

大小写不敏感比较。

### 2.4 chip_name_pattern —— 芯片名正则

**问题**：芯片文件夹名规则可能不同。LB3 规则：`PDK1_TT10_85` → 提取核心代码 `TT10`。

**LB3 原值**：
```python
'chip_name_pattern': r'(TT|FS|SF|FF|SS)\d{2}',
```

**新项目示例**（假设芯片文件夹为 `WLV3_TYP1_0`，芯片代码为 `TYP1`）：
```python
'chip_name_pattern': r'TYP\d+',
```

### 2.5 temp_chip_pattern / temp_batch_patterns —— 温度正则

**LB3 原值**：
```python
'temp_chip_pattern':   r'(?:TT|FS|SF|FF|SS)\d{2}_(-?\d+)',   # 芯片名后缀
'temp_batch_patterns': [r'(-?\d+)c', r'temp(-?\d+)'],         # 批次名兜底
```

**新项目示例**：
```python
'temp_chip_pattern':   r'TYP\d+_(-?\d+)',
'temp_batch_patterns': [r'(-?\d+)c', r'T(-?\d+)'],
```

**优先级**：芯片文件夹名后缀 → 批次文件夹名兜底 → 常温。多温度歧义时 core 层会在 stderr 警告。

### 2.6 nominal_v_priority —— 标称电压优先级

**问题**：多电压档（Shmoo）时，按优先级选一个作为标称。

**LB3 原值**（750mV 最优先）：
```python
'nominal_v_priority': [750.0, 700.0, 800.0, 650.0, 850.0, 900.0,
                       600.0, 950.0, 550.0, 500.0],
```

**新项目示例**（标称 1.2V，按从高到低排）：
```python
'nominal_v_priority': [1200.0, 1100.0, 1300.0, 1000.0, 1400.0],
```

### 2.7 nominal_freqs —— 标称频点

**问题**：Shmoo 批次（>3 个频点）的标称频点列表。

**LB3 原值**：
```python
'nominal_freqs': [20.0, 25.0],
```

**新项目示例**：
```python
'nominal_freqs': [50.0, 100.0],
```

**快测批次**（≤3 个频点）不受此配置影响——core 层自动取全部频点作为标称。

### 2.8 vector_categories —— HTML 向量分类卡片

**问题**：HTML 报告有 4 张向量分类卡（库内总数 / 已测 / Pass / Fail），匹配规则和显示名来自此配置。

**LB3 原值**：
```python
'vector_categories': [
    {'key': 'algo',    'display': 'SHM_ALGO 向量', 'lib': 24,
     'match': ['SMarch', 'LVWalkingPat']},
    {'key': 'rombase', 'display': None,          'lib': 0, 'hidden': True,
     'match': [r'_ROM_G\d+$']},
    {'key': 'default', 'display': 'SHM_Default 向量', 'lib': 13,
     'match': [r'_EMC00000', r'(?:^|_)G\d+$']},
    {'key': 'emc',     'display': 'SHM_EMC 向量',     'lib': 91,
     'match': [r'_EMC[01]{4,5}$'], 'count_shared_from': 'default'},
    {'key': 'nominal', 'display': 'Mbist_标称向量',   'lib': 171,
     'cond': '标称 750mV × 20/25MHz', 'match': []},
],
```

**配置规则**：
| 键 | 含义 |
|----|------|
| `key` | 内部标识，唯一 |
| `display` | 卡片显示名；`None` + `hidden:True` → 不显示但计入其他卡的细分 |
| `lib` | 库内向量总数（显示用，不影响匹配） |
| `match` | 正则/子串列表，**按列表顺序优先匹配**，命中即归入该类 |
| `cond` | 测试条件描述（显示用） |
| `hidden` | `True` → 不显示卡片但参与分类 |
| `count_shared_from` | 该类与另一类共用向量时，已测数需并入显示 |
| `match: []` | 兜底卡：未命中任何其他类的向量全部归入 |

**新项目示例**（假设向量命名为 `WLV3_<算法>_<分组>.txt`）：
```python
'vector_categories': [
    {'key': 'marchexec', 'display': 'MarchExec 向量', 'lib': 30,
     'match': ['MarchExec']},
    {'key': 'marchlong', 'display': 'MarchLong 向量', 'lib': 20,
     'match': ['MarchLong']},
    {'key': 'nominal',   'display': '标称向量',        'lib': 150,
     'cond': '标称 1200mV × 50/100MHz', 'match': []},  # 兜底
],
```

**常见陷阱**：`match` 列表里的正则写得太宽（如 `G\d`）会导致本该归入兜底卡的向量被提前匹配到其他卡。**列表顺序 = 优先级**，兜底卡（`match: []`）通常放最后。

---

## 3. 硬编码值清单（需手动编辑）

以下值**不在 `lb3tools_project.py` 中**，需要直接修改 .py 文件。

### 3.1 lb3tools_core.py

| 行号 | 硬编码值 | 含义 | 何时需要改 |
|------|----------|------|-----------|
| [L379](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_core.py#L379) | `0.9` | 芯片级失效判定阈值（失败点 ≥ 90% → 芯片级失效） | 新项目良率水平不同 |
| [L389](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_core.py#L389) | `0.6` + `tot >= 8` | 分组级失效判定阈值（某分组失败 ≥ 60% 且该分组至少 8 个测试点） | 存储器分组大小不同 |
| [L395](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_core.py#L395) | `ratio=0.3` | 系统性失败向量阈值（≥ 30% 芯片上失败 → 剔除） | 新项目向量数量不同 |
| [L719](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_core.py#L719) | `XDMA_PART_LINES = 8192` | XDMA H2C 分包的向量行数 | DFT Test Tool 不同版本 |
| [L720](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_core.py#L720) | `BYTES_PER_LINE = 16` | 每行激励字节数（= 位宽 / 8） | 向量位宽不是 128bit 时 |
| [L75](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_core.py#L75) | `_GROUP_RE = re.compile(r'_(G\d)(?=[_.])')` | 存储器分组提取正则 | 分组命名不是 G0~G7 时 |
| [L291-L300](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_core.py#L291-L300) | `vector_group()` 中的 `ICLNetwork` / `ROM` 硬编码 | 向量分组分类逻辑 | 新项目向量名不含这些关键字时 |

**修改示例**（如果新项目向量位宽是 64bit，分组叫 `BANK0~BANK7`）：
```python
# L720
BYTES_PER_LINE = 8      # 64bit = 8 字节

# L75
_GROUP_RE = re.compile(r'_(BANK\d)(?=[_.])')

# L291-L300 的 vector_group 函数
def vector_group(vec):
    if 'ICL' in vec:
        return 'ICL'
    m = _GROUP_RE.search(vec)
    if m:
        return m.group(1)
    if 'ROM' in vec:
        return 'ROM'
    return 'OTHER'
```

### 3.2 lb3tools_html.py

| 行号 | 硬编码值 | 含义 | 何时需要改 |
|------|----------|------|-----------|
| [L278-L283](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L278-L283) | `_short_vec()` 中的 `LB3_MemoryBist_P1_` / `LB3_MemoryBist_` / `LB3_` 前缀 | 向量名前缀剥离 | 新项目向量名前缀不同 |
| [L225](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L225) | `MBIST` 标签 | HTML 头部右上角小标签 | 不是 MBIST 时 |
| [L251](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L251) | `LB3 测试数据报告` | 自动生成的默认标题 | 新项目名 |
| [L867](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L867) | `LB3 error_count 原始数据` | Footer 数据来源说明 | 新项目数据源 |
| [L280](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L280) | `'LB3_MemoryBist_P1_', 'LB3_MemoryBist_', 'LB3_'` | 向量名前缀剥离列表 | 新项目向量名前缀 |
| [L402](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L402) / [L802](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L802) | `15.0` | 低频异常判定的基准频率 | 标称频率不是 20/25MHz 时 |
| [L434](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L434) | `>= 10.0` | Fmax 掉档判定阈值（MHz） | 窗口上沿精度要求不同 |
| [L755-L756](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_html.py#L755-L756) | `"低频更易通过"物理预期; 基线失败率≤11%` | 数据总结中的文字描述 | 新项目不同物理预期时 |

**修改示例**（向量名前缀改为 `WLV3_Mem_`，MBIST 标签改为 `SMST`）：
```python
# L225
'<div><h1>%s<span class="tag">SMST</span></h1></div>'

# L278-L283
def _short_vec(v):
    s = v[:-4] if v.endswith('.txt') else v
    for p in ('WLV3_Mem_', 'WLV3_'):
        if s.startswith(p):
            return s[len(p):]
    return s

# L251
title = 'WLV3 测试数据报告 (%d 颗芯片)' % n_chips

# L402 / L802 的 15.0 → 改成新项目的"低频"基准，如 25.0
# L434 的 10.0 → 改成新项目的 Fmax 掉档阈值，如 20.0
```

### 3.3 lb3tools_cli.py（可选）

| 行号 | 硬编码值 | 含义 |
|------|----------|------|
| [L4](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_cli.py#L4) | `LB3 测试数据工具 - CLI 版` | 文件头注释 |
| [L143-L144](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_cli.py#L143-L144) | `prog='lb3tools_cli'`, `description='LB3 测试数据工具...'` | argparse 名称和描述 |
| [L171](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_cli.py#L171) | `/home/yangxinhang/LB3/VECTOR` | vecinfo 命令 help 中的路径示例 |

这些只是展示文本，不影响功能。

---

## 4. 向量分组规则（深度修改）

如果新项目的向量分组命名与 LB3 的 `G0~G7` / `ROM` / `ICLNetwork` 完全不同，需要修改 core 层的 [vector_group](file:///c:/Users/Administrator/Desktop/LB3_OUTPUT/tools_for_LB3/lb3tools_core.py#L291-L300) 函数：

```python
# LB3 原实现
_GROUP_RE = re.compile(r'_(G\d)(?=[_.])')

def vector_group(vec):
    """提取向量的存储器分组: ICL / G0~G7 / ROM / OTHER"""
    if 'ICLNetwork' in vec:
        return 'ICL'
    m = _GROUP_RE.search(vec)
    if m:
        return m.group(1)
    if 'ROM' in vec:
        return 'ROM'
    return 'OTHER'
```

**新项目示例**（分组为 `BANK0~BANK7`、`FLASH`、`SOC`）：
```python
_GROUP_RE = re.compile(r'_(BANK\d)(?=[_.])')

def vector_group(vec):
    if 'SOC' in vec:
        return 'SOC'
    m = _GROUP_RE.search(vec)
    if m:
        return m.group(1)
    if 'FLASH' in vec:
        return 'FLASH'
    return 'OTHER'
```

**影响范围**：
- 良率报告的"分组级失效"判定（`classify_chip` 函数按分组统计失败率）
- Shmoo 报告无影响（按向量整体统计）
- HTML 热力图无影响（向量名直接用作 y 轴标签）

---

## 5. 验证流程

移植完成后，用以下步骤验证配置是否正确：

### 5.1 第一步：加载测试

```bash
python3 lb3tools_cli.py yield -i <新项目批次目录>
```

**成功标志**：控制台输出"已加载 N 颗芯片"，没有 `ValueError: csv 缺少必需列`。

**失败排查**：如果报缺列，把新项目 csv 的表头贴出来，在 `lb3tools_project.py` 的 `columns` 里补上别名。

### 5.2 第二步：检查良率判定

控制台应输出：
```
标称判定条件: 电压=auto, 频率=auto
实际判定: 750.0mV × [20.0, 25.0]MHz
样本总数: N
严格良率(全部标称点通过): x/N = y%
调整良率(剔除系统性向量): x/N = y%
```

如果 `实际判定` 的电压/频率不对，手动指定参数覆盖：
```bash
python3 lb3tools_cli.py yield -i <目录> --nominal-v 1200 --nominal-f 50,100
```

### 5.3 第三步：生成 HTML 报告

```bash
python3 lb3tools_cli.py report -i <目录> --open
```

检查以下点：
- [ ] 页面标题显示新项目名（非"LB3 测试数据报告"）
- [ ] 向量名已去掉旧前缀（如 `G2` 而非 `LB3_MemoryBist_P1_G2`）
- [ ] 向量分类卡片没有全部落入"标称"兜底（如果新项目有自己的向量命名）
- [ ] 热力图按温度分图正常
- [ ] 扫频扫压模式下琥珀色窗口异常标记正常

### 5.4 第四步：生成 xlsx 交叉验证

```bash
python3 lb3tools_cli.py errcount -i <目录>
python3 lb3tools_cli.py shmoo -i <目录>
python3 lb3tools_cli.py vecinfo --lib <向量库目录> -i <目录>
```

检查：
- [ ] errcount 报告的失败明细里，失败点和 CSV 原始数据一致
- [ ] shmoo 报告的 Vmin/Fmax 数值合理
- [ ] vecinfo 的交叉校验没有大量"测试数据中出现但库中无源文件"

---

## 6. 常见陷阱排查

### 陷阱 1：csv 表头匹配不到

**现象**：`ValueError: csv 缺少必需列: ['vector', 'clock', ...]`

**排查**：
1. 打开 csv 看真实表头（注意 BOM/编码问题，推荐用 Notepad++ 转 UTF-8）
2. 在项目配置的 `columns` 里补上正确的别名
3. 记匹配是 `re.sub(r'\s+', '', name).lower()`，所以 `Vector Name` 和 `vectorname` 等价

### 陷阱 2：芯片名提取不正确

**现象**：所有芯片都显示成文件夹全名（如 `PDK1_TT10_85` 而非 `TT10`）

**排查**：`chip_name_pattern` 正则没匹配到。用 Python 验证：
```bash
python3 -c "import re; print(re.search(r'(TYP\d+)', 'PDK1_TYP1_0'))"
```
返回 `None` 说明正则不对。

### 陷阱 3：温度提取失败

**现象**：多温度批次的芯片全部显示为常温

**排查**：
1. 芯片文件夹名有没有温度后缀？如 `TT10_85` → 有；`TT10` → 无
2. 批次名能不能兜底？如 `15c_batch` → 能兜底 85；`temp-25_test` → 能兜底 -25
3. 两者都没有 → 所有芯片按常温处理（这是正常的）

### 陷阱 4：所有向量都落入"标称"兜底卡

**现象**：HTML 报告只有一张 Mbist_标称 卡，algo/default/emc 卡全置灰

**排查**：
1. `vector_categories` 的 `match` 正则/子串有没有覆盖新项目的向量命名？
2. 匹配是**按列表顺序**的，前面的 `match` 命中后面就不会再尝试
3. 兜底卡（`match: []`）应该放**最后**

### 陷阱 5：系统性向量异常多

**现象**：调整良率比严格良率高很多，或控制台输出"系统性失败向量 50 个"

**排查**：
1. `nominal_v` / `nominal_fs` 探测是否正确？如果探测到一个极少测试的电压/频率，会误判
2. 手动指定 `--nominal-v` 和 `--nominal-f` 覆盖自动探测
3. 如果新项目本身测试覆盖的频压点非常少（≤2），`find_systematic_vectors` 的 30% 阈值可能偏高

### 陷阱 6：HTML 报告的 ECharts 走 CDN

**现象**：控制台提示"ECharts: CDN(需联网)"

**解决**：
1. 联网运行一次（会自动下载并保存到同目录 `echarts.min.js`）
2. 或手动从 jsdelivr 下载 `echarts@5.4.3/dist/echarts.min.js` 放到工具同目录
3. 之后全部离线可用

### 陷阱 7：向量库 vecinfo 解析失败

**现象**：`ValueError: 目录中有 N 个 .txt，但没有任何文件首行为 0x 开头的 IO 模式字`

**排查**：新项目的向量文件格式可能不同。DFT Test Tool V3.1 格式是 **首行 0x 开头的 IO 模式字 + 后续每行 128bit 激励**。如果新项目向量格式不同（如无 IO 模式字、位宽不是 128bit），需修改 `parse_vector_file` 函数和 `BYTES_PER_LINE` 常量。

---

## 7. 移植清单（Checklist）

| # | 项目 | 位置 | 难度 | 必需？ |
|---|------|------|------|--------|
| 1 | 复制目录 | 文件系统 | ⭐ | ✅ |
| 2 | `columns` 别名 | `lb3tools_project.py` | ⭐⭐ | ✅ |
| 3 | `clock_scale` / `voltage_scale` | `lb3tools_project.py` | ⭐ | ✅ |
| 4 | 结果词表 | `lb3tools_project.py` | ⭐⭐ | ✅ |
| 5 | 芯片名正则 | `lb3tools_project.py` | ⭐⭐ | ✅ |
| 6 | 温度正则 | `lb3tools_project.py` | ⭐⭐ | ✅ |
| 7 | `nominal_v_priority` | `lb3tools_project.py` | ⭐ | ✅ |
| 8 | `nominal_freqs` | `lb3tools_project.py` | ⭐ | ✅ |
| 9 | `vector_categories` | `lb3tools_project.py` | ⭐⭐⭐ | 可选 |
| 10 | `vector_group()` + `_GROUP_RE` | `lb3tools_core.py` | ⭐⭐⭐ | 分组命名不同时 |
| 11 | `XDMA_PART_LINES` / `BYTES_PER_LINE` | `lb3tools_core.py` | ⭐⭐ | DFT 版本不同时 |
| 12 | 失效阈值（0.9 / 0.6 / 0.3） | `lb3tools_core.py` | ⭐⭐ | 良率口径不同时 |
| 13 | `_short_vec()` 前缀列表 | `lb3tools_html.py` | ⭐ | ✅ |
| 14 | HTML 显示文本（MBIST 标签 / 标题 / Footer） | `lb3tools_html.py` | ⭐ | ✅ |
| 15 | 低频基准频率 / Fmax 掉档阈值 | `lb3tools_html.py` | ⭐⭐ | 标称频率不同时 |
| 16 | 加载测试 | 命令行 | ⭐ | ✅ |
| 17 | 良率验证 | 命令行 | ⭐ | ✅ |
| 18 | HTML 视觉验证 | 浏览器 | ⭐ | ✅ |

---

## 附录：lb3tools_project.py 完整模板

新项目可直接复制以下模板，逐项填写：

```python
# -*- coding: utf-8 -*-
"""<新项目> 项目适配配置"""

PROJECT = {
    'name': '<新项目名>',

    # CSV 列名别名（必需字段: vector / clock / voltage / result）
    'columns': {
        'vector':      ['Vector Name', 'Vector', 'Pattern', '向量名'],
        'clock':       ['Clock/MHz', 'Clock', 'Frequency/MHz', '频率/MHz'],
        'voltage':     ['Set Voltage/mV', 'Voltage/mV', '电压/mV'],
        'read_vddl':   ['Read VDDL/mV', 'VDDL/mV'],
        'error_count': ['Error Count', '错误计数'],
        'result':      ['Test Result', 'Result', 'Status', '结果'],
    },

    # 单位换算（乘法系数）
    'clock_scale':   1.0,     # 目标: MHz
    'voltage_scale': 1.0,     # 目标: mV

    # 测试结果词表（大小写不敏感）
    'pass_values':       ['PASS'],
    'chip_fail_values':  ['FAIL'],
    'equip_fail_values': ['CLOCKSETFAIL', 'READERROR'],

    # 芯片名/温度正则
    'chip_name_pattern':   r'(TT|FS|SF|FF|SS)\d{2}',
    'temp_chip_pattern':   r'(?:TT|FS|SF|FF|SS)\d{2}_(-?\d+)',
    'temp_batch_patterns': [r'(-?\d+)c', r'temp(-?\d+)'],

    # 标称条件
    'nominal_v_priority': [750.0, 700.0, 800.0, 650.0, 850.0, 900.0,
                           600.0, 950.0, 550.0, 500.0],
    'nominal_freqs':      [20.0, 25.0],

    # 向量分类（HTML 卡片，按列表顺序优先匹配）
    'vector_categories': [
        {'key': 'nominal', 'display': '标称向量', 'lib': 0,
         'cond': '标称条件', 'match': []},  # 兜底
    ],
}
```
