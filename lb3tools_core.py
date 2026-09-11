#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LB3 测试数据工具 - 核心模块
============================
数据源(两种, 自动识别):
  1) 芯片子文件夹中的 *_error_count.csv
     列: Vector Name, Clock/MHz, Set Voltage/mV, Read VDDL/mV, Error Count, Test Result
  2) 批级 chart 汇总 xlsx(每颗芯片一个 sheet, 块结构:
     "Vector: xxx" / "Clock/MHz \\ Set Voltage/mV" / 数据行)

功能:
  - error_count 汇总   (总览 / 失败明细 / 向量统计)
  - Shmoo 矩阵汇总    (频率×电压 Pass 矩阵 + Vmin/Fmax 提取, 带颜色标注)
  - 良率统计          (标称条件判定 + 失效模式自动分类)
  - 向量库信息        (IO模式字指纹表 / 库概览 / 测试数据×向量库交叉校验)
"""

import csv
import os
import re
import sys
from collections import defaultdict

import openpyxl
from openpyxl.styles import PatternFill, Font

PASS_FILL = PatternFill('solid', fgColor='C6EFCE')   # 全通过 - 绿
FAIL_FILL = PatternFill('solid', fgColor='FFC7CE')   # 全失败 - 红
PART_FILL = PatternFill('solid', fgColor='FFEB9C')   # 部分通过 - 黄
HEAD_FILL = PatternFill('solid', fgColor='DDEBF7')   # 表头 - 蓝
BOLD = Font(bold=True)

# ================================================================
# 项目适配配置: 从 lb3tools_project.py 加载(缺省键回落到内置默认值)。
# 移植到其他项目时只需修改 lb3tools_project.py, 分析/渲染逻辑零改动。
# ================================================================
_DEFAULT_PROJECT = {
    'name': 'LB3',
    'columns': {
        'vector':      ['Vector Name', 'Vector', 'Pattern', 'Pattern Name',
                        'Test Name', '向量名'],
        'clock':       ['Clock/MHz', 'Clock', 'Frequency/MHz', 'Frequency',
                        'Freq', '频率/MHz'],
        'voltage':     ['Set Voltage/mV', 'Voltage/mV', 'Set Voltage', 'Voltage',
                        '电压/mV'],
        'read_vddl':   ['Read VDDL/mV', 'Read VDDL', 'VDDL/mV'],
        'error_count': ['Error Count', 'ErrorCount', '错误计数'],
        'result':      ['Test Result', 'Result', 'Status', '结果'],
    },
    'clock_scale':   1.0,
    'voltage_scale': 1.0,
    'pass_values':       ['PASS'],
    'chip_fail_values':  ['FAIL'],
    'equip_fail_values': ['CLOCKSETFAIL', 'READERROR'],
    'chip_name_pattern':   r'(TT|FS|SF|FF|SS)\d{2}',
    'temp_chip_pattern':   r'(?:TT|FS|SF|FF|SS)\d{2}_(-?\d+)',
    'temp_batch_patterns': [r'(-?\d+)c', r'temp(-?\d+)'],
    'nominal_v_priority': [750.0, 700.0, 800.0, 650.0, 850.0, 900.0,
                           600.0, 950.0, 550.0, 500.0],
    'nominal_freqs':      [20.0, 25.0],
}
try:
    from lb3tools_project import PROJECT as _USER_PROJECT
except ImportError:
    _USER_PROJECT = {}
PROJ = dict(_DEFAULT_PROJECT)
PROJ.update({k: v for k, v in (_USER_PROJECT or {}).items() if v is not None})

# 结果词表(集合, 大小写不敏感比较)
_PASS_SET = {v.strip().upper() for v in PROJ['pass_values']}
_CHIP_FAIL_SET = {v.strip().upper() for v in PROJ['chip_fail_values']}
_EQUIP_FAIL_SET = {v.strip().upper() for v in PROJ['equip_fail_values']}

_GROUP_RE = re.compile(r'_(G\d)(?=[_.])')


# ================================================================ 数据加载

def find_error_count_csvs(root):
    """递归查找所有 error_count.csv, 返回 [(芯片名, 路径)]"""
    out = []
    for dirpath, _, files in os.walk(root):
        for fn in sorted(files):
            if fn.lower().endswith('.csv') and 'error_count' in fn.lower():
                out.append((os.path.basename(dirpath), os.path.join(dirpath, fn)))
    return out


def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _resolve_columns(fieldnames):
    """把 csv 表头映射到标准字段(别名匹配, 忽略大小写与空格)。
    返回 {标准字段: 实际列名}; 缺少必需字段时抛出带指引的 ValueError。"""
    if not fieldnames:
        raise ValueError('csv 表头为空')
    norm = {}
    for f in fieldnames:
        if f:
            norm[re.sub(r'\s+', '', str(f)).lower()] = f
    out = {}
    missing = []
    for std, aliases in PROJ['columns'].items():
        for a in aliases:
            key = re.sub(r'\s+', '', a).lower()
            if key in norm:
                out[std] = norm[key]
                break
        else:
            if std in ('vector', 'clock', 'voltage', 'result'):
                missing.append(std)
    if missing:
        raise ValueError(
            'csv 缺少必需列: %s (实际表头: %s)。请在 lb3tools_project.py 的 '
            "'columns' 中为目标 csv 配置列名别名。" % (missing, list(fieldnames)))
    return out


def parse_error_count_csv(path):
    """解析单颗芯片的 error_count.csv → [row dict]
    列名通过 lb3tools_project.py 的别名映射识别, 单位经 scale 换算为 MHz/mV。"""
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        col = _resolve_columns(reader.fieldnames)
        cs = float(PROJ.get('clock_scale', 1.0) or 1.0)
        vs = float(PROJ.get('voltage_scale', 1.0) or 1.0)
        for r in reader:
            try:
                rows.append({
                    'vector': (r[col['vector']] or '').strip(),
                    'clock': float(r[col['clock']]) * cs,
                    'voltage': float(r[col['voltage']]) * vs,
                    'read_vddl': _to_float(r.get(col['read_vddl']))
                        if 'read_vddl' in col else None,
                    'error_count': int(r[col['error_count']])
                        if ('error_count' in col
                            and r.get(col['error_count']) not in (None, ''))
                        else None,
                    'result': (r[col['result']] or '').strip(),
                })
            except (KeyError, ValueError, TypeError):
                continue
    return rows


def parse_chart_xlsx(path):
    """解析批级 chart xlsx → {芯片名(sheet): [row dict]}"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    data = {}
    for ws in wb.worksheets:
        rows, vec, volts = [], None, []
        for raw in ws.iter_rows(values_only=True):
            a = raw[0]
            if isinstance(a, str) and a.startswith('Vector:'):
                vec = a.split(':', 1)[1].strip()
            elif isinstance(a, str) and a.startswith('Clock'):
                volts = [c for c in raw[1:] if c is not None]
            elif isinstance(a, (int, float)) and vec:
                for i, c in enumerate(raw[1:]):
                    if c is None or i >= len(volts):
                        continue
                    rows.append({
                        'vector': vec,
                        'clock': float(a),
                        'voltage': float(volts[i]),
                        'read_vddl': None,
                        'error_count': None,
                        'result': str(c).strip(),
                    })
        if rows:
            data[ws.title] = rows
    wb.close()
    return data


