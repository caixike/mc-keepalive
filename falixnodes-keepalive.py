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

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json"
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print("✅ Telegram notification sent.")
            else:
                print(f"❌ Telegram error: {resp.status}")
    except Exception as e:
        print(f"❌ Telegram request failed: {e}")

# ─── MC Status Check ─────────────────────────────────────────────

def check_mc_status():
    """Check if MC server is online using mcstatus protocol."""
    try:
        from mcstatus import JavaServer
        server = JavaServer.lookup(f"{MC_HOST}:{MC_PORT}")
        status = server.status()
        return {
            "online": True,
            "players_online": status.players.online,
            "players_max": status.players.max,
            "version": status.version.name,
            "latency": round(status.latency, 1)
        }
    except Exception as e:
        print(f"❌ mcstatus check failed: {e}")
        return {"online": False}

# ─── Auto Restart via Selenium ───────────────────────────────────

def auto_restart():
    """Use Selenium to visit Remote Startup page and click the start button."""
    if not AUTO_RESTART:
        print("⚠️ AUTO_RESTART is disabled, skipping.")
        return False

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        print(f"🌐 Navigating to Remote Startup page: {FALIXNODES_START_URL}")

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        try:
            driver.get(FALIXNODES_START_URL)
            print("📄 Page loaded, looking for start button...")

            # Wait for the start button to appear
            wait = WebDriverWait(driver, 15)
            start_btn = wait.until(EC.element_to_be_clickable((By.XPATH,
                "//button[contains(text(), '启动服务器') or contains(text(), 'Start Server')]"
            )))

            print("🖱️ Found start button, clicking...")
            start_btn.click()

            # Wait a moment for the action to process
            time.sleep(3)

            # Check if we got redirected to queue page
            current_url = driver.current_url
            print(f"📍 Current URL after click: {current_url}")

            if "queue" in current_url.lower() or "server" in current_url.lower():
                print("✅ Server startup request sent successfully!")
                return True
            else:
                print("⚠️ Button clicked but status unclear, checking page content...")
                # Try to find queue indicator
                page_source = driver.page_source
                if "queue" in page_source.lower() or "启动" in page_source.lower():
                    print("✅ Queue page detected, startup request likely successful.")
                    return True
                else:
                    print("⚠️ Could not confirm startup success.")
                    return False

        finally:
            driver.quit()

    except ImportError:
        print("❌ Selenium not installed. Run: pip install selenium")
        return False
    except Exception as e:
        print(f"❌ Auto-restart failed: {e}")
        return False

# ─── Main Logic ──────────────────────────────────────────────────

def main():
    print(f"🚀 {SERVER_NAME} Keepalive Script")
    print(f"📍 Server: {MC_HOST}:{MC_PORT}")
    print(f"🔗 Startup URL: {FALIXNODES_START_URL}")
    print(f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Step 1: Check MC server status
    print("📡 Checking server status...")
    status = check_mc_status()

    if status["online"]:
        # Server is online - keepalive success
        msg = (
            f"🟢 <b>{SERVER_NAME} [{MC_HOST}] 保活成功</b>\n\n"
            f"📅 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📊 状态: ✅ 运行中\n"
            f"👥 玩家: {status['players_online']}/{status['players_max']}\n"
            f"🏷️ 版本: {status['version']}\n"
            f"⚡ 延迟: {status['latency']}ms\n"
            f"🌐 地址: {MC_HOST}:{MC_PORT}\n\n"
            f"✅ 保活操作已完成"
        )
        print(msg)
        send_telegram(msg)
        print("\n✅ Done!")
        sys.exit(0)

    # Step 2: Server is offline - attempt restart
    print("⚠️ Server is OFFLINE. Attempting restart...")
    restart_success = auto_restart()

    if restart_success:
        # Wait for server to start
        print(f"\n⏳ Waiting {STARTUP_WAIT_SECONDS}s for server to boot...")
        time.sleep(STARTUP_WAIT_SECONDS)

        # Verify restart
        print("📡 Verifying server status...")
        verify_status = check_mc_status()

        if verify_status["online"]:
            msg = (
                f"🟢 <b>{SERVER_NAME} [{MC_HOST}] 重启成功</b>\n\n"
                f"📅 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📊 状态: ✅ 已重启并运行中\n"
                f"👥 玩家: {verify_status['players_online']}/{verify_status['players_max']}\n"
                f"🏷️ 版本: {verify_status['version']}\n"
                f"⚡ 延迟: {verify_status['latency']}ms\n"
                f"🌐 地址: {MC_HOST}:{MC_PORT}\n\n"
                f"🔄 服务器已成功重启"
            )
            print(msg)
            send_telegram(msg)
        else:
            msg = (
                f"🟡 <b>{SERVER_NAME} [{MC_HOST}] 重启请求已发送</b>\n\n"
                f"📅 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📊 状态: ⏳ 排队中或启动中\n"
                f"🌐 地址: {MC_HOST}:{MC_PORT}\n"
                f"🔗 启动链接: {FALIXNODES_START_URL}\n\n"
                f"⏳ 启动请求已发送，服务器可能正在排队等待\n"
                f"👉 请稍后手动检查服务器状态"
            )
            print(msg)
            send_telegram(msg)
    else:
        # Auto-restart failed
        msg = (
            f"🔴 <b>{SERVER_NAME} [{MC_HOST}] 服务器离线</b>\n\n"
            f"📅 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📊 状态: ❌ 已停止\n"
            f"🌐 地址: {MC_HOST}:{MC_PORT}\n"
            f"🔄 自动重启: ❌ 失败\n\n"
            f"👉 请手动启动服务器:\n"
            f"🔗 {FALIXNODES_START_URL}"
        )
        print(msg)
        send_telegram(msg)

    print("\n✅ Done!")
    sys.exit(0)

if __name__ == "__main__":
    main()
