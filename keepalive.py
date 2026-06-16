#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FreeMCHost / 一般 Minecraft 服务器保活脚本
- 使用 mcstatus 发送官方状态请求（Handshake + Status Request）
- 失败时回退到旧的 \xFE\x01 TCP 探测
- 每 120 秒（可调）执行一次，写入带时间戳的日志
- 可作 systemd 服务或后台任务长期运行
"""

import time
import socket
import datetime
import sys
from mcstatus import JavaServer, BedrockServer, status_response  # pip install mcstatus

# ----------------- 配置区 -----------------
SERVER_IP = "nd6.hn21.xyz"   # 目标服务器 IP 或域名
SERVER_PORT = 20358          # 目标端口（默认 25565，这里按你的服务器改）
INTERVAL = 120               # 探测间隔（秒），建议 120-180 秒
TIMEOUT = 5.0                # 单次探测超时（秒）
USE_MCSTATUS = True          # 是否优先使用 mcstatus（状态请求）
# ----------------------------------------

def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def ping_via_mcstatus() -> bool:
    """使用 mcstatus 发送状态请求，返回是否成功"""
    try:
        server = JavaServer(SERVER_IP, SERVER_PORT)
        # status() 会执行完整的握手+状态请求，并在成功时返回对象
        resp = server.status(timeout=TIMEOUT)
        log(f"MCStatus 成功 → 在线玩家: {resp.players.online}/{resp.players.max}, "
            f"版本: {resp.version.name}, 延迟: {resp.latency:.0f} ms")
        return True
    except Exception as e:
        log(f"MCStatus 失败: {e}")
        return False

def ping_via_legacy() -> bool:
    """回退到旧的 \xFE\x01 探测（适用于极旧版）"""
    try:
        with socket.create_connection((SERVER_IP, SERVER_PORT), timeout=TIMEOUT) as sock:
            sock.sendall(b"\xFE\x01")
            # 读取响应（最多 1024 字节），只要有返回即视为成功
            data = sock.recv(1024)
            if data:
                log(f"Legacy ping 成功，收到 {len(data)} 字节回复")
                return True
            else:
                log("Legacy ping 未收到回复")
                return False
    except Exception as e:
        log(f"Legacy ping 失败: {e}")
        return False

def main():
    log(f"开始保活：目标 {SERVER_IP}:{SERVER_PORT}，间隔 {INTERVAL}s")
    while True:
        ok = False
        if USE_MCSTATUS:
            ok = ping_via_mcstatus()
        if not ok:
            # 状态请求失败时尝试 legacy 方案，以防某些极旧服务器仍然只认这个
            ok = ping_via_legacy()
        if not ok:
            log("⚠️ 两种方式均失败，将在下次循环重试")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("收到中断信号，脚本结束")
        sys.exit(0)