def _normalize_chip_name(name):
    """提取芯片名(规则来自 lb3tools_project.py 的 chip_name_pattern)。
    只保留芯片核心代码，去掉所有前缀(工艺PDK0/PDK1、应力AL/De/EM等)和
    后缀(温度_0/_-25、应力_EMC/_Default等)。
    例: PDK1_TT02_0 → TT02, PDK0_ALTT06 → TT06, FF11_EMC → FF11"""
    m = re.search(PROJ['chip_name_pattern'], name)
    if m:
        return m.group(0)
    return name


def _extract_temperature(name):
    """从文件夹名提取温度后缀(规则来自 temp_chip_pattern), 返回整数或 None。
    例: PDK1_TT02_0 → 0, PDK1_TT02_-25 → -25, PDK1_TT10_85 → 85,
        PDK1_TT10_125 → 125, PDK1_TT02(无后缀) → None(常温)"""
    m = re.search(PROJ['temp_chip_pattern'], name)
    if m:
        return int(m.group(1))
    return None


def _extract_batch_temperatures(name):
    """从批次文件夹名提取温度列表(回退用, 当芯片文件夹无温度后缀时)。
    规则来自 temp_batch_patterns: 匹配 XXc (如 85c→85) 或 tempXX (如 temp-25→-25)。"""
    temps = set()
    for pat in PROJ['temp_batch_patterns']:
        for m in re.finditer(pat, name):
            temps.add(int(m.group(1)))
    return sorted(temps)


