#!/usr/bin/env python3

# -*- coding: utf-8 -*-
"""
Rustix (FreeMCHost) Minecraft 服务器保活/监控脚本
- 使用 mcstatus 发送官方状态请求（Handshake + Status Request）
- 失败时回退到旧的 TCP 探测
- 检测到服务器离线时自动通过面板 API 启动服务器
- 通过 Telegram Bot 发送通知（在线/离线状态均通知）
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

SERVER_NAME = "Rustix"

# Minecraft 服务器连接信息
SERVER_HOST = os.environ.get("SERVER_HOST", "")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "25565"))
TIMEOUT = float(os.environ.get("TIMEOUT", "8"))

# 面板 API 配置（通过 GitHub Secrets 传入，切勿硬编码）
RUSTIX_API_KEY = os.environ.get("RUSTIX_API_KEY", "")
RUSTIX_SERVER_UUID = os.environ.get("RUSTIX_SERVER_UUID", "")

# Telegram Bot 通知配置（通过 GitHub Secrets 传入，切勿硬编码）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


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
# 服务器控制模块
# ============================================================

def start_server() -> bool:
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
            log(f"[OK] Rustix API 启动命令已发送 (HTTP {resp.status})")
            return True
    except urllib.error.HTTPError as e:
        log(f"[FAIL] Rustix API HTTP 错误: {e.code} {e.reason}")
        return False
    except Exception as e:
        log(f"[FAIL] Rustix API 请求失败: {e}")
        return False


# ============================================================
# 状态检测模块
# ============================================================

def check_mcstatus() -> dict:
    """使用 mcstatus 发送状态请求，返回服务器状态信息"""
    try:
        from mcstatus import JavaServer
        server = JavaServer(SERVER_HOST, SERVER_PORT)
        resp = server.status(timeout=TIMEOUT)
        return {
            "online": True,
            "players": resp.players.online,
            "max_players": resp.players.max,
            "version": resp.version.name,
            "latency": round(resp.latency),
        }
    except ImportError:
        log("[WARN] mcstatus 未安装，跳过")
        return {"online": False}
    except Exception as e:
        log(f"[FAIL] MCStatus 失败: {e}")
        return {"online": False}


def check_legacy() -> bool:
    """回退到旧的 TCP 探测"""
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


def check_tcp() -> bool:
    """最基础的 TCP 连接探测"""
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
    if not SERVER_HOST:
        log("[ERROR] SERVER_HOST 未配置，请在 GitHub Secrets 中设置")
        return 1

    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    log(f"=== [{SERVER_NAME}] 保活检测开始 | 目标: {SERVER_HOST}:{SERVER_PORT} ===")

    # 1. 优先使用 mcstatus（完整握手+状态请求）
    status = check_mcstatus()
    if status["online"]:
        msg = (
            f"✅ [{SERVER_NAME}] 服务器在线\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"玩家: {status['players']}/{status['max_players']}\n"
            f"版本: {status['version']} | 延迟: {status['latency']}ms\n"
            f"时间: {now_str}"
        )
        log(f"=== [{SERVER_NAME}] 检测完成：服务器在线 (mcstatus) ===")
        send_telegram(msg)
        return 0

    # 2. 回退 legacy ping
    if check_legacy():
        send_telegram(
            f"✅ [{SERVER_NAME}] 服务器在线 (legacy)\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"时间: {now_str}"
        )
        return 0

    # 3. 最后尝试纯 TCP 连通
    if check_tcp():
        send_telegram(
            f"⚠️ [{SERVER_NAME}] 端口可达但 MCStatus 无响应（可能正在启动）\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"时间: {now_str}"
        )
        return 0

    # ============================================================
    # 服务器离线 — 自动启动 + 通知
    # ============================================================
    log(f"=== [{SERVER_NAME}] 检测完成：服务器离线或无响应 ===")

    send_telegram(
        f"❌ [{SERVER_NAME}] 服务器离线\n"
        f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
        f"时间: {now_str}\n"
        f"正在尝试通过 API 自动启动…"
    )

    if start_server():
        import time
        time.sleep(60)
        status2 = check_mcstatus()
        if status2["online"]:
            send_telegram(
                f"✅ [{SERVER_NAME}] 服务器已自动恢复\n"
                f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
                f"玩家: {status2['players']}/{status2['max_players']}\n"
                f"版本: {status2['version']} | 延迟: {status2['latency']}ms"
            )
        else:
            send_telegram(
                f"⏳ [{SERVER_NAME}] 启动命令已发送，服务器仍在启动中\n"
                f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
                f"预计 1-3 分钟后恢复"
            )
        log(f"=== [{SERVER_NAME}] 已通过 Rustix API 发送启动命令 ===")
        return 0
    else:
        send_telegram(
            f"🚨 [{SERVER_NAME}] 自动启动失败，请手动处理\n"
            f"主机: {SERVER_HOST}:{SERVER_PORT}\n"
            f"控制台: https://my.rustix.me"
        )
        log(f"=== [{SERVER_NAME}] 自动启动失败，请登录 Rustix 控制台手动启动 ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
