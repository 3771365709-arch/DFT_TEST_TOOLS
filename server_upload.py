#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LB3 测试数据上传 - 服务端
=========================
在公司服务器上运行, 接收客户端通过 HTTP POST 上传的文件, 按相对路径保存.

协议 (无需鉴权, 限内网使用):
  POST /upload
  Header: X-File-Path: <URL编码的相对路径>   (如 source/01批次/FF11/xxx.csv)
  Body:   文件原始二进制
  返回: 200 OK / 4xx 错误

用法:
  python3 server_upload.py                      # 默认 0.0.0.0:8000, 存到 ./uploads
  python3 server_upload.py 9000 /data/lb3       # 指定端口和存储目录
"""

import os
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler


class UploadHandler(BaseHTTPRequestHandler):
    storage_root = './uploads'

    def do_POST(self):
        if self.path != '/upload':
            self._send(404, 'Not Found')
            return
        rel_encoded = self.headers.get('X-File-Path', '').strip()
        if not rel_encoded:
            self._send(400, 'Missing X-File-Path header')
            return
        rel_path = urllib.parse.unquote(rel_encoded)
        # 安全检查: 归一化后必须是相对路径, 防止 ../ 穿越
        rel_path = os.path.normpath(rel_path)
        if rel_path.startswith('..') or os.path.isabs(rel_path):
            self._send(400, 'Invalid path (path traversal not allowed)')
            return

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            self._send(400, 'Empty body')
            return
        data = self.rfile.read(content_length)

        dest = os.path.join(self.storage_root, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(data)

        self._send(200, 'OK %d bytes' % len(data))

    def log_message(self, fmt, *args):
        print('[%s] %s' % (self.log_date_time_string(), fmt % args))

    def _send(self, code, msg):
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(msg.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(msg.encode('utf-8'))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    root = sys.argv[2] if len(sys.argv) > 2 else './uploads'
    UploadHandler.storage_root = os.path.abspath(root)
    os.makedirs(UploadHandler.storage_root, exist_ok=True)
    server = HTTPServer(('0.0.0.0', port), UploadHandler)
    print('=' * 60)
    print('  LB3 上传服务端已启动')
    print('  监听地址 : 0.0.0.0:%d' % port)
    print('  存储目录 : %s' % UploadHandler.storage_root)
    print('  停止服务 : Ctrl+C')
    print('=' * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n正在关闭...')
        server.shutdown()


if __name__ == '__main__':
    main()
