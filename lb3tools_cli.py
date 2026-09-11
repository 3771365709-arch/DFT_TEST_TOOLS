#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LB3 测试数据工具 - CLI 版
==========================
用法:
  python3 lb3tools_cli.py errcount -i <目录或csv>  [-o 输出.xlsx]
  python3 lb3tools_cli.py shmoo    -i <chart.xlsx或目录> [-o 输出.xlsx] [--vector 子串]
  python3 lb3tools_cli.py yield    -i <目录或chart.xlsx> [-o 输出.xlsx]
                                     [--nominal-v 750] [--nominal-f 20,25]
  python3 lb3tools_cli.py vecinfo --lib <向量库目录> [-i 测试数据] [-o 输出.xlsx]
  python3 lb3tools_cli.py report   -i <目录或chart.xlsx> [-o 报告.html]

示例:
  # error_count 汇总(递归扫描目录下所有芯片子文件夹)
  python3 lb3tools_cli.py errcount -i "../已完成/03 LB3 Mbist TTPDK1_40pcs 0608"

  # Shmoo 汇总(chart xlsx, 每颗芯片一个矩阵sheet, 带Vmin/Fmax)
  python3 lb3tools_cli.py shmoo -i "../已完成/04 .../LB3 PDK1 TT 5PCS_Default_chart 0617.xlsx"

  # 良率统计(标称点 750mV×20/25MHz 判定, 失效模式自动分类)
  python3 lb3tools_cli.py yield -i "../已完成/03 LB3 Mbist TTPDK1_40pcs 0608"

  # HTML网页测试报告(单文件看板: 良率/失效分类/Shmoo热力图/失败向量)
  python3 lb3tools_cli.py report -i "../已完成/03 LB3 Mbist TTPDK1_40pcs 0608"
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lb3tools_core import (load_inputs, write_errcount_report,
                           write_shmoo_report, write_yield_report,
                           write_vecinfo_report)
import lb3tools_html


def default_out(prefix, inp):
    name = os.path.splitext(os.path.basename(inp.rstrip('/')))[0]
    stamp = time.strftime('%Y%m%d_%H%M%S')
    return '%s_%s_%s.xlsx' % (prefix, name, stamp)


def cmd_errcount(args):
    chips = load_inputs(args.input)
    out = args.out or default_out('error_count汇总', args.input)
    print('已加载 %d 颗芯片, 共 %d 个测试点' % (
        len(chips), sum(len(v) for v in chips.values())))
    write_errcount_report(chips, out)
    print('完成 → %s' % out)
    # 控制台简报
    nfail_chip = 0
    for chip in sorted(chips):
        fails = [r for r in chips[chip] if r['result'].strip().upper() != 'PASS']
        if fails:
            nfail_chip += 1
            print('  [Fail] %s: %d 点失败, 涉及 %d 个向量' %
                  (chip, len(fails), len({r['vector'] for r in fails})))
    print('简报: %d 颗中 %d 颗存在失败点' % (len(chips), nfail_chip))


def cmd_shmoo(args):
    chips = load_inputs(args.input)
    out = args.out or default_out('Shmoo汇总', args.input)
    print('已加载 %d 颗芯片(sheet)' % len(chips))
    write_shmoo_report(chips, out, vector_sub=args.vector)
    print('完成 → %s' % out)


def cmd_yield(args):
    chips = load_inputs(args.input)
    out = args.out or default_out('良率统计', args.input)
    if args.nominal_v == 'auto':
        nv = 'auto'
    else:
        nv = float(args.nominal_v)
    if args.nominal_f == 'auto':
        fs = 'auto'
    else:
        fs = [float(x) for x in args.nominal_f.split(',') if x.strip()] or None
    print('已加载 %d 颗芯片' % len(chips))
    print('标称判定条件: 电压=%s, 频率=%s' %
          (args.nominal_v, args.nominal_f))
    ret = write_yield_report(chips, out, nominal_v=nv, nominal_fs=fs)
    print('实际判定: %smV × %sMHz' % (ret['nominal_v'],
                                     ret['nominal_fs'] or '全部'))
    print('完成 → %s' % out)
    print()
    print('======== 良率统计结果 ========')
    print('样本总数: %d' % ret['total'])
    print('严格良率(全部标称点通过): %d/%d = %.1f%%' % (
        ret['pass_strict'], ret['total'], ret['yield_strict']))
    print('调整良率(剔除系统性向量): %d/%d = %.1f%%' % (
        ret['pass'], ret['total'], ret['yield']))
    if ret['systematic_vectors']:
        print('系统性失败向量(在≥30%芯片上失败, 向量级问题):')
        for v in ret['systematic_vectors']:
            print('  - %s' % v)
    print('失效类别分布(剔除系统性向量后):')
    for cat in sorted(ret['categories']):
        print('  %-16s %d' % (cat, ret['categories'][cat]))
    if ret.get('equip_abnormal_count'):
        print('设备侧无效数据点(ClockSetFail/ReadError, 不参与判定, 仅供参考): %d 个'
              % ret['equip_abnormal_count'])


