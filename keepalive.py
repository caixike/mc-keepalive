#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rustix Minecraft 服务器保活/监控脚本
- 使用 mcstatus 发送官方状态请求（Handshake + Status Request）
- 失败时回退到旧的 TCP 探测
- 检测到服务器离线时自动通过 Rustix API 启动服务器
- 通过 Telegram Bot 发送通知
- 由 GitHub Actions 每 10 分钟定时调用一次
"""

import os
import sys
import socket
import datetime
import urllib.request
import urllib.error
import json


# ============================================================
# 配置区（优先读取环境变量，方便从 GitHub Secrets 注入）
# ============================================================

# Minecraft 服务器连接信息
SERVER_HOST = os.environ.get("SERVER_HOST", "f1.rustix.me")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "37030"))
TIMEOUT = float(os.environ.get("TIMEOUT", "8"))

# Rustix 面板 API 配置（通过 GitHub Secrets 传入，切勿硬编码）
RUSTIX_API_KEY = os.environ.get("RUSTIX_API_KEY", "")
RUSTIX_SERVER_UUID = os.environ.get("RUSTIX_SERVER_UUID", "")

# Telegram Bot 通知配置（通过 GitHub Secrets 传入，切勿硬编码）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# ============================================================
# 工具函数
# ============================================================

def log(msg: str) -> None:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def send_telegram(text: str) -> bool:
    """通过 Telegram Bot 发送通知消息"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("[SKIP] Telegram 未配置（TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 为空）")
        return False
    try:
        import urllib.parse
        url = (
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            f"?chat_id={TELEGRAM_CHAT_ID}"
            f"&text={urllib.parse.quote(text)}"
        )
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode()
            log(f"[OK] Telegram 通知已发送")
            return True
    except Exception as e:
        log(f"[FAIL] Telegram 发送失败: {e}")
        return False


def rustix_start_server() -> bool:
    """通过 Rustix API 启动服务器"""
    if not RUSTIX_API_KEY or not RUSTIX_SERVER_UUID:
        log("[SKIP] Rustix API 未配置（RUSTIX_API_KEY 或 RUSTIX_SERVER_UUID 为空）")
        return False
    try:
        url = f"https://my.rustix.me/api/client/servers/{RUSTIX_SERVER_UUID}/power"
        data = json.dumps({"signal": "start"}).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {RUSTIX_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            log(f"[OK] Rustix API 启动命令已发送 (HTTP {status})")
            return True
    except urllib.error.HTTPError as e:
        log(f"[FAIL] Rustix API HTTP 错误: {e.code} {e.reason}")
        return False
    except Exception as e:
        log(f"[FAIL] Rustix API 请求失败: {e}")
        return False


# ============================================================
# 服务器状态检测
# ============================================================

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


# ============================================================
# 主逻辑
# ============================================================

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

    # ============================================================
    # 服务器离线 — 自动启动 + 通知
    # ============================================================
    log("=== 检测完成：服务器离线或无响应 ===")

    # 发送 Telegram 离线告警
    alert_msg = (
        f"⚠️ Minecraft 服务器离线\n"
        f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
        f"时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"正在尝试通过 Rustix API 自动启动…"
    )
    send_telegram(alert_msg)

    # 通过 Rustix API 自动启动服务器
    if rustix_start_server():
        success_msg = (
            f"✅ 服务器启动命令已发送\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"预计 1-3 分钟后恢复"
        )
        send_telegram(success_msg)
        log("=== 已通过 Rustix API 发送启动命令 ===")
        return 0  # 发送成功不算脚本错误
    else:
        fail_msg = (
            f"❌ 自动启动失败，请手动处理\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"控制台: https://my.rustix.me"
        )
        send_telegram(fail_msg)
        log("=== 自动启动失败，请登录 Rustix 控制台手动启动 ===")
        log("https://my.rustix.me")
        return 1


if __name__ == "__main__":
    sys.exit(main())
