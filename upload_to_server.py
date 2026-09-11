#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LB3 测试数据上传 - 客户端 (一次性脚本)
=======================================
将源数据(csv + chart xlsx) 和 测试结果分析(pivot/良率/汇总/HTML 等)
通过 HTTP 上传到公司服务器.

使用前请修改下方配置:
  SERVER_URL  = 服务器地址 (如 http://192.168.1.100:8000)
  LB3_ROOT    = 本地 LB3_OUTPUT 目录 (默认自动取脚本所在目录的上一级)
  MAX_RETRY   = 单文件失败重试次数

运行:
  python3 upload_to_server.py              # 上传全部 (源数据 + 结果分析)
  python3 upload_to_server.py source       # 只上传源数据
  python3 upload_to_server.py result       # 只上传结果分析
"""

import fnmatch
import hashlib
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ===================== 配置区 (使用前请修改) =====================
SERVER_URL = 'http://192.168.1.100:8000'   # ← 改成你的服务器地址
LB3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_RETRY = 3                               # 失败重试次数
RETRY_SLEEP = 2                             # 重试间隔(秒)
# ================================================================

# 源数据: 只传 error_count.csv 和 chart xlsx (跳过 9 万多 txt 向量文件)
SOURCE_PATTERNS = [
    '*error_count*.csv',
    '*chart*.xlsx',
]

# 结果分析: pivot / 良率统计 / 汇总 / 向量库信息 / HTML 报告
RESULT_PATTERNS = [
    '*pivot*.xlsx',
    '*良率统计*.xlsx',
    '*error_count*汇总*.xlsx',
    '*Shmoo*汇总*.xlsx',
    '*向量库*.xlsx',
    '*.html',
]

# 排除目录 (不上传工具自身目录)
EXCLUDE_DIRS = {'tools_for_LB3', '.git', '__pycache__'}


def find_files(root, patterns):
    """递归扫描匹配的文件, 返回 [绝对路径]"""
    found = []
    for dirpath, dirnames, files in os.walk(root):
        # 排除指定目录
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in files:
            for pat in patterns:
                if fnmatch.fnmatch(fn, pat):
                    found.append(os.path.join(dirpath, fn))
                    break
    return sorted(found)


def file_md5(path, chunk=65536):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def upload_file(local_path, server_rel_path):
    """上传单个文件. server_rel_path: 服务器端相对路径(含子目录)"""
    url = SERVER_URL.rstrip('/') + '/upload'
    # 中文/空格路径需 URL 编码
    encoded_path = urllib.parse.quote(server_rel_path)
    file_size = os.path.getsize(local_path)

    with open(local_path, 'rb') as f:
        data = f.read()

    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('X-File-Path', encoded_path)
    req.add_header('Content-Type', 'application/octet-stream')
    req.add_header('X-File-MD5', file_md5(local_path))
    req.add_header('X-File-Size', str(file_size))

    for attempt in range(1, MAX_RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError,
                ConnectionError, TimeoutError) as e:
            if attempt < MAX_RETRY:
                print('    重试 %d/%d: %s' % (attempt, MAX_RETRY, e))
                time.sleep(RETRY_SLEEP)
            else:
                print('    [失败] %s' % e)
                return False
    return False


def upload_batch(file_list, category, label):
    """批量上传一类文件"""
    total = len(file_list)
    print('\n' + '=' * 60)
    print('  上传 %s (%s)  共 %d 个文件' % (label, category, total))
    print('=' * 60)
    if total == 0:
        print('  (无匹配文件, 跳过)')
        return 0, 0

    success = 0
    failed = []
    t0 = time.time()
    for i, fpath in enumerate(file_list, 1):
        rel = os.path.relpath(fpath, LB3_ROOT)
        # 服务器端路径: source/ 或 result/ + 相对路径
        server_rel = '%s/%s' % (category, rel)
        size_mb = os.path.getsize(fpath) / 1048576.0
        print('[%d/%d] %s (%.2f MB)' % (i, total, rel, size_mb))
        if upload_file(fpath, server_rel):
            success += 1
        else:
            failed.append(rel)
    elapsed = time.time() - t0
    print('\n  ── %s 上传完成 ──' % label)
    print('  成功: %d/%d   耗时: %.1f 秒' % (success, total, elapsed))
    if failed:
        print('  失败文件 (%d 个):' % len(failed))
        for f in failed:
            print('    - %s' % f)
    return success, total


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else 'all'
    if mode not in ('all', 'source', 'result'):
        print('用法: python3 upload_to_server.py [all|source|result]')
        sys.exit(1)

    print('服务器地址: %s' % SERVER_URL)
    print('本地根目录: %s' % LB3_ROOT)
    print('重试次数:   %d' % MAX_RETRY)

    if mode in ('all', 'source'):
        src = find_files(LB3_ROOT, SOURCE_PATTERNS)
        upload_batch(src, 'source', '源数据 (error_count.csv + chart xlsx)')

    if mode in ('all', 'result'):
        res = find_files(LB3_ROOT, RESULT_PATTERNS)
        upload_batch(res, 'result', '测试结果分析 (pivot/良率/汇总/HTML)')

    print('\n全部任务结束.')


if __name__ == '__main__':
    main()
