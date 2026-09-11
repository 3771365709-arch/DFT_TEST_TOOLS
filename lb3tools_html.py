#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LB3 测试数据工具 - HTML 网页报告模块
=====================================
将测试数据分析结果生成为单文件 HTML 看板(内嵌 ECharts, 离线可用):
  - 总览页: 批次信息 / 良率统计卡片 / 失效类别饼图
  - 全量矩阵页: 向量×频率(纵) × 芯片×电压(横) 四维热力图(按温度分图, 标称点蓝框标注)
  - 向量页: 失败向量排行柱状图
用法(经 lb3tools_core 调用):
  write_html_report(chips, 'report.html', nominal_v='auto', nominal_fs='auto')
"""

import json
import os
import re
import time
from collections import defaultdict

import lb3tools_core as core

# ECharts 库来源: 优先本地同目录 echarts.min.js, 其次尝试下载, 最后回退 CDN
_ECHARTS_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'echarts.min.js')
_ECHARTS_CDN = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'
_ECHARTS_URL = 'https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js'


def _get_echarts_js():
    """获取 ECharts 脚本内容(本地→下载→CDN 三级回退)"""
    if os.path.isfile(_ECHARTS_LOCAL):
        with open(_ECHARTS_LOCAL, encoding='utf-8') as f:
            return f.read(), 'local'
    try:
        import urllib.request
        req = urllib.request.Request(_ECHARTS_URL,
                                     headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read().decode('utf-8')
        # 顺手保存供下次离线使用
        try:
            with open(_ECHARTS_LOCAL, 'w', encoding='utf-8') as f:
                f.write(data)
        except OSError:
            pass
        return data, 'downloaded'
    except Exception:
        return None, 'cdn'


# ---------------------------------------------------------------- 数据组织

def _yield_stats(chips, nominal_v, nominal_fs):
    """复用 core 的良率逻辑, 收集网页所需统计"""
    sys_vectors = core.find_systematic_vectors(chips, nominal_v, nominal_fs)
    rows = []
    for chip in sorted(chips):
        rn = core.nominal_rows(chips[chip], nominal_v, nominal_fs)
        cat, desc = core.classify_chip(rn, sys_vectors)
        rows_adj = [r for r in rn if r['vector'] not in sys_vectors]
        nfail = sum(1 for r in rows_adj if core.is_chip_fail(r))
        rows.append({'chip': chip, 'points': len(rows_adj),
                     'fails': nfail, 'cat': cat, 'desc': desc})
    cats = {}
    for r in rows:
        cats[r['cat']] = cats.get(r['cat'], 0) + 1
    return {'rows': rows, 'categories': cats, 'sys_vectors': sorted(sys_vectors),
            'npass': cats.get('Pass', 0), 'total': len(rows)}


def _shmoo_data(chips, vector_sub=None):
    """每芯片的 Shmoo 矩阵 → {芯片: {freqs, volts, values[[通过数]], totals}}"""
    out = {}
    for chip, rows in chips.items():
        m = core.build_matrix(rows, vector_sub)
        if not m:
            continue
        freqs = sorted({f for f, _ in m})
        volts = sorted({v for _, v in m})
        vals = []
        for f in freqs:
            row = []
            for v in volts:
                p, t = m[(f, v)]
                ratio = (p / t) if t else None
                row.append(round(ratio, 3) if ratio is not None else None)
            vals.append(row)
        out[chip] = {'freqs': freqs, 'volts': volts, 'values': vals}
    return out


def _vector_fails(chips, top=25):
    """失败向量排行: 向量 → 失败点数(跨芯片)"""
    vf = {}
    for rows in chips.values():
        for r in rows:
            if core.is_chip_fail(r):
                vf[r['vector']] = vf.get(r['vector'], 0) + 1
    items = sorted(vf.items(), key=lambda x: -x[1])[:top]
    return [{'name': n, 'fails': c} for n, c in items]


# ---------------------------------------------------------------- HTML 模板

def _html_page(title, echarts_js, echarts_mode, meta_html, body, footer_html, script):
    stamp = time.strftime('%Y-%m-%d %H:%M:%S')
    if echarts_js:
        echarts_tag = '<script>%s</script>' % echarts_js
        note = 'ECharts: 内嵌(离线可用, %s)' % echarts_mode
    else:
        echarts_tag = ('<script src="%s"></script>' % _ECHARTS_CDN)
        note = 'ECharts: CDN(需联网)'
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
<style>
  :root{
    --bg:#0b1220; --panel:#121c30; --panel2:#0f1830; --line:#1e2c4a;
    --txt:#e8eefb; --sub:#8fa3c8; --dim:#5b6c8f;
    --green:#22c07a; --red:#f4515c; --amber:#f5a623; --blue:#3d8bff; --gray:#3a4a6b;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);
       font-family:"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;
       padding:28px 32px 48px;}
  .wrap{max-width:1440px;margin:0 auto}
  header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;
         gap:12px;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:20px}
  h1{font-size:26px;font-weight:700;letter-spacing:.5px}
  h1 .tag{display:inline-block;vertical-align:middle;margin-left:12px;font-size:12px;
          font-weight:500;color:var(--blue);border:1px solid var(--blue);
          border-radius:4px;padding:2px 8px;letter-spacing:1px}
  .meta{color:var(--sub);font-size:13px;line-height:1.8;text-align:right}
  .meta b{color:var(--txt)}
  /* KPI */
  .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:20px}
  .kpi{background:linear-gradient(160deg,var(--panel),var(--panel2));
       border:1px solid var(--line);border-radius:12px;padding:18px 20px}
  .kpi .label{font-size:13px;color:var(--sub);margin-bottom:8px}
  .kpi .value{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums}
  .kpi .foot{font-size:12px;color:var(--dim);margin-top:6px}
  .kpi.good .value{color:var(--green)}
  .kpi.bad .value{color:var(--red)}
  .kpi.warn .value{color:var(--amber)}
  .kpi.info .value{color:var(--blue)}
  /* alert */
  .alert{display:flex;gap:16px;align-items:flex-start;
         background:linear-gradient(90deg,rgba(244,81,92,.14),rgba(244,81,92,.03));
         border:1px solid rgba(244,81,92,.45);border-radius:12px;
         padding:16px 20px;margin-bottom:20px}
  .alert .icon{font-size:22px;line-height:1.4}
  .alert h3{color:var(--red);font-size:15px;margin-bottom:6px}
  .alert p{color:var(--sub);font-size:13.5px;line-height:1.75}
  .alert p b{color:var(--txt)}
  .alert.ok{background:linear-gradient(90deg,rgba(34,192,122,.12),rgba(34,192,122,.02));
            border-color:rgba(34,192,122,.4)}
  .alert.ok h3{color:var(--green)}
  /* panels grid */
  .grid{display:grid;grid-template-columns:7fr 5fr;gap:14px;margin-bottom:20px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
  .panel h2{font-size:15px;font-weight:600;margin-bottom:4px}
  .panel .hint{font-size:12px;color:var(--dim);margin-bottom:8px}
  .chart{width:100%%;height:340px}
  .chart.tall{height:420px}
  .full{grid-column:1/-1}
  [id^="heatmap_"]{height:560px}
  /* category cards */
  .cats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}
  .cat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
  .cat h3{font-size:14px;color:var(--sub);font-weight:600;margin-bottom:10px}
  .cat .num{font-size:26px;font-weight:700;color:var(--blue)}
  .cat ul{list-style:none;margin-top:10px}
  .cat li{font-size:12.5px;color:var(--sub);padding:4px 0;border-top:1px dashed var(--line)}
  .cat li span{float:right;font-variant-numeric:tabular-nums}
  .pill{display:inline-block;font-size:11px;border-radius:3px;padding:1px 6px;margin-left:6px}
  .pill.p{color:var(--green);background:rgba(34,192,122,.12)}
  .pill.f{color:var(--red);background:rgba(244,81,92,.12)}
  /* table */
  table{width:100%%;border-collapse:collapse;font-size:12.5px}
  th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
  th{color:var(--sub);font-weight:600;background:var(--panel2);position:sticky;top:0}
  td.vec{font-family:"Consolas","Menlo",monospace;color:#c8d6f0}
  td.fail{color:var(--red);font-weight:600}
  td.r{text-align:right;font-family:Consolas,Menlo,monospace}
  .tbl-wrap{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:8px}
  .legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--sub);margin-top:6px}
  .dot{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
  /* vector category summary */
  .vcats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}
  .vcat{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
  .vcat.dim{opacity:.45}
  .vcat h4{font-size:13px;color:var(--sub);font-weight:600;margin-bottom:2px}
  .vcat .cond{font-size:11px;color:var(--dim);margin-bottom:8px}
  .vcat .num{font-size:26px;font-weight:700;color:var(--blue);font-variant-numeric:tabular-nums}
  .vcat .num small{font-size:13px;color:var(--sub);font-weight:400}
  .vcat .badge{display:inline-block;font-size:11px;border-radius:4px;padding:2px 8px;margin:8px 0 6px}
  .vcat ul{list-style:none;margin:0;padding:0}
  .vcat li{font-size:12px;color:var(--sub);padding:4px 0;border-top:1px dashed var(--line);display:flex;justify-content:space-between;gap:8px}
  .vcat li b{color:var(--txt);font-variant-numeric:tabular-nums;font-weight:600}
  @media(max-width:1000px){.vcats{grid-template-columns:repeat(2,1fr)}}
  /* data summary */
  .summary{margin-top:20px}
  .summary-block{margin-bottom:18px}
  .summary-block:last-child{margin-bottom:0}
  .summary-block h3{font-size:13.5px;font-weight:600;color:var(--blue);margin-bottom:10px;
    padding-left:10px;border-left:3px solid var(--blue)}
  .summary-block p{font-size:13.5px;line-height:1.9;color:var(--txt);margin:0}
  .summary-block ul{margin:0;padding-left:20px}
  .summary-block li{font-size:13px;line-height:2;color:var(--sub)}
  .summary-block li b{color:var(--txt);font-weight:600}
  .tag-g{color:var(--green);font-weight:600}
  .tag-r{color:var(--red);font-weight:600}
  .tag-a{color:var(--amber);font-weight:600}
  footer{margin-top:28px;color:var(--dim);font-size:12px;text-align:center;line-height:1.8}
  @media(max-width:1000px){.kpis{grid-template-columns:repeat(2,1fr)}
    .grid{grid-template-columns:1fr}.cats{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div><h1>%s<span class="tag">MBIST</span></h1></div>
    <div class="meta">%s</div>
  </header>
%s
  <footer>%s</footer>
</div>
%s
<script>
%s
</script>
</body>
</html>''' % (title, title, meta_html, body, footer_html, echarts_tag, script)


# ---------------------------------------------------------------- 主入口

def write_html_report(chips, out_path, title=None, nominal_v='auto',
                      nominal_fs='auto', vector_sub=None, heatmap_mode='auto'):
    """生成单文件 HTML 测试报告
    chips: load_inputs() 的结果
    out_path: 输出 .html 路径
    nominal_v / nominal_fs: 'auto' 或显式值(同 write_yield_report)
    vector_sub: Shmoo 向量过滤子串(可选)
    heatmap_mode: 'auto'=由csv频压组合数自动判定 / 'nominal'=强制标称 / 'sweep'=强制扫频扫压"""
    n_chips = len(chips)
    if title is None:
        title = 'LB3 测试数据报告 (%d 颗芯片)' % n_chips

    # ---- 数据准备 ----
    auto_note = ''
    if nominal_v == 'auto' or nominal_v is None:
        nominal_v = core.auto_nominal_voltage(chips)
        auto_note += '电压自动探测=%smV ' % nominal_v
    if nominal_fs == 'auto':
        fs = core.auto_nominal_freqs(chips, nominal_v)
        nominal_fs = fs
    ys = _yield_stats(chips, nominal_v, nominal_fs)
    vfails = _vector_fails(chips)

    echarts_js, echarts_mode = _get_echarts_js()
    if echarts_js:
        note = 'ECharts: 内嵌(离线可用, %s)' % echarts_mode
    else:
        note = 'ECharts: CDN(需联网)'

    total_pts = sum(len(v) for v in chips.values())
    def _g(x):
        return '%g' % x
    nv_lab = _g(nominal_v) if nominal_v is not None else '自动'
    fs_lab = ('/'.join(_g(f) for f in nominal_fs)) if nominal_fs else '全部'
    cond = '%smV × %sMHz' % (nv_lab, fs_lab)

    # ---- 向量名简称(去前缀/后缀, 用于图内标签) ----
    def _short_vec(v):
        s = v[:-4] if v.endswith('.txt') else v
        for p in ('LB3_MemoryBist_P1_', 'LB3_MemoryBist_', 'LB3_'):
            if s.startswith(p):
                return s[len(p):]
        return s

    # ---- 向量清单(标称条件, 供统计口径使用) ----
    chip_names = sorted(chips.keys())
    vec_set = set()
    for c in chip_names:
        for r in core.nominal_rows(chips[c], nominal_v, nominal_fs):
            vec_set.add(r['vector'])
    vectors = sorted(vec_set)

    # ---- 温度分组与排序: 低温(0/-25) → 常温(None, 视作25°C) → 高温(85/125) ----
    # 温度来源优先级: 芯片子文件夹名后缀(TT10_85) > 批次文件夹名(85c/temp-25, 仅单温度时兜底)
    # > 无任何温度标记 = 常温; 每个温度独立一张分图, 同页显示不合并
    all_temps_set = set()
    for c in chip_names:
        for r in chips[c]:
            all_temps_set.add(r.get('temp'))
    temps_sorted_inner = sorted(all_temps_set,
                                key=lambda t: 25.0 if t is None else t)

    def _temp_label(t):
        return '常温' if t is None else ('%d°C' % t)

    # ---- 电压频率配置模式(前置选择逻辑): nominal=标称 / sweep=扫频扫压 ----
    # 由 csv 实际内容自动判定: 频压组合 ≤3 组(如 750mV×20/25MHz) → 标称;
    # 组合多(如 500-950mV × 10-45MHz = 80 组) → 扫频扫压; 可用 --heatmap-mode 强制指定
    vf_pairs = set()
    for rows in chips.values():
        for r in rows:
            vf_pairs.add((r['clock'], r['voltage']))
    if heatmap_mode not in ('nominal', 'sweep'):
        heatmap_mode = 'nominal' if len(vf_pairs) <= 3 else 'sweep'
    nvp = len(vf_pairs)
    if nvp:
        _vs = sorted({v for _, v in vf_pairs})
        _fs = sorted({f for f, _ in vf_pairs})
        vf_range = '%g-%gmV × %g-%gMHz' % (_vs[0], _vs[-1], _fs[0], _fs[-1])
    else:
        vf_range = '-'

    # ---- 向量×芯片 热力图数据(按温度分图), 悬停展开格内频压明细 ----
    # status[向量][芯片]: nominal 模式 0=Pass/1=Fail/2=无数据;
    #                     sweep 模式 0=全Pass/1=全Fail/2=无数据/3=部分Fail
    # pts[向量][芯片] = 频压点状态数组(频率主序×电压副序), 与 freqs×volts 网格对应,
    #   悬停时渲染成 频率×电压 小格矩阵; 无数据单元格为 null
    full_matrices = []
    for t in temps_sorted_inner:
        results = {}
        for c in chip_names:
            for r in chips[c]:
                if r.get('temp') != t:
                    continue
                key = (r['vector'], c, r['clock'], r['voltage'])
                results.setdefault(key, set()).add(r['result'].strip().upper())
        if not results:
            continue
        t_vecs = sorted({k[0] for k in results})
        t_chips = sorted({k[1] for k in results})
        t_freqs = sorted({k[2] for k in results})
        t_volts = sorted({k[3] for k in results})
        nfv, nff = len(t_volts), len(t_freqs)
        ci = {c: i for i, c in enumerate(t_chips)}
        gi = {v: i for i, v in enumerate(t_vecs)}
        fi_ = {f: i for i, f in enumerate(t_freqs)}
        oi_ = {v: i for i, v in enumerate(t_volts)}

        def _st(res):
            if res == {'PASS'}:
                return 0
            if 'FAIL' in res:
                return 1
            if res <= {'CLOCKSETFAIL', 'READERROR'}:
                return 3
            return 1

        pts2d = [[None] * len(t_chips) for _ in t_vecs]
        status = [[2] * len(t_chips) for _ in t_vecs]
        ratio = [[None] * len(t_chips) for _ in t_vecs]
        tmp = {}
        for (vec, c, f, v), res in results.items():
            arr = tmp.setdefault((gi[vec], ci[c]), [2] * (nff * nfv))
            arr[fi_[f] * nfv + oi_[v]] = _st(res)
        for (a, b), arr in tmp.items():
            pts2d[a][b] = arr
            sts = [s for s in arr if s != 2]
            if not sts:
                status[a][b] = 2
                continue
            npass = sum(1 for s in sts if s == 0)
            ratio[a][b] = round(npass / len(sts), 3)
            if heatmap_mode == 'nominal':
                status[a][b] = 0 if npass == len(sts) else 1
            else:
                if npass == len(sts):
                    status[a][b] = 0
                elif npass == 0:
                    status[a][b] = 1
                else:
                    status[a][b] = 3
        full_matrices.append({
            'label': _temp_label(t),
            'chips': t_chips,
            'vecs': [_short_vec(v) for v in t_vecs],
            'freqs': ['%g' % x for x in t_freqs],
            'volts': ['%g' % x for x in t_volts],
            'mode': heatmap_mode,
            'status': status,
            'ratio': ratio,
            'pts': pts2d,
        })

    # ---- 窗口法着色标记: 琥珀=窗口异常格(低频失效 / Fmax@750 掉档), 与数据总结判据一致 ----
    if heatmap_mode == 'sweep' and full_matrices:
        # 先算每格 Fmax@750(数值) 与 15MHz 失败占比
        for fm in full_matrices:
            fnums = [float(x) for x in fm['freqs']]
            vnums = [float(x) for x in fm['volts']]
            nfv = len(vnums)
            vi750 = vnums.index(750.0) if 750.0 in vnums else None
            fi15 = fnums.index(15.0) if 15.0 in fnums else None
            fm['fmax750'] = [[None] * len(fm['chips']) for _ in fm['vecs']]
            fm['low15'] = [[0] * len(fm['chips']) for _ in fm['vecs']]
            for i in range(len(fm['vecs'])):
                for j in range(len(fm['chips'])):
                    pts = fm['pts'][i][j]
                    if not pts:
                        continue
                    if vi750 is not None:
                        for fi in range(len(fnums) - 1, -1, -1):
                            if pts[fi * nfv + vi750] == 0:
                                fm['fmax750'][i][j] = fnums[fi]
                                break
                    if fi15 is not None:
                        fails15 = sum(1 for vi in range(nfv)
                                      if pts[fi15 * nfv + vi] == 1)
                        fm['low15'][i][j] = 1 if fails15 / nfv >= 0.5 else 0
        # 向量级批次内最好 Fmax@750(跨芯片/温度), 用于掉档判定
        vec_best = {}
        for fm in full_matrices:
            for i, vn in enumerate(fm['vecs']):
                for j in range(len(fm['chips'])):
                    f = fm['fmax750'][i][j]
                    if f is not None and (vn not in vec_best or f > vec_best[vn]):
                        vec_best[vn] = f
        # 异常标记: 低频失效 或 Fmax 掉档 ≥10MHz(2个频率档)
        for fm in full_matrices:
            fm['anom'] = [[0] * len(fm['chips']) for _ in fm['vecs']]
            for i, vn in enumerate(fm['vecs']):
                for j in range(len(fm['chips'])):
                    low15 = fm['low15'][i][j]
                    f = fm['fmax750'][i][j]
                    drop = (vec_best.get(vn) - f >= 10.0) \
                        if (f is not None and vn in vec_best) else 0
                    fm['anom'][i][j] = 1 if (low15 or drop) else 0

    # ---- 向量分类总结(对应《LB3测试进度汇总》: 1个标称 + 3个扫频扫压) ----
    # 类别定义/库总数/匹配规则来自 lb3tools_project.py 的 vector_categories
    # (顺序 = 优先级, match 命中即归类; 未命中 → 兜底 nominal 卡 = 标称独有)
    _VCATS = core.PROJ.get('vector_categories') or []
    _FALLBACK_KEY = next((c['key'] for c in _VCATS if not c.get('match')),
                         'nominal')
    _LIB_TOTAL = {c['key']: c.get('lib', 0) for c in _VCATS}
    _CAT_ORDER = {c['key']: c.get('order', 99) for c in _VCATS}
    _CAT_DISPLAY = {c['key']: c for c in _VCATS if c.get('display')
                    and not c.get('hidden')}

    def _cat_matches(cat, name):
        s = name[:-4] if name.endswith('.txt') else name
        return any(re.search(rx, s) for rx in cat.get('match', []))

    def _vec_family(name):
        for cat in _VCATS:
            if _cat_matches(cat, name):
                return cat['key']
        return _FALLBACK_KEY

    if heatmap_mode == 'sweep':
        name_list = sorted({_short_vec(v) for v in
                            (r['vector'] for rows in chips.values() for r in rows)})
    else:
        name_list = sorted({r['vector'] for rows in chips.values() for r in rows})
    fams = defaultdict(list)
    for _v in name_list:
        fams[_vec_family(_v)].append(_v)

    vec_has_fail = {}
    anom_vecs = set()
    if heatmap_mode == 'nominal':
        for c, rows in chips.items():
            for r in core.nominal_rows(rows, nominal_v, nominal_fs):
                if core.is_chip_fail(r):
                    vec_has_fail[r['vector']] = True
    else:
        for fm2 in full_matrices:
            for i, vn in enumerate(fm2['vecs']):
                for j in range(len(fm2['chips'])):
                    rr = fm2['ratio'][i][j]
                    if rr is not None and rr > 0:
                        vec_has_fail[vn] = True
                    if fm2['anom'][i][j]:
                        anom_vecs.add(vn)

    def _tested_of(cat):
        if cat == 'nominal':
            return name_list if heatmap_mode == 'nominal' else []
        if heatmap_mode != 'sweep':
            return []
        return [v for v in name_list if _vec_family(v) == cat]

    # 卡片渲染顺序: 兜底(标称)卡在前, 其余按配置的 order 字段
    _CATS_META = [(c['key'], c['display'], c.get('cond', ''))
                  for c in _VCATS if c.get('display') and not c.get('hidden')]
    _CATS_META.sort(key=lambda t: (0 if t[0] == _FALLBACK_KEY else 1,
                                   _CAT_ORDER.get(t[0], 99)))
    cat_cards = []
    for cat, cname, ccond in _CATS_META:
        tested = _tested_of(cat)
        n, total = len(tested), _LIB_TOTAL[cat]
        nfail = sum(1 for v in tested if vec_has_fail.get(v))
        nanom = len([v for v in tested if v in anom_vecs]) \
            if heatmap_mode == 'sweep' else 0
        dim = ' dim' if n == 0 else ''
        if n == 0:
            note = '本批次未按标称测试' if cat == 'nominal' else '本批次未测'
            badge = ('<span class="badge" style="color:#5b6c8f;'
                     'border:1px solid var(--line)">%s</span>' % note)
        elif nfail == 0:
            badge = ('<span class="badge" style="color:#22c07a;'
                     'border:1px solid rgba(34,192,122,.5)">全部 Pass</span>')
        elif nanom > 0:
            badge = ('<span class="badge" style="color:#f5a623;'
                     'border:1px solid rgba(245,166,35,.5)">%d 条存在 Fail'
                     '(含 %d 条窗口异常)</span>' % (nfail, nanom))
        else:
            badge = ('<span class="badge" style="color:#f5a623;'
                     'border:1px solid rgba(245,166,35,.5)">%d 条存在 Fail</span>'
                     % nfail)
        rows = ['<li><span>库内向量</span><b>%d 条</b></li>' % total,
                '<li><span>本批次已测</span><b>%d 条</b></li>' % n]
        if cat == _FALLBACK_KEY and heatmap_mode == 'nominal' and n:
            shown = 0
            for c2 in sorted(_VCATS, key=lambda c: c.get('order', 99)):
                if c2['key'] == cat or c2.get('hidden') or not c2.get('display'):
                    continue
                t2 = len(fams.get(c2['key'], []))
                if c2.get('count_shared_from'):
                    t2 += sum(1 for v in fams.get(c2['count_shared_from'], [])
                              if _cat_matches(c2, v))
                t2 = min(t2, c2.get('lib', 0))   # 按库总数封顶(超出部分计入未归类)
                shown += t2
                short_name = c2['display'].replace(' 向量', '')
                rows.append('<li><span>├ %s 类</span><b>%d/%d</b></li>'
                            % (short_name, t2, c2.get('lib', 0)))
            rows.append('<li><span>└ 未归入上述类别</span><b>%d</b></li>'
                        % (n - shown))
        else:
            rows.append('<li><span>全向量 Pass</span><b>%d 条</b></li>' % (n - nfail))
            rows.append('<li><span>存在 Fail</span><b>%d 条</b></li>' % nfail)
            if heatmap_mode == 'sweep':
                rows.append('<li><span>窗口异常</span><b>%d 条</b></li>' % nanom)
        cat_cards.append(
            '<div class="vcat%s"><h4>%s</h4><div class="cond">%s</div>'
            '<div class="num">%d<small> / %d 条</small></div>%s<ul>%s</ul></div>'
            % (dim, cname, ccond, n, total, badge, ''.join(rows)))
    _hint_parts = ['%s = %d条(%s)' % (c['display'], c.get('lib', 0),
                                      c.get('cond', ''))
                   for c in _VCATS if c.get('display') and not c.get('hidden')]
    vcat_html = (
        '<div class="panel full" style="margin-bottom:20px">'
        '<h2>向量分类总结（对应测试进度：按向量库分类）</h2>'
        '<div class="hint">按《LB3测试进度汇总》与向量库分类：'
        + '；'.join(_hint_parts) +
        '；数字为 本批次已测/库内总数</div>'
        '<div class="vcats">' + ''.join(cat_cards) + '</div></div>')

    # 每颗芯片 fail 点数(标称): 与良率判定同口径, 仅统计芯片相关 FAIL,
    # 不把 ClockSetFail/ReadError 等设备侧异常算进 Fail
    chip_fails = []
    for c in chip_names:
        nr = core.nominal_rows(chips[c], nominal_v, nominal_fs)
        fails = sum(1 for r in nr if core.is_chip_fail(r))
        chip_fails.append(fails)

    # 散点 fail 列表(标称条件下芯片相关 FAIL 的 向量,芯片,频率,电压,温度)
    scattered = []
    for c in chip_names:
        for r in core.nominal_rows(chips[c], nominal_v, nominal_fs):
            if core.is_chip_fail(r):
                scattered.append([r['vector'], c, r['clock'], r['voltage'], r.get('temp')])
    scattered.sort(key=lambda x: x[0])

    # 温度文本(含常温)
    temp_text = '、'.join(_temp_label(t) for t in temps_sorted_inner)

    # 最差芯片(fail 最多)
    worst_idx = max(range(len(chip_names)), key=lambda i: chip_fails[i])
    worst_chip = chip_names[worst_idx]
    worst_fails = chip_fails[worst_idx]
    total_fails = sum(chip_fails)

    # ---- meta(头部右侧) ----
    meta_html = ('数据源：<b>%s 批次 · error_count 原始数据</b><br>'
                 '向量数：<b>%d</b>　·　芯片数：<b>%d</b>　·　判定条件：<b>%s</b><br>'
                 '生成时间：<b>%s</b>' % (
        title.split('(')[0].strip(), len(vectors), n_chips, cond,
        time.strftime('%Y-%m-%d %H:%M:%S')))

    # ---- KPI 卡片 ----
    yield_pct = (100.0 * ys['npass'] / ys['total']) if ys['total'] else 0
    n_fail = ys['total'] - ys['npass']
    yield_color = 'good' if yield_pct >= 80 else ('warn' if yield_pct >= 50 else 'bad')
    kpis = '''
  <div class="kpis">
    <div class="kpi info"><div class="label">芯片数量</div><div class="value">%d</div>
      <div class="foot">共 %d 颗被测芯片</div></div>
    <div class="kpi info"><div class="label">测试温度</div><div class="value" style="font-size:22px">%s</div>
      <div class="foot">从文件夹名后缀提取</div></div>
    <div class="kpi info"><div class="label">测试点总数</div><div class="value">%d</div>
      <div class="foot">标称条件下 %d 个测试点</div></div>
    <div class="kpi good"><div class="label">全向量 Pass 芯片</div><div class="value">%d</div>
      <div class="foot">芯片级通过</div></div>
    <div class="kpi bad"><div class="label">存在 Fail 芯片</div><div class="value">%d</div>
      <div class="foot">含边缘失败与分组级失效</div></div>
    <div class="kpi %s"><div class="label">调整良率</div><div class="value">%.1f%%</div>
      <div class="foot">%d / %d 颗芯片全 Pass</div></div>
  </div>''' % (n_chips, n_chips, temp_text, total_pts, len(vectors) * n_chips,
             ys['npass'], n_fail, yield_color, yield_pct, ys['npass'], ys['total'])

    # ---- alert 提示框 ----
    alert_html = ''
    if worst_fails > 0 and total_fails > 0:
        pct = 100.0 * worst_fails / total_fails if total_fails else 0
        alert_html += '''
  <div class="alert">
    <div class="icon">⚠️</div>
    <div>
      <h3>关键发现：%s 在 %d 条向量上失效（占总 fail 的 %.1f%%）</h3>
      <p><b>%s</b> 在标称条件下 %d / %d 条向量 fail，%s。建议优先排查该芯片是否存在系统性问题。</p>
    </div>
  </div>''' % (worst_chip, worst_fails, pct, worst_chip, worst_fails, len(vectors),
              '覆盖全部向量，指向芯片自身缺陷' if worst_fails == len(vectors)
              else '失败向量分布需结合热力图判断')
    if len(ys['sys_vectors']) > 0:
        alert_html += '''
  <div class="alert ok">
    <div class="icon">✅</div>
    <div>
      <h3>系统性失败向量 %d 条，其余散点 fail 分布无明显聚集</h3>
      <p>剔除系统性失败向量后，<b>%d 颗芯片全向量 Pass</b>；其余芯片的散点 fail 建议结合 fail bitmap 确认是否为真实 memory 缺陷。</p>
    </div>
  </div>''' % (len(ys['sys_vectors']), ys['npass'])
    if not alert_html:
        alert_html = '''
  <div class="alert ok">
    <div class="icon">✅</div>
    <div>
      <h3>全部 %d 颗芯片在标称条件下全向量 Pass</h3>
      <p>所有测试点均通过，无失败记录。</p>
    </div>
  </div>''' % n_chips

    # ---- body 主体 ----
    if heatmap_mode == 'nominal':
        hm_title = '向量 × 芯片 标称热力图（按温度分图）'
        hm_hint = ('标称配置 %s（每格 %d 个频压点）：绿=Pass，红=Fail，灰=无数据；'
                   '鼠标悬停格子显示格内频压点明细' % (cond, nvp))
    else:
        hm_title = '向量 × 芯片 扫频扫压热力图（按温度分图）'
        hm_hint = ('扫频扫压配置 %s = 每格 %d 个频压点：绿=正常窗口(含部分Fail角点)，'
                   '琥珀=窗口异常(15MHz低频失效 或 Fmax@750掉档≥10MHz)，红=全Fail，'
                   '空白=无数据；鼠标悬停格子显示频×压明细矩阵' % (vf_range, nvp))
    # 每个温度一个热力图 div
    hm_divs = ''
    for i, fm in enumerate(full_matrices):
        hm_divs += '''
      <h3 style="color:#8fa3c8;margin:16px 0 4px">▎ %s</h3>
      <div id="heatmap_f_%d"></div>''' % (fm['label'], i)
    # ---- 测试条件一览(静态表格, 每芯片实际扫频扫压范围) ----
    cond_rows = []
    for c in chip_names:
        freqs_c = sorted({r['clock'] for r in chips[c]})
        volts_c = sorted({r['voltage'] for r in chips[c]})
        temps_c = sorted({t for t in (r.get('temp') for r in chips[c])},
                         key=lambda x: (x is None, x if x is not None else 0))
        t_lab = '、'.join('常温' if t is None else '%d°C' % t for t in temps_c)
        f_lab = '、'.join('%g' % f for f in freqs_c) or '-'
        v_lab = '、'.join('%g' % v for v in volts_c) or '-'
        cond_rows.append(
            '<tr><td class="vec">%s</td><td class="r">%s</td>'
            '<td class="r">%s <span style="color:#5b6c8f">(%d点)</span></td>'
            '<td class="r">%s <span style="color:#5b6c8f">(%d点)</span></td>'
            '<td class="r">%s</td></tr>'
            % (c, t_lab, f_lab, len(freqs_c), v_lab, len(volts_c), cond))
    cond_table = '''
  <div class="panel full" style="margin-bottom:20px">
    <h2>测试条件一览（频率 / 电压）</h2>
    <div class="hint">每颗芯片实际测试的频率点与电压点；"标称判定条件"列为向量×芯片矩阵的取点依据，Shmoo 图中对应 ★ 标注</div>
    <div class="tbl-wrap" style="max-height:360px">
      <table>
        <thead><tr><th>芯片</th><th>温度</th><th class="r">频率点 / MHz</th><th class="r">电压点 / mV</th><th class="r">标称判定条件</th></tr></thead>
        <tbody>%s</tbody>
      </table>
    </div>
  </div>''' % ''.join(cond_rows)

    body = kpis + alert_html + vcat_html + '''
  <div class="grid">
    <div class="panel">
      <h2>各芯片 Fail 向量数</h2>
      <div class="hint">标称条件下，每颗芯片的 fail 向量数；红色为失效最多的芯片</div>
      <div id="bar" class="chart"></div>
    </div>
    <div class="panel">
      <h2>芯片级结果构成（%d 颗芯片）</h2>
      <div class="hint">一颗芯片在全部向量上 pass 才算通过</div>
      <div id="donut" class="chart"></div>
    </div>
    <div class="panel full">
      <h2>%s</h2>
      <div class="hint">%s</div>%s
      <div class="legend">
        <span><span class="dot" style="background:#1d8f5f"></span>正常窗口(含部分Fail角点)</span>
        <span><span class="dot" style="background:#f5a623"></span>窗口异常(低频失效/Fmax掉档, 仅扫频扫压)</span>
        <span><span class="dot" style="background:#e5484d"></span>全 Fail</span>
        <span><span class="dot" style="background:#3a4a6b"></span>无数据(空白)</span>
        <span style="color:#5b6c8f">悬停格子查看频压点明细</span>
      </div>
    </div>
  </div>

%s

  <div class="panel full" style="margin-bottom:20px">
    <h2>失败向量 TOP (按失败芯片数)</h2>
    <div class="hint">按在多少颗芯片上 fail 排序，系统性失败向量会排到前面</div>
    <div id="vfails" class="chart tall"></div>
  </div>

  <div class="panel full" style="margin-bottom:0">
    <h2>Fail 明细（标称条件下，共 %d 处）</h2>
    <div class="hint">每条记录为一个 (向量, 芯片) 在标称条件下 fail</div>
    <div class="tbl-wrap">
      <table id="failTbl">
        <thead><tr><th>#</th><th>向量名称</th><th>Fail 芯片</th><th>温度</th><th>频率</th><th>电压</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>''' % (n_chips, hm_title, hm_hint, hm_divs, cond_table, len(scattered))

    # ---- 数据总结(文字) ----
    cats = ys['categories']
    n_sys = len(ys['sys_vectors'])
    adj_fails = {r['chip']: r['fails'] for r in ys['rows']}
    # 概要(客观输出, 不加主观评价词汇)
    if yield_pct >= 80:
        ytag = 'tag-g'
    elif yield_pct >= 50:
        ytag = 'tag-a'
    else:
        ytag = 'tag-r'
    overview = (
        '本批次共 <b>%d</b> 颗芯片，测试温度 <b>%s</b>，标称判定条件为 <b>%s</b>，'
        '覆盖 <b>%d</b> 个测试向量。调整后（剔除系统性失败向量 %d 个）'
        '<b>%d</b> 颗芯片全向量通过，<b>%d</b> 颗存在 Fail，'
        '调整良率 <b class="%s">%.1f%%</b>。'
        % (n_chips, temp_text, cond, len(vectors), n_sys, ys['npass'], n_fail,
           ytag, yield_pct))
    worst_chip_adj = max(adj_fails, key=adj_fails.get)
    worst_fails_adj = adj_fails[worst_chip_adj]
    if worst_fails_adj > 0:
        overview += '失效最严重的芯片为 <b class="tag-r">%s</b>（%d 个 fail 向量）。' % (
            worst_chip_adj, worst_fails_adj)
    # 细则
    detail_items = []
    detail_items.append('芯片总数 <b>%d</b>，其中通过 <b class="tag-g">%d</b> 颗、失效 <b class="tag-r">%d</b> 颗' % (
        n_chips, ys['npass'], n_fail))
    cat_order = [('Pass', 'tag-g'), ('芯片级失效', 'tag-r'),
                 ('分组级失效(G2)', 'tag-r'), ('分组级失效(G3)', 'tag-r'),
                 ('边缘失败', 'tag-a'), ('无数据', None)]
    cat_parts = []
    for cn, cls in cat_order:
        if cn in cats:
            t = '<b class="%s">%d</b>' % (cls, cats[cn]) if cls else '<b>%d</b>' % cats[cn]
            cat_parts.append('%s=%s' % (cn, t))
    if cat_parts:
        detail_items.append('失效类别分布：' + '、'.join(cat_parts))
    detail_items.append('测试温度：<b>%s</b>' % temp_text)
    detail_items.append('标称条件下 Fail 记录共 <b>%d</b> 处（向量×芯片）' % len(scattered))
    if n_sys > 0:
        sv_preview = '、'.join(ys['sys_vectors'][:5])
        more = ' 等' if n_sys > 5 else ''
        detail_items.append('系统性失败向量 <b>%d</b> 个（在 ≥30%% 芯片上 Fail，已从良率中剔除）：%s%s' % (
            n_sys, sv_preview, more))
    else:
        detail_items.append('未发现系统性失败向量')
    # 扫频扫压重点异常: 用物理意义更强的判据替代单纯失败率阈值
    #   ① 低频异常: 15MHz 失败率>50%(低频应更易通过, 基线失败率≤11%; 10MHz 全Fail为已知最小工作频率约束, 正常)
    #   ② Fmax@750mV 最低的向量(窗口上沿掉档)
    #   ③ 单格失败率>80% 的格子(最差点位)
    if heatmap_mode == 'sweep':
        vec_freq_fail = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        vec_fmax = defaultdict(list)
        for c, rows in chips.items():
            per = defaultdict(dict)
            for r in rows:
                per[(r['vector'], r.get('temp'))][(r['clock'], r['voltage'])] = core.is_chip_fail(r)
            for (vec, _t), pts in per.items():
                freqs = sorted({f for f, _ in pts})
                for f in freqs:
                    tot = sum(1 for ff, _ in pts if ff == f)
                    fail = sum(1 for (ff, _v), fl in pts.items() if ff == f and fl)
                    vec_freq_fail[vec][f][0] += fail
                    vec_freq_fail[vec][f][1] += tot
                f750 = [f for f in freqs if not pts.get((f, 750.0), True)]
                if f750:
                    vec_fmax[vec].append(max(f750))
        # ① 低频异常向量
        low_freq_bad = sorted(
            v for v in vec_freq_fail
            if vec_freq_fail[v].get(15.0, [0, 0])[1]
            and vec_freq_fail[v][15.0][0] / vec_freq_fail[v][15.0][1] > 0.5)
        if low_freq_bad:
            names = '、'.join(_short_vec(v) for v in low_freq_bad)
            detail_items.append(
                '低频异常向量(15MHz失败率&gt;50%%, 违反"低频更易通过"物理预期; '
                '基线失败率≤11%%): <b class="tag-a">%s</b>——建议反馈设计/向量团队核查'
                % names)
        # ② Fmax@750 最低的向量(窗口上沿)
        if vec_fmax:
            fmax_min = {v: min(fs) for v, fs in vec_fmax.items() if fs}
            worst = sorted(fmax_min.items(), key=lambda x: x[1])[:3]
            wtxt = '、'.join('%s(%gMHz)' % (_short_vec(v), f)
                             for v, f in worst)
            detail_items.append(
                'Fmax@750mV 最低向量(扫频窗口上沿, 全Pass最高频率): %s；'
                '批次内其余向量普遍更高则为相对掉档' % wtxt)
    if heatmap_mode == 'sweep' and full_matrices:
        sweep_bad = []
        for fm in full_matrices:
            for i, vn in enumerate(fm['vecs']):
                for j, cn in enumerate(fm['chips']):
                    r = fm['ratio'][i][j]
                    if r is not None and r <= 0.2:
                        sweep_bad.append((fm['label'], vn, cn, r))
        if sweep_bad:
            sweep_bad.sort(key=lambda x: x[3])
            parts = ['%s %s×%s(失败率%.0f%%)' % (lb, vn, cn, (1 - r) * 100)
                     for lb, vn, cn, r in sweep_bad[:6]]
            more = ' 等' if len(sweep_bad) > 6 else ''
            detail_items.append(
                '扫频扫压重点异常(单格失败率&gt;80%%, 不计入良率)共 '
                '<b class="tag-a">%d</b> 格：%s%s；同类向量跨多颗芯片一致出现时, '
                '偏向向量级窗口/设计问题而非单颗芯片缺陷'
                % (len(sweep_bad), '、'.join(parts), more))
    # 最差几颗芯片(用调整后 fail 数, 剔除系统性向量)
    fail_chips = [(c, adj_fails.get(c, 0)) for c in chip_names
                  if adj_fails.get(c, 0) > 0]
    fail_chips.sort(key=lambda x: -x[1])
    if fail_chips:
        top3 = '、'.join('<b class="tag-r">%s</b>(%d)' % (n, f) for n, f in fail_chips[:3])
        detail_items.append('Fail 向量数最多的芯片：%s' % top3)
    # 健康芯片(调整后无 fail)
    healthy = [c for c in chip_names if adj_fails.get(c, 0) == 0]
    detail_items.append('全向量 Pass 的健康芯片 <b class="tag-g">%d</b> 颗' % len(healthy))

    summary_html = '''
  <div class="panel full summary">
    <h2>数据总结</h2>
    <div class="hint">以下为基于标称条件测试数据的文字化总结，与上方图表信息一致</div>
    <div class="summary-block">
      <h3>概要</h3>
      <p>%s</p>
    </div>
    <div class="summary-block">
      <h3>细则</h3>
      <ul>
%s
      </ul>
    </div>
  </div>''' % (overview, '\n'.join('        <li>%s</li>' % it for it in detail_items))

    body += summary_html

    # ---- footer ----
    footer_html = ('数据来源：LB3 error_count 原始数据 · 页面自动生成于 %s<br>'
                   '判定条件：%s · 调整良率 %.1f%% (%d/%d) · %s' % (
        time.strftime('%Y-%m-%d %H:%M:%S'), cond, yield_pct,
        ys['npass'], ys['total'], note))

    # ---- 嵌入数据与脚本 ----
    data_js = ('var CHIPS=%s;\nvar VECTORS=%s;\n'
               'var CHIPFAILS=%s;\nvar CATS=%s;\nvar VFAILS=%s;\n'
               'var SCATTERED=%s;\nvar WORST="%s";\n'
               'var FULL=%s;\n') % (
        json.dumps(chip_names, ensure_ascii=False),
        json.dumps(vectors, ensure_ascii=False),
        json.dumps(chip_fails),
        json.dumps(ys['categories'], ensure_ascii=False),
        json.dumps(vfails, ensure_ascii=False),
        json.dumps(scattered, ensure_ascii=False),
        worst_chip,
        json.dumps(full_matrices, ensure_ascii=False))

    script = data_js + r'''
// ---- 柱状图: 各芯片 fail 向量数 ----
(function(){
  var el = document.getElementById('bar');
  var c = echarts.init(el);
  var worst = WORST;
  c.setOption({
    grid:{left:44,right:20,top:30,bottom:60},
    tooltip:{trigger:'axis',axisPointer:{type:'shadow'},
      formatter:function(p){return p[0].name+'<br>Fail 向量数：<b style="color:#f4515c">'+p[0].value+'</b> 条'}},
    xAxis:{type:'category',data:CHIPS,name:'芯片',nameLocation:'middle',nameGap:40,
      nameTextStyle:{color:'#8fa3c8'},
      axisLabel:{color:'#8fa3c8',fontSize:11,interval:0,rotate:30},
      axisLine:{lineStyle:{color:'#1e2c4a'}}},
    yAxis:{type:'value',name:'fail 向量数',nameTextStyle:{color:'#8fa3c8'},
      splitLine:{lineStyle:{color:'#1e2c4a'}},axisLabel:{color:'#8fa3c8'}},
    series:[{type:'bar',data:CHIPS.map(function(n,i){return{
      value:CHIPFAILS[i],
      itemStyle:{color:n===worst?'#f4515c':(CHIPFAILS[i]>0?'#f5a623':'#2a3d63'),
                 borderRadius:[3,3,0,0]}}}),barWidth:'62%',
      label:{show:true,position:'top',color:'#c8d6f0',fontSize:10,
        formatter:function(p){return p.value>0?p.value:''}}}]
  });
  window.addEventListener('resize',function(){c.resize()});
})();

// ---- 环形图: 芯片级结果构成 ----
(function(){
  var el = document.getElementById('donut');
  var c = echarts.init(el);
  var colorMap={'Pass':'#22c07a','芯片级失效':'#f4515c','分组级失效(G2)':'#f4515c',
                '分组级失效(G3)':'#f4515c','边缘失败':'#f5a623','无数据':'#5b6c8f'};
  var data=Object.keys(CATS).map(function(k){return{name:k,value:CATS[k],
    itemStyle:{color:colorMap[k]||'#3a4a6b'}}});
  var npass=CATS['Pass']||0;
  c.setOption({
    tooltip:{trigger:'item',formatter:function(p){return p.name+'：<b>'+p.value+'</b> 颗芯片（'+p.percent+'%）'}},
    title:[
      {text:npass+' / '+CHIPS.length+'\n全向量通过',left:'50%',top:'42%',textAlign:'center',
        textStyle:{color:'#22c07a',fontSize:18,fontWeight:700,lineHeight:26}},
      {text:'芯片级良率 '+(100*npass/CHIPS.length).toFixed(1)+'%',left:'50%',top:'64%',textAlign:'center',
        textStyle:{color:'#8fa3c8',fontSize:12,fontWeight:400}}
    ],
    legend:{bottom:0,textStyle:{color:'#8fa3c8',fontSize:12}},
    series:[{name:'芯片级判定',type:'pie',radius:['48%','70%'],center:['50%','52%'],
      label:{color:'#e8eefb',fontSize:12,formatter:'{b} {c} 颗'},
      labelLine:{lineStyle:{color:'#5b6c8f'}},data:data}]
  });
  window.addEventListener('resize',function(){c.resize()});
})();

// ---- 热力图: 向量×芯片矩阵(按温度分图), 悬停展开格内频压明细 ----
// mode=nominal: 每格2~3个频压点(标称); mode=sweep: 每格80个频压点(扫频扫压)
// 明细只在悬停该格子时渲染成 频率×电压 小格矩阵, 平时不显示
FULL.forEach(function(fm, idx){
  var el = document.getElementById('heatmap_f_'+idx);
  if(!el) return;
  var c = echarts.init(el);
  var chips = fm.chips, vecs = fm.vecs, freqs = fm.freqs, volts = fm.volts;
  var mode = fm.mode, nff = freqs.length, nfv = volts.length;
  var hm = [];
  // sweep 着色=窗口法: 琥珀=窗口异常格(15MHz低频失效 或 Fmax@750掉档), 红=全Fail,
  // 绿=正常窗口(含部分Fail角点), 空白=无数据; 与数据总结的三判据一致
  for(var i=0;i<vecs.length;i++)
    for(var j=0;j<chips.length;j++){
      if(mode==='sweep'){
        var r = fm.ratio[i][j];
        if(r===null || r===undefined){
          hm.push({value:[j,i,0], ratio:null, itemStyle:{color:'rgba(0,0,0,0)'}});
        }else{
          var col = fm.anom[i][j] ? '#f5a623' : (r<=0 ? '#e5484d' : '#1d8f5f');
          hm.push({value:[j,i,r], ratio:r, itemStyle:{color:col}});
        }
      }else{
        hm.push([j,i,fm.status[i][j]]);
      }
    }
  var stColor = ['#1d8f5f','#e5484d','#3a4a6b','#f5a623'];
  var stText = ['PASS','FAIL','无数据','设备侧异常'];
  function cellStateTxt(st){
    if(mode !== 'sweep') return stText[st];
    return st===0?'全Pass':st===1?'全Fail':st===3?'部分Fail':'无数据';
  }
  // 悬停明细: 格内频压点 → 频率×电压 小格矩阵(仅悬停时出现在 tooltip 中)
  function tipGrid(gi, ci){
    var pts = fm.pts[gi] ? fm.pts[gi][ci] : null;
    if(!pts) return '';
    var h = '<div style="margin-top:6px">';
    h += '<table style="border-collapse:collapse">';
    h += '<tr><td></td>';
    for(var v=0; v<nfv; v++)
      h += '<td style="color:#8fa3c8;font-size:9px;padding:0 3px;text-align:center">'+volts[v]+'</td>';
    h += '</tr>';
    for(var f=0; f<nff; f++){
      h += '<tr><td style="color:#8fa3c8;font-size:9px;padding-right:4px;text-align:right;white-space:nowrap">'+freqs[f]+'M</td>';
      for(var v=0; v<nfv; v++){
        var st = pts[f*nfv+v];
        h += '<td style="width:13px;height:13px;background:'+stColor[st]+';border:1px solid #0b1220"></td>';
      }
      h += '</tr>';
    }
    h += '</table>';
    var npass=0, ntot=0;
    for(var k=0; k<pts.length; k++){ if(pts[k]!==2){ ntot++; if(pts[k]===0) npass++; } }
    h += '<div style="margin-top:4px;color:#8fa3c8;font-size:10px">格内频压点: <b style="color:#e8eefb">'+
         npass+'/'+ntot+'</b> Pass <span style="color:#5b6c8f">(列=电压mV, 行=频率MHz, 悬停本格才显示)</span></div></div>';
    return h;
  }
  c.setOption({
    grid:{left:170, right:30, top:30, bottom:60},
    tooltip:{formatter:function(p){
      var gi = p.value[1], ci = p.value[0];
      var st = fm.status[gi][ci];
      var anomTag = (fm.anom && fm.anom[gi] && fm.anom[gi][ci])
        ? ' <span style="color:#f5a623">⚠窗口异常</span>' : '';
      return '<b>'+vecs[gi]+'</b><br>'+chips[ci]+'：<span style="color:'+
        (st===0?'#22c07a':st===1?'#f4515c':st===3?'#f5a623':'#8fa3c8')+
        ';font-weight:bold">'+cellStateTxt(st)+'</span>'+anomTag+tipGrid(gi,ci);}},
    xAxis:{type:'category', data:chips, position:'top',
      axisLabel:{color:'#8fa3c8', fontSize:11, interval:0},
      axisLine:{show:false}, axisTick:{show:false}},
    yAxis:{type:'category', data:vecs, inverse:true,
      axisLabel:{color:'#8fa3c8', fontSize:10.5, width:160, overflow:'truncate'},
      axisLine:{show:false}, axisTick:{show:false}},
    dataZoom:[{type:'slider', yAxisIndex:0, right:6, width:14, borderColor:'#1e2c4a',
        backgroundColor:'#0f1830', fillerColor:'rgba(61,139,255,.2)',
        handleStyle:{color:'#3d8bff'},
        start:0, end:Math.min(100, 100*40/Math.max(vecs.length,1))},
      {type:'inside', yAxisIndex:0}],
    visualMap: mode==='sweep'
      ? {show:false}   // sweep 逐格指定颜色(全Pass绿/部分Fail琥珀→绿渐变/全Fail红/无数据透明)
      : {show:false, dimension:2, min:0, max:2, inRange:{color:['#1d8f5f','#e5484d','#3a4a6b']}},
    series:[{type:'heatmap', data:hm,
      itemStyle:{borderColor:'#0b1220', borderWidth:1},
      emphasis:{itemStyle:{shadowBlur:8, shadowColor:'rgba(0,0,0,.6)'}}}]
  });
  window.addEventListener('resize',function(){c.resize()});
});

// ---- 失败向量 TOP 柱状图 ----
(function(){
  var el = document.getElementById('vfails');
  var c = echarts.init(el);
  var names = VFAILS.map(function(v){return v.name;}).reverse();
  var vals = VFAILS.map(function(v){return v.fails;}).reverse();
  c.setOption({
    tooltip:{formatter:function(p){return p.name+'<br>失败芯片数：<b style="color:#f4515c">'+p.value+'</b>'}},
    grid:{left:420,right:60,top:20,bottom:40},
    xAxis:{type:'value',name:'失败芯片数',nameTextStyle:{color:'#8fa3c8'},
           axisLabel:{color:'#8fa3c8'}, splitLine:{lineStyle:{color:'#1e2c4a'}}},
    yAxis:{type:'category', data:names,
           axisLabel:{fontSize:11, width:410, overflow:'truncate', color:'#8fa3c8'}},
    series:[{type:'bar', data:vals, itemStyle:{color:'#f4515c',borderRadius:[0,3,3,0]},
      label:{show:true, position:'right', color:'#e8eefb'}}]
  });
  window.addEventListener('resize',function(){c.resize()});
})();

// ---- Fail 明细表 ----
(function(){
  var tb = document.querySelector('#failTbl tbody');
  var rows = SCATTERED.map(function(r,i){
    var temp = (r[4]===null||r[4]===undefined)?'常温':(r[4]+'°C');
    return '<tr><td>'+(i+1)+'</td><td class="vec">'+r[0]+'</td><td class="fail">'+r[1]+' ✗</td>'+
      '<td class="r">'+temp+'</td><td class="r">'+r[2]+' MHz</td><td class="r">'+r[3]+' mV</td></tr>';
  });
  tb.innerHTML = rows.join('') || '<tr><td colspan="6" style="text-align:center;color:#5b6c8f">无 Fail 记录</td></tr>';
})();
'''

    mode = echarts_mode
    html = _html_page(title, echarts_js, mode, meta_html, body, footer_html, script)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return {'chips': n_chips, 'points': total_pts,
            'yield': yield_pct, 'echarts': mode,
            'html_size': os.path.getsize(out_path)}


# ============================================================
#  命令行入口(与 lb3tools_cli.py 的 report 子命令共用同一实现)
# ============================================================
def run_report_cli(args):
    """report 命令的共享执行逻辑。
    lb3tools_html.py 直接运行 与 lb3tools_cli.py report 子命令
    都调用本函数, 保证两个入口行为完全一致。
    args 需要的属性: input / out / nominal_v / nominal_f / vector / open"""
    chips = core.load_inputs(args.input)

    out = args.out
    name = os.path.splitext(os.path.basename(args.input.rstrip('/')))[0]
    if not out:
        out = '测试报告_%s_%s.html' % (name, time.strftime('%Y%m%d_%H%M%S'))

    if args.nominal_v == 'auto':
        nv = 'auto'
    else:
        nv = float(args.nominal_v)
    if args.nominal_f == 'auto':
        fs = 'auto'
    else:
        fs = [float(x) for x in args.nominal_f.split(',') if x.strip()] or None

    print('已加载 %d 颗芯片, 共 %d 个测试点' % (
        len(chips), sum(len(v) for v in chips.values())))
    print('判定条件: 电压=%s, 频率=%s' % (args.nominal_v, args.nominal_f))
    title = 'LB3 测试数据报告 - %s' % name
    ret = write_html_report(chips, out, title=title, nominal_v=nv, nominal_fs=fs,
                            vector_sub=args.vector,
                            heatmap_mode=getattr(args, 'heatmap_mode', 'auto'))
    print('完成 → %s' % out)
    print('网页报告: %d 颗芯片 / %d 测试点 / 调整良率 %.1f%% / ECharts来源=%s / 文件大小 %.1f MB' % (
        ret['chips'], ret['points'], ret['yield'], ret['echarts'],
        ret['html_size'] / 1024 / 1024))
    if ret['echarts'] == 'cdn':
        print('(注意: ECharts 走 CDN, 查看时需联网)')
    else:
        print('浏览器打开即可查看(单文件, 离线可用)')

    if getattr(args, 'open', False):
        import webbrowser
        abs_path = os.path.abspath(out)
        ok = webbrowser.open('file://' + abs_path)
        print(('已在浏览器打开: ' if ok else '自动打开失败, 请手动用浏览器打开: ') + abs_path)
    return ret


def main(argv=None):
    """lb3tools_html.py 直接运行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        prog='lb3tools_html',
        description='生成 LB3 测试数据单文件 HTML 看板报告')
    parser.add_argument('-i', '--input', required=True,
                        help='批次目录(含 *error_count*.csv) 或单个 chart.xlsx')
    parser.add_argument('-o', '--out', help='输出 .html 路径(默认自动命名)')
    parser.add_argument('--nominal-v', default='auto',
                        help='标称电压(V), auto=自动选择最密集电压(默认 auto)')
    parser.add_argument('--nominal-f', default='auto',
                        help='标称频率(MHz), 逗号分隔, auto=自动选择(默认 auto)')
    parser.add_argument('--vector', default=None,
                        help='向量名子串过滤(如 G2 / EMC0000), 默认聚合全部')
    parser.add_argument('--heatmap-mode', default='auto',
                        choices=['auto', 'nominal', 'sweep'],
                        help='热力图模式: auto=由csv频压组合数自动判定(默认), '
                             'nominal=强制标称热力图, sweep=强制扫频扫压热力图')
    parser.add_argument('--open', action='store_true',
                        help='生成后自动用默认浏览器打开报告')
    args = parser.parse_args(argv)
    run_report_cli(args)


if __name__ == '__main__':
    main()