def load_inputs(path):
    """智能加载: .xlsx → chart 模式; 目录 → csv 递归模式; 单个 .csv → 单芯片"""
    if os.path.isfile(path):
        bn = os.path.basename(path)
        if path.lower().endswith('.xlsx'):
            if 'error_count' in bn.lower():
                name = _normalize_chip_name(os.path.splitext(bn)[0])
                temp = _extract_temperature(bn)
                rows = parse_error_count_xlsx(path)
                for r in rows:
                    r['temp'] = temp
                return {name: rows}
            data = parse_chart_xlsx(path)
            for rows in data.values():
                for r in rows:
                    r['temp'] = None
            return data
        if path.lower().endswith('.csv'):
            name = _normalize_chip_name(os.path.splitext(bn)[0])
            temp = _extract_temperature(bn)
            rows = parse_error_count_csv(path)
            for r in rows:
                r['temp'] = temp
            return {name: rows}
        raise ValueError('不支持的文件类型(仅支持 .xlsx/.csv/目录): ' + path)
    if os.path.isdir(path):
        found = find_error_count_csvs(path)
        if not found:
            raise FileNotFoundError('目录下未找到任何 *error_count*.csv: ' + path)
        # 批次文件夹名回退提取温度(当芯片文件夹无温度后缀时)
        # 规则: 芯片子文件夹名后缀(TT10_85/TT02_-25/TT02_0)是权威来源;
        #       批次名仅含一个温度标记(85c/125c/temp-25/temp0)时才兜底;
        #       都没有 = 常温; 批次名含多个温度但芯片无后缀 = 歧义, 按常温并警告
        batch_name = os.path.basename(os.path.normpath(path))
        batch_temps = _extract_batch_temperatures(batch_name)
        if len(batch_temps) > 1:
            print('警告: 批次名含多个温度标记%s, 但部分芯片文件夹无温度后缀, '
                  '无法确定各芯片温度, 无后缀的芯片将按常温处理。'
                  '建议将芯片子文件夹命名为 <芯片名>_<温度> (如 PDK1_TT10_85)。'
                  % batch_temps, file=sys.stderr)
        fallback_temp = batch_temps[0] if len(batch_temps) == 1 else None
        chips = {}
        for chip, p in found:
            norm = _normalize_chip_name(chip)
            temp = _extract_temperature(chip)
            if temp is None:
                temp = fallback_temp
            rows = parse_error_count_csv(p)
            for r in rows:
                r['temp'] = temp
            if norm in chips:
                chips[norm].extend(rows)
            else:
                chips[norm] = rows
        return chips
    raise FileNotFoundError('路径不存在: ' + path)


# ================================================================ 通用分析

# 设备/环境侧异常结果词表见 PROJ['equip_fail_values'](lb3tools_project.py)


def is_fail(row):
    """任何非 Pass 结果(Fail / ReadError / ClockSetFail 等, 词表见 lb3tools_project.py)"""
    return row['result'].strip().upper() not in _PASS_SET


def is_chip_fail(row):
    """芯片相关失败(仅 chip_fail_values, 排除设备侧异常)"""
    return row['result'].strip().upper() in _CHIP_FAIL_SET


def is_equip_fail(row):
    """设备/环境侧异常(ClockSetFail / ReadError 等), 不计入芯片失效"""
    return row['result'].strip().upper() in _EQUIP_FAIL_SET


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


def nominal_rows(rows, nominal_v=None, nominal_fs=None):
    """筛选标称条件下的测试点"""
    out = rows
    if nominal_v is not None:
        out = [r for r in out if abs(r['voltage'] - nominal_v) < 1e-6]
    if nominal_fs:
        out = [r for r in out if any(abs(r['clock'] - f) < 1e-6 for f in nominal_fs)]
    return out


# 标称电压优先级见 PROJ['nominal_v_priority'](lb3tools_project.py)


def auto_nominal_voltage(chips):
    """自动探测标称电压:
    1) 若批次仅含 1 个电压档(快测) → 直接采用
    2) 多电压档(Shmoo) → 按项目配置的标称电压优先级选择批次中存在的最高优先档
       (优先级列表见 lb3tools_project.py 的 nominal_v_priority)"""
    cnt = defaultdict(int)
    for rows in chips.values():
        for r in rows:
            cnt[r['voltage']] += 1
    if not cnt:
        return None
    if len(cnt) == 1:
        return next(iter(cnt))
    for v in PROJ['nominal_v_priority']:
        if v in cnt:
            return v
    return max(cnt, key=cnt.get)


