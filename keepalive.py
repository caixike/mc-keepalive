#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rustix Minecraft 服务器保活/监控脚本
- 使用 mcstatus 发送官方状态请求（Handshake + Status Request）
- 失败时回退到旧的 TCP 探测
- 由 GitHub Actions 每 10 分钟定时调用一次
"""

import os
import sys
import socket
import datetime


# 配置区（优先读取环境变量，方便 GitHub Secrets 注入）
SERVER_HOST = os.environ.get("SERVER_HOST", "f1.rustix.me")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "37030"))
TIMEOUT = float(os.environ.get("TIMEOUT", "8"))


def log(msg: str) -> None:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def ping_via_mcstatus() -> bool:
    """使用 mcstatus 发送状态请求，返回是否成功"""
    try:
        from mcstatus import JavaServer
        server = JavaServer(SERVER_HOST, SERVER_PORT)
        resp = server.status(timeout=TIMEOUT)
        log(f"[OK] MCStatus 成功 | 在线: {resp.players.online}/{resp.players.max} | 版本: {resp.version.name} | 延迟: {resp.latency:.0f}ms")
        return True
    except ImportError:
        log("[WARN] mcstatus 未安装，跳过")
        return False
    except Exception as e:
        log(f"[FAIL] MCStatus 失败: {e}")
        return False


def ping_via_legacy() -> bool:
    """回退到旧的 TCP 探测（适用于极旧版服务器）"""
    try:
        with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=TIMEOUT) as sock:
            sock.sendall(b"\xfe\x01")
            data = sock.recv(1024)
            if data:
                log(f"[OK] Legacy ping 成功，收到 {len(data)} 字节回复")
                return True
            else:
                log("[FAIL] Legacy ping 未收到回复")
                return False
    except Exception as e:
        log(f"[FAIL] Legacy ping 失败: {e}")
        return False


def ping_via_tcp() -> bool:
    """最基础的 TCP 连接探测，只检查端口是否可达"""
    try:
        with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=TIMEOUT):
            log(f"[OK] TCP 端口可达: {SERVER_HOST}:{SERVER_PORT}")
            return True
    except Exception as e:
        log(f"[FAIL] TCP 连接失败: {e}")
        return False


def main() -> int:
    log(f"=== Rustix 保活检测开始 | 目标: {SERVER_HOST}:{SERVER_PORT} ===")

    # 1. 优先使用 mcstatus（完整握手+状态请求）
    if ping_via_mcstatus():
        log("=== 检测完成：服务器在线 (mcstatus) ===")
        return 0

    # 2. 回退 legacy ping
    if ping_via_legacy():
        log("=== 检测完成：服务器在线 (legacy) ===")
        return 0

    # 3. 最后尝试纯 TCP 连通
    if ping_via_tcp():
        log("=== 检测完成：端口可达（服务器可能正在启动）===")
        return 0

    log("=== 检测完成：服务器离线或无响应 ===")
    log("请登录 Rustix 控制台手动启动：https://game.rustix.me")
    return 1


if __name__ == "__main__":
    sys.exit(main())
