"""
Discord Multi-Channel Trade Scheduler
Async Multi-Tab Architecture with Live TUI Dashboard. Zero Cursor Hijacking.
"""

import argparse
import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import random
import sys
import time
from typing import Any
from playwright.async_api import async_playwright, Page, BrowserContext

if sys.platform == "win32":
    os.system("")  # Enable ANSI terminal output
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PROFILE_DIR = os.path.join(BASE_DIR, "discord_browser_data")

# ANSI Color Palette
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
WHITE, GRAY, CYAN, GREEN, YELLOW, MAGENTA, RED = (
    "\033[97m", "\033[90m", "\033[96m", "\033[92m", "\033[93m", "\033[95m", "\033[91m"
)

STATUS_COLORS = {
    "INIT": GRAY, "READY": GREEN, "SENDING": CYAN + BOLD,
    "COOLDOWN": YELLOW, "SLOWMODE": MAGENTA + BOLD, "ERROR": RED + BOLD,
}
TAG_COLORS = {
    "OK": GREEN, "SEND": CYAN, "WAIT": YELLOW, "SLOW": MAGENTA,
    "ERR": RED, "INFO": WHITE, "SETUP": CYAN, "LOGIN": YELLOW,
}


def color_badge(text: str, color_map: dict[str, str], width: int) -> str:
    """Format badge with fixed visible width regardless of ANSI codes."""
    raw = f"[{text}]"
    color = color_map.get(text, WHITE)
    return f"{color}{raw}{RESET}{' ' * max(0, width - len(raw))}"


def fmt_seconds(s: int) -> str:
    """Format seconds as mm:ss or hh:mm:ss."""
    if s < 0:
        return "00:00"
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


@dataclass
class ChannelState:
    index: int
    name: str
    url: str
    msg_file: str
    status: str = "INIT"
    sent_count: int = 0
    next_run: datetime | None = None
    msg_idx: int = 0


class AppState:
    def __init__(self, mode: str, profile: str = "default"):
        self.mode = mode
        self.profile = profile
        self.start_time = datetime.now()
        self.channels: list[ChannelState] = []
        self.logs: deque[tuple[str, str, str, str]] = deque(maxlen=6)
        self.is_running = True

    def log(self, channel: str, tag: str, msg: str) -> None:
        self.logs.append((datetime.now().strftime("%H:%M:%S"), channel, tag, msg))


def load_config() -> list[dict[str, Any]]:
    """Load channel list from config.json with fallback support."""
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "channels" in data and isinstance(data["channels"], list):
            return data["channels"]
        if "channel_url" in data:
            return [{
                "name": "Default", "channel_url": data["channel_url"],
                "message_file": "msg1.txt", "interval_seconds": data.get("interval_seconds", 5),
                "jitter_seconds": data.get("jitter_seconds", 0)
            }]
    except Exception:
        pass
def get_discord_token() -> str | None:
    """Retrieve Discord User Token from Environment Variables or config.json."""
    token = os.environ.get("USER_TOKEN") or os.environ.get("DISCORD_TOKEN")
    if token and token.strip():
        return token.strip()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "user_token" in data and isinstance(data["user_token"], str) and data["user_token"].strip():
                return data["user_token"].strip()
        except Exception:
            pass
    return None


async def inject_discord_token(page: Page, token: str, app: AppState) -> bool:
    """Inject Discord User Token into Playwright LocalStorage for headless login."""
    clean_token = token.strip().strip('"').strip("'")
    app.log("SYSTEM", "LOGIN", "Injecting Discord User Token into LocalStorage...")
    try:
        await page.goto("https://discord.com/login", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1.5)
        await page.evaluate("""(token) => {
            const iframe = document.createElement('iframe');
            document.body.appendChild(iframe);
            iframe.contentWindow.localStorage.token = `"${token}"`;
        }""", clean_token)
        await asyncio.sleep(1)
        app.log("SYSTEM", "LOGIN", "Token injected successfully.")
        return True
    except Exception as e:
        app.log("SYSTEM", "ERR", f"Token injection error: {e}")
        return False


