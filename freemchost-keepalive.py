#!/usr/bin/env python3
"""
FreeMCHost (nd6.hn21.xyz:20358) Minecraft 服务器保活脚本
纯监控 + Telegram 通知方案（无面板 API）
"""

import os
import json
import urllib.request
import urllib.parse
import urllib.error
import sys
import time

# === 服务器配置 ===
SERVER_HOST = "nd6.hn21.xyz"
SERVER_PORT = 20358
SERVER_NAME = "FreeMCHost"

# === Telegram 通知模块 ===
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_telegram(message):
    """通过 Telegram 发送通知"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram 未配置，跳过通知")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                print("✅ Telegram 通知发送成功")
            else:
                print(f"⚠️  Telegram 返回异常: {result}")
    except Exception as e:
        print(f"⚠️  Telegram 通知失败: {e}")


# === MC 状态检测模块 ===
def check_server_status():
    """使用 mcstatus 检测 MC 服务器状态"""
    try:
        from mcstatus import JavaServer
        server = JavaServer.lookup(f"{SERVER_HOST}:{SERVER_PORT}")
        status = server.status()
        return {
            "online": True,
            "players_online": status.players.online,
            "players_max": status.players.max,
            "version": status.version.name,
            "latency": round(status.latency, 1),
            "motd": str(status.description) if status.description else ""
        }
    except ImportError:
        print("❌ mcstatus 未安装，请检查 requirements.txt")
        return {"online": False, "error": "mcstatus not installed"}
    except Exception as e:
        print(f"❌ 服务器检测失败: {e}")
        return {"online": False, "error": str(e)}


# === 主逻辑 ===
def main():
    print(f"🔍 检测 {SERVER_NAME} 服务器状态...")
    print(f"   地址: {SERVER_HOST}:{SERVER_PORT}")
    print(f"   时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)

    # 检测服务器状态
    status = check_server_status()

    if status.get("online"):
        # 服务器在线
        print(f"✅ 服务器在线")
        print(f"   玩家: {status['players_online']}/{status['players_max']}")
        print(f"   版本: {status['version']}")
        print(f"   延迟: {status['latency']}ms")

        msg = (
            f"🟢 <b>[{SERVER_NAME}] 服务器在线</b>\n"
            f"📍 地址: <code>{SERVER_HOST}:{SERVER_PORT}</code>\n"
            f"👥 玩家: {status['players_online']}/{status['players_max']}\n"
            f"📦 版本: {status['version']}\n"
            f"⏱ 延迟: {status['latency']}ms"
        )
        send_telegram(msg)
    else:
        # 服务器离线
        error = status.get("error", "未知错误")
        print(f"❌ 服务器离线!")
        print(f"   错误: {error}")

        msg = (
            f"🔴 <b>[{SERVER_NAME}] 服务器离线!</b>\n"
            f"📍 地址: <code>{SERVER_HOST}:{SERVER_PORT}</code>\n"
            f"❌ 错误: {error}\n"
            f"⏰ 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"⚠️ 请手动前往面板启动服务器:\n"
            f"https://freemchost.com"
        )
        send_telegram(msg)
        print("\n⚠️ 无面板 API，无法自动重启，请手动启动服务器")
        print("   面板地址: https://freemchost.com")

    print("-" * 50)
    print("🏁 检测完成")


if __name__ == "__main__":
    main()
