#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wispbyte (yidai) Minecraft 服务器保活/监控脚本
- 使用 mcstatus 发送官方状态请求（Handshake + Status Request）
- 失败时回退到旧的 TCP 探测
- 通过 Telegram Bot 发送通知（在线/离线状态均通知）
- Wispbyte 不暴露公共 API，离线时仅通知用户手动启动
- 由 GitHub Actions 每 10 分钟定时调用一次
"""

import os
import sys
import socket
import datetime
import json
import urllib.request
import urllib.error


# ============================================================
# 配置区（优先读取环境变量，方便从 GitHub Secrets 注入）
# ============================================================

# Minecraft 服务器连接信息
SERVER_HOST = os.environ.get("WISPBYTE_HOST", "")
SERVER_PORT = int(os.environ.get("WISPBYTE_PORT", "25565"))
TIMEOUT = float(os.environ.get("TIMEOUT", "8"))

# Telegram Bot 通知配置（通过 GitHub Secrets 传入，切勿硬编码）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 服务器标识（用于日志和通知消息前缀）
SERVER_NAME = "Wispbyte"


# ============================================================
# 通知模块
# ============================================================

def log(msg: str) -> None:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def send_telegram(text: str) -> bool:
    """通过 Telegram Bot 发送通知消息（POST + JSON，支持长消息和特殊字符）"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("[SKIP] Telegram 未配置（TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 为空）")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log("[OK] Telegram 通知已发送")
            return True
    except Exception as e:
        log(f"[FAIL] Telegram 发送失败: {e}")
        return False


# ============================================================
# 状态检测模块
# ============================================================

def ping_via_mcstatus() -> dict | None:
    """使用 mcstatus 发送状态请求，返回状态信息或 None"""
    try:
        from mcstatus import JavaServer
        server = JavaServer(SERVER_HOST, SERVER_PORT)
        resp = server.status(timeout=TIMEOUT)
        log(f"[OK] MCStatus 成功 | 在线: {resp.players.online}/{resp.players.max} | 版本: {resp.version.name} | 延迟: {resp.latency:.0f}ms")
        return {
            "online": resp.players.online,
            "max": resp.players.max,
            "version": resp.version.name,
            "latency": round(resp.latency),
        }
    except ImportError:
        log("[WARN] mcstatus 未安装，跳过")
        return None
    except Exception as e:
        log(f"[FAIL] MCStatus 失败: {e}")
        return None


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
    # 检查必需配置
    if not SERVER_HOST:
        log("[ERROR] WISPBYTE_HOST 未配置，请在 GitHub Secrets 中设置")
        return 1

    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    log(f"=== [{SERVER_NAME}] 保活检测开始 | 目标: {SERVER_HOST}:{SERVER_PORT} ===")

    # 1. 优先使用 mcstatus（完整握手+状态请求）
    status = ping_via_mcstatus()
    if status:
        log(f"=== [{SERVER_NAME}] 检测完成：服务器在线 (mcstatus) ===")
        send_telegram(
            f"✅ [{SERVER_NAME}] 服务器在线\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"玩家: {status['online']}/{status['max']}\n"
            f"版本: {status['version']} | 延迟: {status['latency']}ms\n"
            f"时间: {now_str}"
        )
        return 0

    # 2. 回退 legacy ping
    if ping_via_legacy():
        log(f"=== [{SERVER_NAME}] 检测完成：服务器在线 (legacy) ===")
        send_telegram(
            f"✅ [{SERVER_NAME}] 服务器在线 (legacy)\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"时间: {now_str}"
        )
        return 0

    # 3. 最后尝试纯 TCP 连通
    if ping_via_tcp():
        log(f"=== [{SERVER_NAME}] 检测完成：端口可达（服务器可能正在启动）===")
        send_telegram(
            f"⚠️ [{SERVER_NAME}] 端口可达但 MCStatus 无响应\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"时间: {now_str}"
        )
        return 0

    # ============================================================
    # 服务器离线 — 通知用户（Wispbyte 无公共 API，无法自动启动）
    # ============================================================
    log(f"=== [{SERVER_NAME}] 检测完成：服务器离线或无响应 ===")

    send_telegram(
        f"❌ [{SERVER_NAME}] 服务器离线\n"
        f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
        f"时间: {now_str}\n"
        f"Wispbyte 不支持 API 自动启动，请手动启动：\n"
        f"https://wispbyte.com/server/2f247117"
    )

    log("=== 请登录 Wispbyte 控制台手动启动 ===")
    log("https://wispbyte.com/server/2f247117")
    return 1


if __name__ == "__main__":
    sys.exit(main())