def get_channel_message(cfg: dict[str, Any], idx: int) -> str:
    """Hot-reload trade message from text file or inline config."""
    msg_file = cfg.get("message_file")
    if msg_file:
        path = os.path.join(BASE_DIR, msg_file) if not os.path.isabs(msg_file) else msg_file
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    parts = [p.strip() for p in f.read().split("\n---\n") if p.strip()]
                    if parts:
                        return random.choice(parts) if cfg.get("mode") == "random" else parts[idx % len(parts)]
            except Exception:
                pass
    messages = cfg.get("messages", [])
    if messages:
        return random.choice(messages) if cfg.get("mode") == "random" else messages[idx % len(messages)]
    return "Pesan promosi belum dikonfigurasi."


async def set_window_bounds(context: BrowserContext, page: Page, x: int, y: int) -> None:
    """Move Chrome window (offscreen or on-screen) via CDP."""
    try:
        session = await context.new_cdp_session(page)
        win = await session.send("Browser.getWindowForTarget")
        await session.send("Browser.setWindowBounds", {
            "windowId": win["windowId"],
            "bounds": {"left": x, "top": y, "width": 1280, "height": 800, "windowState": "normal"}
        })
    except Exception:
        pass


async def wait_for_chat_box(page: Page, ctx: BrowserContext, hidden: bool, state: AppState, ch_name: str = "") -> bool:
    """Wait for Discord textbox. Automatically restores window if login needed and handles focus/diagnostics."""
    start = time.time()
    restored = False
    selectors = [
        'div[role="textbox"]',
        'div[class*="slateTextArea"]',
        'div[class*="textArea_"]',
        'form div[role="textbox"]'
    ]

    try:
        await page.bring_to_front()
    except Exception:
        pass

    while time.time() - start < 60:
        try:
            for sel in selectors:
                if await page.is_visible(sel):
                    if hidden and restored and sys.platform == "win32":
                        await asyncio.sleep(1)
                        await set_window_bounds(ctx, page, -3200, -3200)
                        state.log("SYSTEM", "INFO", "Chat box ready. Window hidden back offscreen.")
                    return True

            # Diagnose reasons if chat box is missing
            diag = await page.evaluate("""() => {
                const text = document.body ? document.body.innerText : '';
                if (/you do not have permission to send messages/i.test(text)) return "NO_PERMISSION";
                if (/must complete a few steps before you can talk/i.test(text)) return "RULES_GATE";
                if (/channel is locked|read-only/i.test(text)) return "LOCKED";
                return null;
            }""")
            if diag == "NO_PERMISSION":
                state.log(ch_name or "CHANNEL", "ERR", "No permission to send in this channel (Read-only).")
                return False
            elif diag == "RULES_GATE":
                state.log(ch_name or "CHANNEL", "WARN", "Membership rules agreement required.")
                complete_btn = page.locator('button:has-text("Complete")').first
                if await complete_btn.is_visible():
                    await complete_btn.click()

            curr_url = page.url
            if "login" in curr_url and time.time() - start > 15:
                state.log(ch_name or "CHANNEL", "LOGIN", "Redirected to login. Session not authenticated.")
                return False

        except Exception:
            pass

        # Periodically re-focus page so Chrome doesn't throttle background rendering
        elapsed = int(time.time() - start)
        if elapsed > 0 and elapsed % 12 == 0:
            try:
                await page.bring_to_front()
            except Exception:
                pass

        if hidden and not restored and sys.platform == "win32" and (time.time() - start > 8 or "login" in page.url):
            await set_window_bounds(ctx, page, 100, 100)
            restored = True
            state.log("SYSTEM", "LOGIN", "Login needed. Browser window shown on screen.")

        await asyncio.sleep(2)

    return False


async def get_slowmode_seconds(page: Page) -> int:
    """Accurately extract slowmode remaining seconds from Discord chat form."""
    try:
        val = await page.evaluate("""() => {
            const form = document.querySelector('form');
            if (!form) return 0;
            const isSlowCtx = /slowmode|cooldown/i.test(form.innerText);
            for (const el of form.querySelectorAll('*')) {
                const txt = (el.innerText || '').trim();
                if (!txt || el.children.length > 1) continue;
                if (!(el.querySelector('svg') || el.parentElement?.querySelector('svg'))) continue;
                const hms = txt.match(/^(\\d{1,2}):(\\d{2}):(\\d{2})$/);
                if (hms) return (+hms[1]) * 3600 + (+hms[2]) * 60 + (+hms[3]);
                const ms = txt.match(/^(\\d{1,2}):(\\d{2})$/);
                if (ms && (isSlowCtx || /cooldown|slowmode/i.test(el.className + ' ' + el.parentElement?.className))) {
                    return (+ms[1]) * 60 + (+ms[2]);
                }
            }
            return 0;
        }""")
        return int(val or 0)
    except Exception:
        return 0