def auto_nominal_freqs(chips, nominal_v):
    """自动探测标称频率: 标称电压下的频点数
    - ≤3 个频点(快测批次) → 返回全部(即为标称频点)
    - >3 个(Shmoo 批次)   → 返回项目配置的标称频点(lb3tools_project.py 的
      nominal_freqs, LB3 为 20/25), 保证可判定"""
    cnt = defaultdict(int)
    for rows in chips.values():
        for r in rows:
            if abs(r['voltage'] - nominal_v) < 1e-6:
                cnt[r['clock']] += 1
    if not cnt:
        return None
    freqs = sorted(cnt)
    if len(freqs) <= 3:
        return freqs
    std = [f for f in PROJ['nominal_freqs'] if f in cnt]
    if std:
        return std
    mid = freqs[len(freqs) // 2: len(freqs) // 2 + 2]
    return mid


def classify_chip(rows, sys_vectors=None):
    """失效模式自动分类 → (类别, 说明)
    sys_vectors: 系统性失败向量集合(跨芯片普遍失败的向量, 判定时剔除)
    规则:
      - 无失败点            → Pass
      - 失败点 ≥ 90%        → 芯片级失效(测试通路/电源系统缺陷)
      - 某分组失败点 ≥ 60%   → 分组级失效(该存储器分组硬缺陷)
      - 其余                → 边缘失败(零星/向量级速度边缘)
    注: ClockSetFail/ReadError 为设备侧无效数据点, 不参与任何判定
        (不判 Fail 也不单独归类), 仅记录数量供日志/明细展示
    """
    if sys_vectors:
        rows = [r for r in rows if r['vector'] not in sys_vectors]
    n = len(rows)
    if n == 0:
        return '无数据', '未找到测试点'
    fails = [r for r in rows if is_chip_fail(r)]
    equips = [r for r in rows if is_equip_fail(r)]
    equip_note = (' (+%d 个ClockSetFail/ReadError数据点, 不参与判定)'
                  % len(equips)) if equips else ''
    if not fails:
        return 'Pass', '全部测试点通过%s' % equip_note
    if len(fails) >= 0.9 * n:
        return '芯片级失效', '%d/%d 点失败, 疑似测试通路/芯片级缺陷' % (len(fails), n)
    g_stat = defaultdict(lambda: [0, 0])   # 组 → [总数, 失败数]
    for r in rows:
        g = vector_group(r['vector'])
        g_stat[g][0] += 1
        if is_chip_fail(r):
            g_stat[g][1] += 1
    for g in sorted(g_stat):
        tot, bad = g_stat[g]
        if tot >= 8 and bad >= 0.6 * tot:
            return '分组级失效(%s)' % g, '%s 组 %d/%d 点失败%s' % (g, bad, tot, equip_note)
    return '边缘失败', '%d/%d 点零星失败%s' % (len(fails), n, equip_note)


def find_systematic_vectors(chips, nominal_v=None, nominal_fs=None,
                            ratio=0.3):
    """识别系统性失败向量: 标称点下在 ≥ ratio 比例芯片上失败的向量
    (向量级设计/规范问题, 而非单颗芯片缺陷)"""
    vec_fail = defaultdict(int)
    vec_seen = defaultdict(int)
    for rows in chips.values():
        rn = nominal_rows(rows, nominal_v, nominal_fs)
        per = defaultdict(int)
        for r in rn:
            if is_chip_fail(r):
                per[r['vector']] += 1
        for v in per:
            vec_fail[v] += 1
        for v in {r['vector'] for r in rn}:
            vec_seen[v] += 1
    n = len(chips)
    return {v for v in vec_fail
            if vec_seen.get(v) and vec_fail[v] >= ratio * max(n, 1)}


# ================================================================ Shmoo 分析

def build_matrix(rows, vector_sub=None):
    """构建 (频率, 电压) → [通过数, 总数] 矩阵
    vector_sub: 向量名子串过滤(不区分大小写), None 表示聚合全部向量"""
    m = defaultdict(lambda: [0, 0])
    for r in rows:
        if vector_sub and vector_sub.lower() not in r['vector'].lower():
            continue
        key = (r['clock'], r['voltage'])
        m[key][1] += 1
        if not is_fail(r):
            m[key][0] += 1
    return m


def shmoo_params(matrix):
    """提取窗口参数(全通过判据):
    Vmin[f]  = 频率 f 全通过的最低电压
    Fmax[v]  = 电压 v 全通过的最高频率"""
    vmin, fmax = {}, {}
    freqs = sorted({f for f, _ in matrix})
    volts = sorted({v for _, v in matrix})
    for f in freqs:
        vs = [v for v in volts
              if matrix[(f, v)][1] and matrix[(f, v)][0] == matrix[(f, v)][1]]
        vmin[f] = min(vs) if vs else None
    for v in volts:
        fs = [f for f in freqs
              if matrix[(f, v)][1] and matrix[(f, v)][0] == matrix[(f, v)][1]]
        fmax[v] = max(fs) if fs else None
    return vmin, fmax


# ================================================================ 报告输出

def _set_width(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def _style_header(ws, row, ncol):
    for c in range(1, ncol + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = BOLD
        cell.fill = HEAD_FILL


def write_errcount_report(chips, out_path):
    """error_count 汇总报告: 总览 / 失败明细 / 向量统计"""
    wb = openpyxl.Workbook()

    # --- 总览 ---
    ws = wb.active
    ws.title = '总览'
    ws.append(['芯片', '测试点数', 'Pass', 'Fail/ReadError', '失败向量数',
               '最大ErrorCount', '判定'])
    for chip in sorted(chips):
        rows = chips[chip]
        fails = [r for r in rows if is_fail(r)]
        max_ec = max((r['error_count'] for r in rows
                      if r['error_count'] is not None), default=0)
        ws.append([chip, len(rows), len(rows) - len(fails), len(fails),
                   len({r['vector'] for r in fails}), max_ec,
                   'Pass' if not fails else 'Fail'])
    _set_width(ws, {'A': 22, 'B': 10, 'C': 8, 'D': 14, 'E': 12, 'F': 15, 'G': 8})
    _style_header(ws, 1, 7)

    # --- 失败明细 ---
    ws2 = wb.create_sheet('失败明细')
    ws2.append(['芯片', '向量', '时钟/MHz', '电压/mV', '实测VDDL/mV',
                'ErrorCount', '结果'])
    for chip in sorted(chips):
        for r in chips[chip]:
            if is_fail(r):
                ws2.append([chip, r['vector'], r['clock'], r['voltage'],
                            r['read_vddl'], r['error_count'], r['result']])
    _set_width(ws2, {'A': 20, 'B': 60, 'C': 10, 'D': 10, 'E': 13, 'F': 12, 'G': 10})
    _style_header(ws2, 1, 7)

    # --- 向量统计(跨芯片) ---
    ws3 = wb.create_sheet('向量统计')
    ws3.append(['向量', '出现芯片数', '全通过芯片数', '失败芯片数', '最大ErrorCount'])
    v_stat = defaultdict(lambda: [0, 0, 0, 0])
    for chip, rows in chips.items():
        per_vec = defaultdict(list)
        for r in rows:
            per_vec[r['vector']].append(r)
        for v, rs in per_vec.items():
            v_stat[v][0] += 1
            if any(is_fail(r) for r in rs):
                v_stat[v][2] += 1
            else:
                v_stat[v][1] += 1
            v_stat[v][3] = max(v_stat[v][3],
                               max((r['error_count'] for r in rs
                                    if r['error_count'] is not None), default=0))
    for v in sorted(v_stat):
        t, p, f_, e = v_stat[v]
        ws3.append([v, t, p, f_, e])
    _set_width(ws3, {'A': 60, 'B': 12, 'C': 14, 'D': 12, 'E': 15})
    _style_header(ws3, 1, 5)

    wb.save(out_path)
    return {'chips': len(chips)}


def write_shmoo_report(chips, out_path, vector_sub=None):
    """Shmoo 汇总报告: 每芯片一个矩阵 sheet + 参数汇总 sheet"""
    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = '窗口参数汇总'
    ws_sum.append(['芯片', 'Vmin@各频率(mV)', 'Fmax@750mV(MHz)',
                   '全通过最低Vmin', '最高全通过Fmax'])
    _set_width(ws_sum, {'A': 20, 'B': 46, 'C': 16, 'D': 16, 'E': 16})
    _style_header(ws_sum, 1, 5)

    for chip in sorted(chips):
        m = build_matrix(chips[chip], vector_sub)
        if not m:
            continue
        vmin, fmax = shmoo_params(m)
        freqs = sorted({f for f, _ in m})
        volts = sorted({v for _, v in m})

        ws = wb.create_sheet(chip[:31])
        ws.append(['Shmoo 矩阵: %s%s' % (
            chip, ('  向量过滤: ' + vector_sub) if vector_sub else '  (全部向量聚合)')])
        ws.append([])
        ws.append(['MHz \\ mV'] + [int(v) if v == int(v) else v for v in volts])
        _style_header(ws, 3, len(volts) + 1)
        for f in freqs:
            line = [int(f) if f == int(f) else f]
            for v in volts:
                p, t = m[(f, v)]
                if not t:
                    line.append(None)
                    continue
                cell_val = '%d/%d' % (p, t)
                line.append(cell_val)
            ws.append(line)
            r = ws.max_row
            for ci, v in enumerate(volts, start=2):
                p, t = m[(f, v)]
                if not t:
                    continue
                fill = PASS_FILL if p == t else (FAIL_FILL if p == 0 else PART_FILL)
                ws.cell(row=r, column=ci).fill = fill
        # 窗口参数
        ws.append([])
        ws.append(['Vmin(该频率全通过的最低电压/mV):'])
        ws.append(['频率/MHz'] + [int(f) if f == int(f) else f for f in freqs])
        ws.append(['Vmin/mV'] + [vmin[f] if vmin[f] is not None else '无' for f in freqs])
        ws.append([])
        ws.append(['Fmax(该电压全通过的最高频率/MHz):'])
        ws.append(['电压/mV'] + [int(v) if v == int(v) else v for v in volts])
        ws.append(['Fmax/MHz'] + [fmax[v] if fmax[v] is not None else '无' for v in volts])
        _set_width(ws, {'A': 26})
        for col in 'BCDEFGHIJKL':
            ws.column_dimensions[col].width = 9

        # 汇总行
        vs_ok = [v for v in vmin.values() if v is not None]
        fs_ok = [f for f in fmax.values() if f is not None]
        vmin_str = ', '.join('%gMHz→%gmV' % (f, vmin[f])
                             for f in freqs if vmin[f] is not None)
        f750 = fmax.get(750.0) or fmax.get(750)
        ws_sum.append([chip, vmin_str or '无全通过点',
                       f750 if f750 is not None else '无',
                       min(vs_ok) if vs_ok else '无',
                       max(fs_ok) if fs_ok else '无'])

    wb.save(out_path)
    return {'chips': len(chips)}


def write_yield_report(chips, out_path, nominal_v=None, nominal_fs=None):
    """良率统计报告: 总览(含失效分类) + 系统性向量 + 失败明细
    输出双良率: 严格良率 / 剔除系统性向量后的调整良率
    nominal_v / nominal_fs 传 'auto' 时自动探测"""
    auto_note = ''
    if nominal_v == 'auto' or nominal_v is None:
        nominal_v = auto_nominal_voltage(chips)
        auto_note += '电压自动探测=%smV ' % nominal_v
    if nominal_fs == 'auto':
        fs = auto_nominal_freqs(chips, nominal_v)
        if fs is None:
            auto_note += '(Shmoo批次, 频率未过滤) '
        nominal_fs = fs
    sys_vectors = find_systematic_vectors(chips, nominal_v, nominal_fs)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '良率总览'
    ws.append(['芯片', '标称测试点', '失败点(严格)', '失败点(剔除系统向量)',
               '设备侧异常', '失效类别', '说明'])
    cats_strict = defaultdict(int)
    cats_adj = defaultdict(int)
    result_rows = []
    for chip in sorted(chips):
        rows_n = nominal_rows(chips[chip], nominal_v, nominal_fs)
        cat_s, _ = classify_chip(rows_n)                      # 严格判定
        cat_a, desc = classify_chip(rows_n, sys_vectors)      # 剔除系统性向量
        cats_strict[cat_s] += 1
        cats_adj[cat_a] += 1
        nfail_s = sum(1 for r in rows_n if is_chip_fail(r))
        rows_adj = [r for r in rows_n if r['vector'] not in sys_vectors]
        nfail_a = sum(1 for r in rows_adj if is_chip_fail(r))
        nequip = sum(1 for r in rows_adj if is_equip_fail(r))
        ws.append([chip, len(rows_n), nfail_s, nfail_a, nequip, cat_a, desc])
        result_rows.append((chip, rows_n, cat_a, desc, nfail_a))

    total = len(chips)
    npass_s = cats_strict.get('Pass', 0)
    npass_a = cats_adj.get('Pass', 0)
    cond_str = '%smV × %sMHz %s' % (
        nominal_v, nominal_fs if nominal_fs else '全部',
        ('(%s)' % auto_note) if auto_note else '')
    ws.append([])
    ws.append(['判定条件', cond_str])
    ws.append(['样本总数', total])
    ws.append(['严格良率  (全部标称点通过)',
               '%d/%d = %.1f%%' % (npass_s, total,
                                   100.0 * npass_s / total if total else 0)])
    ws.append(['调整良率  (剔除系统性失败向量)',
               '%d/%d = %.1f%%' % (npass_a, total,
                                   100.0 * npass_a / total if total else 0)])
    ws.append([])
    ws.append(['失效类别分布(剔除系统性向量后):'])
    ws.append(['注: ClockSetFail/ReadError 为设备侧无效数据点, 不参与任何判定',
               '(既不算Pass也不算Fail), 仅记录于"设备侧异常"列与同名sheet供参考'])
    for cat in sorted(cats_adj):
        ws.append([cat, cats_adj[cat]])
    _set_width(ws, {'A': 40, 'B': 14, 'C': 15, 'D': 20, 'E': 12, 'F': 24, 'G': 46})
    _style_header(ws, 1, 7)
    for r in range(ws.max_row - len(cats_adj) - 5, ws.max_row + 1):
        ws.cell(row=r, column=1).font = BOLD

    # --- 系统性向量 sheet ---
    if sys_vectors:
        ws3 = wb.create_sheet('系统性失败向量')
        ws3.append(['向量名', '说明: 该向量在 ≥30% 芯片的标称点上失败,',
                    '属于向量级设计/规范问题而非单颗芯片缺陷'])
        for v in sorted(sys_vectors):
            ws3.append([v])
        _set_width(ws3, {'A': 60, 'B': 55, 'C': 30})
        _style_header(ws3, 1, 3)

    # --- 设备侧异常 sheet (ClockSetFail/ReadError, 建议复测) ---
    equip_rows = []
    for chip in sorted(chips):
        rows_n = nominal_rows(chips[chip], nominal_v, nominal_fs)
        rows_adj = [r for r in rows_n if r['vector'] not in sys_vectors]
        for r in rows_adj:
            if is_equip_fail(r):
                equip_rows.append((chip, r))
    if equip_rows:
        ws4 = wb.create_sheet('设备侧异常')
        ws4.append(['芯片', '向量', '时钟/MHz', '电压/mV', 'ErrorCount',
                    '结果', '说明: ClockSetFail=时钟设置失败, ReadError=电源回读失败,',
                    '属设备侧无效数据点, 不参与良率/失效判定, 仅供参考'])
        for chip, r in equip_rows:
            ws4.append([chip, r['vector'], r['clock'], r['voltage'],
                        r['error_count'], r['result']])
        _set_width(ws4, {'A': 18, 'B': 58, 'C': 10, 'D': 10, 'E': 12, 'F': 14,
                         'G': 40, 'H': 30})
        _style_header(ws4, 1, 8)

    # --- 失败明细(仅非 Pass 芯片, 标称点, 仅芯片相关Fail) ---
    ws2 = wb.create_sheet('失败明细')
    ws2.append(['芯片', '失效类别', '向量', '时钟/MHz', '电压/mV',
                'ErrorCount', '结果'])
    for chip, rows_n, cat, _, _ in result_rows:
        if cat == 'Pass':
            continue
        for r in rows_n:
            if is_chip_fail(r):
                ws2.append([chip, cat, r['vector'], r['clock'], r['voltage'],
                            r['error_count'], r['result']])
    _set_width(ws2, {'A': 18, 'B': 22, 'C': 58, 'D': 10, 'E': 10, 'F': 12, 'G': 10})
    _style_header(ws2, 1, 7)

    wb.save(out_path)
    return {'total': total,
            'pass_strict': npass_s,
            'yield_strict': 100.0 * npass_s / total if total else 0.0,
            'pass': npass_a,
            'yield': 100.0 * npass_a / total if total else 0.0,
            'categories': dict(cats_adj),
            'systematic_vectors': sorted(sys_vectors),
            'equip_abnormal_count': len(equip_rows),
            'nominal_v': nominal_v,
            'nominal_fs': nominal_fs}


# ================================================================ 向量库分析
# 向量文件格式(依据 DFT Test Tool V3.1 文档):
#   第 1 行: IO 模式选择值(16进制), 加载时写入 IO_MODE_SEL 寄存器(0x2C)
#   第 2 行起: 每行一个测试周期(cycle)的 128 位并行激励
# 派生公式:
#   vector_size = 总行数 - 1          (写入 VECTOR_LINE_SIZE 寄存器)
#   dump_len    = (总行数 - 1) * 16   (字节, 每行 128bit = 16B)
#   total_parts = vector_size // 8192 + 1  (XDMA H2C 分包数, 每包 8192 行)

XDMA_PART_LINES = 8192   # 每个 XDMA 分包的向量行数
BYTES_PER_LINE = 16      # 每行 128 bit = 16 字节


def parse_vector_file(path):
    """解析单个向量文件 → dict(io_mode, cycles, width, dump_bytes, xdma_parts)
    io_mode: 首行 IO 模式选择值(int, 解析失败为 None)
    cycles:  激励行数(= 总行数 - 1, 即 VECTOR_LINE_SIZE)
    width:   激励数据最大位宽
    dump_bytes / xdma_parts: 按文档公式推导"""
    io_mode, cycles, width = None, 0, 0
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if io_mode is None and line.lower().startswith('0x'):
                try:
                    io_mode = int(line, 16)
                    continue
                except ValueError:
                    pass
            cycles += 1
            if len(line) > width:
                width = len(line)
    return {'io_mode': io_mode, 'cycles': cycles, 'width': width,
            'dump_bytes': cycles * BYTES_PER_LINE,
            'xdma_parts': cycles // XDMA_PART_LINES + 1}


def scan_vector_library(lib_dir):
    """扫描向量库目录(递归) → {相对文件夹: [向量信息dict]}
    向量信息: name / io_mode / cycles / width / dump_bytes / xdma_parts / group"""
    result = {}
    for dirpath, _, filenames in os.walk(lib_dir):
        txts = [fn for fn in sorted(filenames) if fn.endswith('.txt')]
        if not txts:
            continue
        rel = os.path.relpath(dirpath, lib_dir)
        infos = []
        for fn in txts:
            p = parse_vector_file(os.path.join(dirpath, fn))
            p['name'] = fn
            p['group'] = vector_group(fn)
            infos.append(p)
        result[rel] = infos
    return result


def build_fingerprint(lib):
    """由库信息构建 IO模式字→分组 指纹表 → {分组: {IO模式字: [向量名...]}}
    依据: 向量文件名提取分组, 同分组收集全部 IO 模式字"""
    fp = defaultdict(lambda: defaultdict(list))
    for infos in lib.values():
        for v in infos:
            if v['io_mode'] is not None:
                fp[v['group']]['0x%X' % v['io_mode']].append(v['name'])
    return fp


def cross_check_vectors(chips, lib):
    """交叉校验: 测试数据中出现的向量 vs 向量库
    → (tested_missing, lib_unused): 测了但库无源文件 / 库有但从未测过"""
    tested = set()
    for rows in chips.values():
        for r in rows:
            tested.add(r['vector'])
    lib_names = set()
    for infos in lib.values():
        for v in infos:
            lib_names.add(v['name'])
    return sorted(tested - lib_names), sorted(lib_names - tested)


def write_vecinfo_report(lib_dir, out_path, chips=None):
    """向量库信息报告:
    Sheet1 库概览(文件夹/向量数/cycle统计/IO模式字宽度)
    Sheet2 分组指纹表(分组×IO模式字)
    Sheet3 向量明细(全部向量: 文件夹/名称/IO模式字/cycle/dump字节/分包数/分组)
    Sheet4 交叉校验(可选, 需提供测试数据chips)"""
    lib = scan_vector_library(lib_dir)
    if not lib:
        raise FileNotFoundError('向量库目录中未找到 .txt 向量文件: ' + lib_dir)
    # 合法性校验: 向量文件首行应为 0x 开头的 IO 模式字。
    # 若全部文件都解析不出 IO 模式字, 说明该目录不是向量库(误指普通目录)
    n_valid = sum(1 for infos in lib.values() for v in infos
                  if v['io_mode'] is not None)
    n_total = sum(len(infos) for infos in lib.values())
    if n_total and n_valid == 0:
        raise ValueError(
            '目录 %s 中有 %d 个 .txt, 但没有任何文件首行为 0x 开头的 '
            'IO 模式字——请确认这是向量库目录(如 /LB3/VECTOR)' % (lib_dir, n_total))
    fp = build_fingerprint(lib)

    wb = openpyxl.Workbook()

    # --- 库概览 ---
    ws = wb.active
    ws.title = '库概览'
    ws.append(['文件夹', '向量数', '总cycle', '最长向量cycle',
               'IO模式字宽度范围', '总dump字节'])
    for folder in sorted(lib):
        infos = lib[folder]
        total_c = sum(v['cycles'] for v in infos)
        max_c = max(v['cycles'] for v in infos)
        hw = [v['io_mode'].bit_length() for v in infos
              if v['io_mode'] is not None]
        rng = ('%d~%d bit' % (min(hw), max(hw))) if hw else '-'
        total_d = sum(v['dump_bytes'] for v in infos)
        ws.append([folder, len(infos), total_c, max_c, rng, total_d])
    _set_width(ws, {'A': 30, 'B': 10, 'C': 14, 'D': 16, 'E': 16, 'F': 14})
    _style_header(ws, 1, 6)

    # --- 分组指纹表 ---
    ws2 = wb.create_sheet('分组指纹表')
    ws2.append(['分组', 'IO模式字(IO_MODE_SEL)', '向量数', '向量名(示例)'])
    for g in sorted(fp):
        for h in sorted(fp[g], key=lambda x: int(x, 16)):
            names = fp[g][h]
            ws2.append([g, h, len(names),
                        ', '.join(n[:40] for n in names[:2]) +
                        (' 等' if len(names) > 2 else '')])
    _set_width(ws2, {'A': 10, 'B': 22, 'C': 10, 'D': 70})
    _style_header(ws2, 1, 4)

    # --- 向量明细 ---
    ws3 = wb.create_sheet('向量明细')
    ws3.append(['文件夹', '向量名', 'IO模式字', 'cycle数', 'dump字节',
                'XDMA分包数', '位宽', '分组'])
    for folder in sorted(lib):
        for v in sorted(lib[folder], key=lambda x: x['name']):
            ws3.append([folder, v['name'],
                        '0x%X' % v['io_mode'] if v['io_mode'] is not None else '-',
                        v['cycles'], v['dump_bytes'], v['xdma_parts'],
                        v['width'], v['group']])
    _set_width(ws3, {'A': 26, 'B': 62, 'C': 14, 'D': 10, 'E': 12, 'F': 12,
                     'G': 8, 'H': 8})
    _style_header(ws3, 1, 8)

    # --- 交叉校验(可选) ---
    ret = {'folders': len(lib),
           'vectors': sum(len(v) for v in lib.values()),
           'groups': len(fp)}
    if chips is not None:
        tested_missing, lib_unused = cross_check_vectors(chips, lib)
        ws4 = wb.create_sheet('交叉校验')
        ws4.append(['类别', '数量', '说明'])
        ws4.append(['测试数据中出现, 但向量库无源文件', len(tested_missing),
                    '需补充向量源文件或核对命名'])
        ws4.append(['向量库中有, 但测试数据从未使用', len(lib_unused),
                    '未被该批次使用的向量(可能用于其他批次)'])
        _style_header(ws4, 1, 3)
        ws4.append([])
        ws4.append(['—— 测试数据中出现但库中缺失的向量 ——'])
        for v in tested_missing:
            ws4.append([v])
        ws4.append([])
        ws4.append(['—— 库中未被该批次测试的向量 ——'])
        for v in lib_unused:
            ws4.append([v])
        _set_width(ws4, {'A': 62, 'B': 10, 'C': 40})
        ret['tested_missing'] = tested_missing
        ret['lib_unused'] = lib_unused
    wb.save(out_path)
    return ret
