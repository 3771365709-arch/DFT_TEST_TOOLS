# -*- coding: utf-8 -*-
"""项目适配配置 —— 移植到其他项目时，只需要修改本文件。
=================================================================

lb3tools_core.py 启动时会自动加载本文件的 PROJECT 字典（缺省键回落到
内置默认值），分析/渲染逻辑零改动。当前内容 = LB3 项目的配置。

移植到其他项目的一般步骤（详见 README「移植到其他项目」一节）：
  1. 复制整个 tools_for_LB3 目录到新项目；
  2. 看一眼目标项目 csv 的表头，改下面 'columns' 的别名列表
     （必需字段: vector / clock / voltage / result；可选: read_vddl / error_count）；
  3. 若单位不是 MHz/mV，改 'clock_scale' / 'voltage_scale'（乘法系数）；
  4. 按目标项目的测试结果取值改三个词表（pass / 芯片fail / 设备侧异常）；
  5. 按目标项目的芯片文件夹命名规则改两个正则（芯片名 / 温度后缀）；
  6. 按目标项目标称工作点改 'nominal_v_priority' / 'nominal_freqs'；
  7. （可选）改 'vector_categories'——网页"向量分类总结"卡片的分类规则，
     不改则该模块按 LB3 规则分类，命名不同的向量会全部落入"标称"兜底卡。

全部键均可省略：删掉本文件 = 回到 LB3 默认行为。
"""

PROJECT = {
    # 项目名（仅用于显示）
    'name': 'LB3',

    # ---- CSV 列名映射：标准字段 -> 允许的列名别名（匹配时忽略大小写与空格）----
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

    # ---- 单位换算（乘法系数，统一换算为 MHz / mV）----
    # 例：目标项目电压列单位是 V → 'voltage_scale': 1000.0
    'clock_scale':   1.0,
    'voltage_scale': 1.0,

    # ---- 测试结果词表（大小写不敏感）----
    'pass_values':       ['PASS'],                        # 通过
    'chip_fail_values':  ['FAIL'],                        # 芯片相关失败
    'equip_fail_values': ['CLOCKSETFAIL', 'READERROR'],   # 设备侧无效点（不参与判定）

    # ---- 芯片名 / 温度提取（从文件夹名，正则）----
    'chip_name_pattern':   r'(TT|FS|SF|FF|SS)\d{2}',           # 芯片名: PDK1_TT10_85 → TT10
    'temp_chip_pattern':   r'(?:TT|FS|SF|FF|SS)\d{2}_(-?\d+)',  # 温度后缀: _85/_-25/_0
    'temp_batch_patterns': [r'(-?\d+)c', r'temp(-?\d+)'],       # 批次名兜底: 85c / temp-25

    # ---- 标称条件自动探测 ----
    'nominal_v_priority': [750.0, 700.0, 800.0, 650.0, 850.0, 900.0,
                           600.0, 950.0, 550.0, 500.0],        # 多电压档时的优先级
    'nominal_freqs':      [20.0, 25.0],                          # Shmoo 批次的标称频点

    # ---- 向量分类（网页"向量分类总结"卡片）----
    # 顺序 = 优先级，match 任一正则命中即归入该类别；未命中任何类别 → 兜底 nominal 卡。
    # lib = 库内总数（显示用）；hidden=True 的类别计入"标称独有"，不显示卡片；
    # count_shared_from = 该库含有与另一类别共用的向量，已测数需并入显示。
    'vector_categories': [
        {'key': 'algo',    'display': 'SHM_ALGO 向量',    'lib': 24,  'order': 3,
         'cond': '扫频扫压 10-45MHz × 500-950mV',
         'match': ['SMarch', 'LVWalkingPat']},
        {'key': 'rombase', 'display': None,               'lib': 0,  'hidden': True,
         'match': [r'_ROM_G\d+$']},
        {'key': 'default', 'display': 'SHM_Default 向量', 'lib': 13,  'order': 1,
         'cond': '扫频扫压 10-45MHz × 500-950mV',
         'match': [r'_EMC00000', r'(?:^|_)G\d+$']},
        {'key': 'emc',     'display': 'SHM_EMC 向量',     'lib': 91,  'order': 2,
         'cond': '扫频扫压 10-45MHz × 500-950mV',
         'match': [r'_EMC[01]{4,5}$'], 'count_shared_from': 'default'},
        {'key': 'nominal', 'display': 'Mbist_标称向量',   'lib': 171, 'order': 0,
         'cond': '标称 750mV × 20/25MHz', 'match': []},
    ],
}