async def send_discord_message(page: Page, text: str) -> bool:
    """Type and dispatch message to Discord textbox without moving cursor."""
    await page.bring_to_front()
    box = None
    for sel in ['div[role="textbox"]', 'div[class*="slateTextArea"]', 'div[class*="textArea_"]', '[role="textbox"]']:
        loc = page.locator(sel).first
        if await loc.is_visible():
            box = loc
            break
    if not box:
        box = page.locator('div[role="textbox"]').first

    await box.wait_for(state="visible", timeout=15000)
    await box.click()
    await box.fill(text)
    await asyncio.sleep(0.3)
    await box.press("Enter")
    await asyncio.sleep(0.6)
    if (await box.inner_text()).strip():
        await box.press("Enter")
        await asyncio.sleep(0.2)
    return True


async def channel_worker(
    ch: ChannelState,
    initial_cfg: dict[str, Any],
    page: Page,
    lock: asyncio.Lock,
    hidden: bool,
    ctx: BrowserContext,
    app: AppState
) -> None:
    """Independent worker loop for a single channel with auto-reconnection."""
    # Staggered startup to prevent simultaneous lock contention
    if ch.index > 1:
        await asyncio.sleep((ch.index - 1) * 2.0)

    # Initial check with retry loop (never exit permanently)
    chat_box_ready = False
    while app.is_running and not chat_box_ready:
        if await wait_for_chat_box(page, ctx, hidden, app, ch_name=ch.name):
            chat_box_ready = True
            break
        ch.status = "ERROR"
        app.log(ch.name, "ERR", "Chat box not detected. Retrying in 30s...")
        await asyncio.sleep(30.0)
        try:
            await page.bring_to_front()
            await page.goto(ch.url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass

    ch.status = "READY"
    app.log(ch.name, "OK", "Channel tab ready. Starting independent timer.")

    while app.is_running:
        try:
            # Hot-reload channel settings
            current_cfg = next((c for c in load_config() if c.get("channel_url") == ch.url), initial_cfg)
            interval = int(current_cfg.get("interval_seconds", 5))
            jitter = int(current_cfg.get("jitter_seconds", 0))

            # Check if active slowmode exists
            slowmode = await get_slowmode_seconds(page)
            if slowmode > 0:
                ch.status = "SLOWMODE"
                wait_s = slowmode + (random.uniform(1.0, float(jitter)) if jitter > 0 else 1.0)
                ch.next_run = datetime.now() + timedelta(seconds=wait_s)
                app.log(ch.name, "SLOW", f"Active slowmode: {fmt_seconds(slowmode)} remaining.")
                await asyncio.sleep(wait_s)
                continue

            # Send message with typing lock
            msg = get_channel_message(current_cfg, ch.msg_idx)
            ch.msg_idx += 1
            ch.status = "SENDING"
            app.log(ch.name, "SEND", f"Dispatching message #{ch.sent_count + 1}...")

            async with lock:
                success = await send_discord_message(page, msg)

            if success:
                ch.sent_count += 1
                app.log(ch.name, "OK", f"Message #{ch.sent_count} sent successfully.")
            else:
                app.log(ch.name, "ERR", "Dispatch failed or no response.")

            await asyncio.sleep(1.0)

            # Sync post-send slowmode or standard cooldown
            new_slow = await get_slowmode_seconds(page)
            effective = new_slow if new_slow > 0 else interval
            next_s = max(1.0, effective + (random.uniform(0.0, float(jitter)) if jitter > 0 else 0.0))
            ch.next_run = datetime.now() + timedelta(seconds=next_s)

            ch.status = "SLOWMODE" if new_slow > 0 else "COOLDOWN"
            tag = "SLOW" if new_slow > 0 else "WAIT"
            app.log(ch.name, tag, f"Next schedule in {fmt_seconds(int(next_s))}.")

            await asyncio.sleep(next_s)

        except asyncio.CancelledError:
            break
        except Exception as e:
            if "Target closed" in str(e) or "has been closed" in str(e):
                break
            ch.status = "ERROR"
            app.log(ch.name, "ERR", f"Worker error: {e}")
            await asyncio.sleep(5.0)


async def tui_renderer(app: AppState) -> None:
    """Flicker-free live TUI dashboard using in-place line overwriting."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    width = 86

    while app.is_running:
        try:
            now = datetime.now()
            uptime = fmt_seconds(int((now - app.start_time).total_seconds()))

            lines = [
                f"{BOLD}{CYAN}{'=' * width}{RESET}",
                f" {BOLD}{WHITE}DISCORD TRADE SCHEDULER{RESET} {DIM}::{RESET} {CYAN}Async Multi-Tab{RESET} {DIM}::{RESET} {GREEN}Zero Mouse Hijack{RESET}",
                f"{BOLD}{CYAN}{'=' * width}{RESET}",
                f"  {DIM}Mode:{RESET} {WHITE}{app.mode:<14}{RESET} {DIM}Profile:{RESET} {CYAN}{app.profile:<10}{RESET} {DIM}Chs:{RESET} {WHITE}{len(app.channels):<3}{RESET} {DIM}Uptime:{RESET} {WHITE}{uptime:<8}{RESET} {DIM}Time:{RESET} {WHITE}{now.strftime('%H:%M:%S')}{RESET}",
                f"{GRAY}{'-' * width}{RESET}",
                f"  {BOLD}{'#':<3} {'CHANNEL NAME':<26} {'FILE':<10} {'STATUS':<12} {'SENT':<6} {'REMAINING':<11} {'NEXT RUN':<10}{RESET}",
                f"{GRAY}{'-' * width}{RESET}",
            ]

            for ch in app.channels:
                rem, nxt = "--", "--"
                if ch.next_run:
                    diff = (ch.next_run - now).total_seconds()
                    rem = fmt_seconds(int(diff)) if diff > 0 else "DUE"
                    nxt = ch.next_run.strftime("%H:%M:%S")

                badge = color_badge(ch.status, STATUS_COLORS, 12)
                lines.append(f"  {ch.index:<3} {ch.name[:25]:<26} {ch.msg_file[:9]:<10} {badge} {ch.sent_count:<6} {rem:<11} {nxt:<10}")

            lines.extend([
                f"{GRAY}{'-' * width}{RESET}",
                f" {BOLD}RECENT ACTIVITY LOG:{RESET}",
            ])

            logs = list(app.logs)
            for i in range(6):
                if i < len(logs):
                    ts, name, tag, msg = logs[i]
                    tag_str = color_badge(tag, TAG_COLORS, 8)
                    avail = max(10, width - (len(ts) + 22 + 8 + 4))
                    lines.append(f"  {DIM}[{ts}]{RESET} {BOLD}[{name[:16]:<16}]{RESET} {tag_str} {msg[:avail]}")
                else:
                    lines.append("")

            lines.extend([
                f"{BOLD}{CYAN}{'=' * width}{RESET}",
                f"  {DIM}[INFO] Hot-reload active (edit config.json / msg*.txt). Press Ctrl+C to exit.{RESET}"
            ])

            sys.stdout.write("\033[H" + "\n".join(f"{line}\033[K" for line in lines) + "\033[J")
            sys.stdout.flush()
        except Exception:
            pass
        await asyncio.sleep(0.5)


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Discord Multi-Channel Trade Scheduler")
    parser.add_argument("--gui", action="store_true", help="Display browser window on screen")
    parser.add_argument("--profile", "-p", default="default", help="Account profile name (e.g., --profile alt1)")
    parser.add_argument("--switch-account", action="store_true", help="Reset current profile and prompt new login")
    args = parser.parse_args()

    channels_cfg = load_config()
    if not channels_cfg:
        print(f"{RED}[ERROR] No channels found in config.json!{RESET}")
        return

    profile_name = args.profile.strip()
    profile_dir = PROFILE_DIR if profile_name == "default" else os.path.join(BASE_DIR, f"discord_browser_data_{profile_name}")

    if args.switch_account and os.path.exists(profile_dir):
        import shutil
        shutil.rmtree(profile_dir, ignore_errors=True)
        print(f"{YELLOW}[INFO] Profile '{profile_name}' reset. Opening window for new login...{RESET}")

    is_gui = args.gui or args.switch_account
    app = AppState(mode="GUI (Visible)" if is_gui else "No-GUI (Offscreen)", profile=profile_name)

    for idx, c in enumerate(channels_cfg):
        app.channels.append(ChannelState(
            index=idx + 1,
            name=c.get("name", f"Channel {idx + 1}"),
            url=c["channel_url"],
            msg_file=c.get("message_file", f"msg{idx + 1}.txt")
        ))

    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-gpu",
    ]
    if not is_gui:
        browser_args.extend(["--window-position=-3200,-3200", "--start-minimized"])

    app.log("SYSTEM", "SETUP", f"Launching Chrome [{profile_name}] with {len(channels_cfg)} channels...")
    tui_task = asyncio.create_task(tui_renderer(app))

    is_docker = os.path.exists("/.dockerenv") or not sys.platform.startswith("win")
    channel_name = None
    if sys.platform == "win32":
        if os.path.exists(r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
            channel_name = "chrome"
        elif os.path.exists(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
            channel_name = "msedge"

    launch_kwargs = {
        "user_data_dir": profile_dir,
        "headless": is_docker or not is_gui,
        "args": browser_args,
        "viewport": {"width": 1280, "height": 800}
    }
    if channel_name:
        launch_kwargs["channel"] = channel_name

    async with async_playwright() as p:
        ctx: BrowserContext = await p.chromium.launch_persistent_context(**launch_kwargs)

        pages: list[Page] = [ctx.pages[0] if ctx.pages else await ctx.new_page()]

        # Verify initial login on primary channel
        token = get_discord_token()
        if token:
            await inject_discord_token(pages[0], token, app)
        else:
            app.log("SYSTEM", "WARN", "No USER_TOKEN found. Checking existing browser session...")

        app.log("SYSTEM", "SETUP", "Navigating to primary channel...")
        try:
            await pages[0].bring_to_front()
            await pages[0].goto(channels_cfg[0]["channel_url"], wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass

        if not await wait_for_chat_box(pages[0], ctx, not is_gui, app, ch_name=channels_cfg[0].get("name", "Channel 1")):
            if not token:
                app.log("SYSTEM", "ERR", "Login failed! Please set USER_TOKEN in Dokploy Environment or config.json.")
            else:
                app.log("SYSTEM", "ERR", "Login failed! Please check if your USER_TOKEN is valid.")
            await ctx.close()
            return

        # Open and initialize remaining channel tabs sequentially with active focus
        app.log("SYSTEM", "SETUP", f"Opening {len(channels_cfg) - 1} remaining channel tabs...")
        for i in range(1, len(channels_cfg)):
            c = channels_cfg[i]
            app.log("SYSTEM", "SETUP", f"Loading tab [{i+1}/{len(channels_cfg)}] {c.get('name', '')}...")
            new_p = await ctx.new_page()
            pages.append(new_p)
            try:
                await new_p.bring_to_front()
                await new_p.goto(c["channel_url"], wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(1.5)
            except Exception as e:
                app.log("SYSTEM", "WARN", f"Tab {i+1} notice: {e}")

        # Launch independent workers
        send_lock = asyncio.Lock()
        workers = [
            asyncio.create_task(channel_worker(
                ch=app.channels[i], initial_cfg=channels_cfg[i], page=pages[i],
                lock=send_lock, hidden=not is_gui, ctx=ctx, app=app
            ))
            for i in range(len(channels_cfg))
        ]

        app.log("SYSTEM", "OK", f"All {len(channels_cfg)} channel workers running independently.")

        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            pass
        finally:
            app.is_running = False
            tui_task.cancel()
            try:
                await ctx.close()
            except Exception:
                pass


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        sys.stdout.write("\n\033[J")
        print(f"\n{YELLOW}[EXIT] Scheduler stopped by user. Profile saved.{RESET}")
    except Exception as e:
        sys.stdout.write("\n\033[J")
        print(f"\n{RED}[FATAL] Error: {e}{RESET}")


if __name__ == "__main__":
    main()
