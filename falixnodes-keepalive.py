#!/usr/bin/env python3
"""
FalixNodes MC Server Keepalive Script
Uses mcstatus for monitoring + Selenium for auto-restart via Remote Startup link.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse

# ─── Configuration ───────────────────────────────────────────────
SERVER_NAME = "FalixNodes"
MC_HOST = os.environ.get("FALIXNODES_HOST", "zhuoyidai.falixsrv.me")
MC_PORT = int(os.environ.get("FALIXNODES_PORT", "25565"))
STARTUP_WAIT_SECONDS = int(os.environ.get("STARTUP_WAIT_SECONDS", "90"))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

AUTO_RESTART = os.environ.get("AUTO_RESTART", "true").lower() == "true"

FALIXNODES_START_URL = f"https://falixnodes.net/startserver?ip={MC_HOST}"

# ─── Notification ────────────────────────────────────────────────

def send_telegram(message: str):
    """Send a message to Telegram via Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured, skipping notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("ok"):
                print("✅ Telegram notification sent successfully.")
            else:
                print(f"❌ Telegram API error: {result}")
    except Exception as e:
        print(f"❌ Failed to send Telegram notification: {e}")

# ─── Server Status Check ────────────────────────────────────────

def check_server_status() -> dict:
    """Check MC server status using Java protocol via mcstatus."""
    try:
        from mcstatus import JavaServer
        server = JavaServer.lookup(f"{MC_HOST}:{MC_PORT}")
        status = server.status()
        return {
            "online": True,
            "players_online": status.players.online,
            "players_max": status.players.max,
            "version": status.version.name,
            "latency_ms": round(status.latency, 1),
            "description": str(status.description) if status.description else ""
        }
    except Exception as e:
        print(f"❌ Server check failed: {e}")
        return {"online": False, "error": str(e)}

# ─── Auto Restart via Selenium ───────────────────────────────────

def restart_server_selenium() -> bool:
    """Restart server via FalixNodes Remote Startup page using Selenium."""
    print(f"🔄 Attempting restart via Remote Startup: {FALIXNODES_START_URL}")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)

        try:
            # Navigate to Remote Startup page
            driver.get(FALIXNODES_START_URL)
            print("📄 Remote Startup page loaded.")
            time.sleep(3)

            # Find and click the start button
            start_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], button.btn"))
            )
            start_button.click()
            print("✅ Start button clicked.")
            time.sleep(3)

            # Check for success message
            page_text = driver.find_element(By.TAG_NAME, "body").text
            if "started" in page_text.lower() or "success" in page_text.lower() or "queue" in page_text.lower():
                print("✅ Restart command sent successfully.")
                return True
            else:
                print(f"⚠️ Page content after click: {page_text[:200]}")
                return True  # Assume success if no explicit error

        finally:
            driver.quit()

    except ImportError as e:
        print(f"❌ Selenium/Chrome not available: {e}")
        return False
    except Exception as e:
        print(f"❌ Restart failed: {e}")
        return False

# ─── Main Logic ──────────────────────────────────────────────────

def main():
    print(f"🚀 [{SERVER_NAME}] Keepalive script started")
    print(f"   MC Server: {MC_HOST}:{MC_PORT}")
    print(f"   Auto Restart: {AUTO_RESTART}")
    print(f"   Startup URL: {FALIXNODES_START_URL}")
    print()

    # Step 1: Check server status
    status = check_server_status()

    if status.get("online"):
        # Server is online - send success notification
        msg = (
            f"🟢 <b>[{SERVER_NAME}] 服务器在线</b>\n"
            f"📡 地址: <code>{MC_HOST}:{MC_PORT}</code>\n"
            f"👥 玩家: {status['players_online']}/{status['players_max']}\n"
            f"📦 版本: {status['version']}\n"
            f"📶 延迟: {status['latency_ms']}ms"
        )
        print(f"✅ Server is ONLINE | Players: {status['players_online']}/{status['players_max']} | Latency: {status['latency_ms']}ms")
        send_telegram(msg)
        sys.exit(0)
    else:
        # Server is offline
        error_msg = status.get("error", "Unknown error")
        print(f"❌ Server is OFFLINE | Error: {error_msg}")

        if not AUTO_RESTART:
            msg = (
                f"🔴 <b>[{SERVER_NAME}] 服务器离线</b>\n"
                f"📡 地址: <code>{MC_HOST}:{MC_PORT}</code>\n"
                f"❌ 错误: {error_msg}\n"
                f"⚠️ 自动重启已关闭，请手动启动。"
            )
            send_telegram(msg)
            sys.exit(1)

        # Step 2: Attempt restart
        msg_restarting = (
            f"🟡 <b>[{SERVER_NAME}] 服务器离线，正在尝试重启...</b>\n"
            f"📡 地址: <code>{MC_HOST}:{MC_PORT}</code>\n"
            f"⏳ 等待 {STARTUP_WAIT_SECONDS} 秒后确认状态..."
        )
        send_telegram(msg_restarting)

        restart_success = restart_server_selenium()

        if not restart_success:
            msg_fail = (
                f"🔴 <b>[{SERVER_NAME}] 重启失败</b>\n"
                f"📡 地址: <code>{MC_HOST}:{MC_PORT}</code>\n"
                f"❌ 无法通过 Remote Startup 启动服务器。\n"
                f"⚠️ 请手动启动服务器。"
            )
            send_telegram(msg_fail)
            sys.exit(1)

        # Step 3: Wait and verify
        print(f"⏳ Waiting {STARTUP_WAIT_SECONDS} seconds for server to start...")
        time.sleep(STARTUP_WAIT_SECONDS)

        final_status = check_server_status()

        if final_status.get("online"):
            msg_success = (
                f"🟢 <b>[{SERVER_NAME}] 重启成功！</b>\n"
                f"📡 地址: <code>{MC_HOST}:{MC_PORT}</code>\n"
                f"👥 玩家: {final_status['players_online']}/{final_status['players_max']}\n"
                f"📦 版本: {final_status['version']}\n"
                f"📶 延迟: {final_status['latency_ms']}ms"
            )
            print(f"✅ Server is back ONLINE after restart!")
            send_telegram(msg_success)
            sys.exit(0)
        else:
            msg_still_down = (
                f"🔴 <b>[{SERVER_NAME}] 重启后仍然离线</b>\n"
                f"📡 地址: <code>{MC_HOST}:{MC_PORT}</code>\n"
                f"❌ 错误: {final_status.get('error', 'Unknown')}\n"
                f"⚠️ 服务器可能正在队列中排队，请稍后检查。"
            )
            print(f"❌ Server still OFFLINE after restart attempt.")
            send_telegram(msg_still_down)
            sys.exit(1)

if __name__ == "__main__":
    main()