def cmd_vecinfo(args):
    chips = None
    if args.input:
        chips = load_inputs(args.input)
        print('已加载测试数据: %d 颗芯片' % len(chips))
    out = args.out or default_out('向量库信息', args.lib)
    print('扫描向量库: %s' % args.lib)
    ret = write_vecinfo_report(args.lib, out, chips=chips)
    print('完成 → %s' % out)
    print()
    print('======== 向量库信息 ========')
    print('文件夹: %d 个, 向量: %d 个, 分组: %d 个' % (
        ret['folders'], ret['vectors'], ret['groups']))
    if chips is not None:
        print('交叉校验(测试数据 vs 向量库):')
        print('  测试数据中出现但库中无源文件: %d 个' % len(ret['tested_missing']))
        for v in ret['tested_missing'][:10]:
            print('    - %s' % v)
        if len(ret['tested_missing']) > 10:
            print('    ... 等共 %d 个(详见报告)' % len(ret['tested_missing']))
        print('  库中有但该批次未测试: %d 个' % len(ret['lib_unused']))
        if 0 < len(ret['lib_unused']) <= 10:
            for v in ret['lib_unused']:
                print('    - %s' % v)


def cmd_report(args):
    """HTML 网页报告: 与 lb3tools_html.py 直接运行共用 run_report_cli,
    保证两个入口(报告内容/控制台输出/自动打开)行为完全一致"""
    lb3tools_html.run_report_cli(args)


def main():
    parser = argparse.ArgumentParser(
        prog='lb3tools_cli',
        description='LB3 测试数据工具(CLI): error_count汇总 / Shmoo汇总 / 良率统计 / 向量库信息 / HTML网页报告',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split('用法:')[1] if '用法:' in __doc__ else None)
    sub = parser.add_subparsers(dest='cmd', required=True)

    p1 = sub.add_parser('errcount', help='error_count 汇总(总览/失败明细/向量统计)')
    p1.add_argument('-i', '--input', required=True, help='批次目录或单个csv')
    p1.add_argument('-o', '--out', help='输出xlsx路径(默认自动命名)')
    p1.set_defaults(func=cmd_errcount)

    p2 = sub.add_parser('shmoo', help='Shmoo矩阵汇总(F×V矩阵+Vmin/Fmax, 带颜色)')
    p2.add_argument('-i', '--input', required=True, help='chart xlsx或芯片目录')
    p2.add_argument('-o', '--out', help='输出xlsx路径(默认自动命名)')
    p2.add_argument('--vector', help='向量名子串过滤(如 G2 / EMC0000), 默认聚合全部')
    p2.set_defaults(func=cmd_shmoo)

    p3 = sub.add_parser('yield', help='良率统计(标称条件判定+失效模式分类)')
    p3.add_argument('-i', '--input', required=True, help='批次目录或chart xlsx')
    p3.add_argument('-o', '--out', help='输出xlsx路径(默认自动命名)')
    p3.add_argument('--nominal-v', default='auto',
                    help='标称电压mV(默认auto: 自动探测批次最常见电压)')
    p3.add_argument('--nominal-f', default='auto',
                    help='标称频率MHz列表(默认auto: 快测批次取全部≤3个频点, '
                         'Shmoo批次不过滤; 也可显式指定如"20,25", 空串=不过滤)')
    p3.set_defaults(func=cmd_yield)

    p4 = sub.add_parser('vecinfo', help='向量库信息(标识字指纹表/库概览/交叉校验)')
    p4.add_argument('--lib', required=True, help='向量库目录(如 /home/yangxinhang/LB3/VECTOR)')
    p4.add_argument('-i', '--input', help='可选: 测试数据(目录/csv/chart), 提供则做交叉校验')
    p4.add_argument('-o', '--out', help='输出xlsx路径(默认自动命名)')
    p4.set_defaults(func=cmd_vecinfo)

    p5 = sub.add_parser('report', help='生成单文件HTML网页测试报告(看板)')
    p5.add_argument('-i', '--input', required=True, help='批次目录/csv/chart xlsx')
    p5.add_argument('-o', '--out', help='输出html路径(默认自动命名)')
    p5.add_argument('--nominal-v', default='auto',
                    help='标称电压mV(默认auto)')
    p5.add_argument('--nominal-f', default='auto',
                    help='标称频率MHz(默认auto, 如"20,25")')
    p5.add_argument('--vector', help='Shmoo向量过滤子串(可选)')
    p5.add_argument('--heatmap-mode', default='auto',
                    choices=['auto', 'nominal', 'sweep'],
                    help='热力图模式: auto=由csv频压组合数自动判定(默认), '
                         'nominal=强制标称, sweep=强制扫频扫压')
    p5.add_argument('--open', action='store_true', help='生成后自动用浏览器打开报告')
    p5.set_defaults(func=cmd_report)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print('错误: %s' % e, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
