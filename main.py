"""
Switch → Xbox Controller Translator
====================================
Reads input from a Nintendo Switch Pro Controller (USB) and emulates
a virtual Xbox 360 controller via ViGEmBus.

Usage:
    python main.py                  # Default: Xbox layout, lite UI
    python main.py --layout nintendo
    python main.py --ui full        # Full dashboard
    python main.py --deadzone 0.1
"""

import sys
import time
import signal
import argparse
import os
import io
import ctypes
import threading

from hidhide import DeviceHider, is_admin

from controller_reader import SwitchProController, ControllerState
from xbox_emulator import XboxEmulator
from mapper import InputMapper, MappedState
import auto_wake

# ─── Constants ────────────────────────────────────────────────────
RECONNECT_DELAY = 2.0
STATUS_LITE_INTERVAL = 1.0   # One-line status: 1 Hz (low console cost)
STATUS_FULL_INTERVAL = 0.5   # Full dashboard: 2 Hz

# ─── ANSI helpers ─────────────────────────────────────────────────
C_TITLE = "\033[96;1m"
C_OK = "\033[92;1m"
C_WARN = "\033[93;1m"
C_ERR = "\033[91;1m"
C_DIM = "\033[37;2m"
C_BTN_ON = "\033[92;1m"
C_BTN_OFF = "\033[90;1m"
C_RESET = "\033[0m"


def setup_utf8():
    """Force UTF-8 output on Windows terminals."""
    if os.name == 'nt':
        os.system('chcp 65001 >nul 2>&1')
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding='utf-8', errors='replace')


def clear_screen():
    # ANSI clear — avoids spawning a shell (os.system) every time
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def battery_icon(level: int) -> str:
    """Convert battery nibble (0-8) to icon."""
    if level >= 8:
        return f"{C_OK}█████{C_RESET} 100%"
    elif level >= 6:
        return f"{C_OK}████░{C_RESET}  75%"
    elif level >= 4:
        return f"{C_WARN}███░░{C_RESET}  50%"
    elif level >= 2:
        return f"{C_ERR}██░░░{C_RESET}  25%"
    else:
        return f"{C_ERR}█░░░░{C_RESET}  ~0%"


def btn(name: str, pressed: bool) -> str:
    """Format a button indicator."""
    if pressed:
        return f"{C_BTN_ON}[{name}]{C_RESET}"
    else:
        return f"{C_BTN_OFF}[{name}]{C_RESET}"


def stick_display(x: int, y: int, label: str) -> str:
    """Format stick position as a compact display."""
    # Normalize to -1..1
    nx = (x - 2048) / 2048.0
    ny = (y - 2048) / 2048.0
    return f"{label}: {C_TITLE}{nx:+.2f}{C_RESET},{C_TITLE}{ny:+.2f}{C_RESET}"


def render_status_lite(ctrl_name: str, layout: str, fps: float, state=None):
    """Single-line status — minimal console I/O for smoother input path."""
    bat = f"  bat={state.battery_level}" if state is not None else ""
    lay = "nintendo" if layout == "nintendo" else "xbox"
    line = (
        f"\r  {C_OK}*{C_RESET} {ctrl_name}  "
        f"{C_DIM}{lay}{C_RESET}  "
        f"{C_TITLE}{fps:.0f} Hz{C_RESET}{bat}  "
        f"{C_DIM}| Ctrl+C quit{C_RESET}   "
    )
    sys.stdout.write(line)
    sys.stdout.flush()


def render_status(state: ControllerState, ctrl_name: str, layout: str,
                  fps: float):
    """Render the full CLI status display."""
    lines = []
    sep = f"{C_DIM}{'-' * 56}{C_RESET}"

    lines.append("")
    lines.append(
        f"  {C_TITLE}[>] Switch -> Xbox Controller Translator{C_RESET}")
    lines.append(f"  {sep}")
    lines.append(
        f"  Controller : {C_OK}{ctrl_name}{C_RESET}")
    lines.append(
        f"  Status     : {C_OK}* Connected{C_RESET}   "
        f"Poll: {C_DIM}{fps:.0f} Hz{C_RESET}")
    lay_str = "Nintendo (A↔B X↔Y 互換)" if layout == "nintendo" else "Xbox (直接對應 A→A B→B)"
    lines.append(f"  Layout     : {C_TITLE}{lay_str}{C_RESET}")
    lines.append(
        f"  Battery    : {battery_icon(state.battery_level)}")
    lines.append(f"  {sep}")

    lines.append(
        f"  {btn('ZL', state.zl)} {btn('L', state.l)}      "
        f"{btn('R', state.r)} {btn('ZR', state.zr)}")

    u = "^" if state.dpad_up else "."
    d = "v" if state.dpad_down else "."
    le = "<" if state.dpad_left else "."
    r = ">" if state.dpad_right else "."

    lines.append(
        f"         {C_TITLE}{u}{C_RESET}              "
        f"{btn('X', state.x)}")
    lines.append(
        f"       {C_TITLE}{le} · {r}{C_RESET}       "
        f"{btn('Y', state.y)}  {btn('A', state.a)}")
    lines.append(
        f"         {C_TITLE}{d}{C_RESET}              "
        f"{btn('B', state.b)}")

    lines.append(
        f"     {btn('-', state.minus)}  "
        f"{btn('H', state.home)}  "
        f"{btn('C', state.capture)}  "
        f"{btn('+', state.plus)}")

    lines.append(f"  {sep}")

    ls = stick_display(state.left_stick_x, state.left_stick_y, "L-Stick")
    rs = stick_display(state.right_stick_x, state.right_stick_y, "R-Stick")
    lines.append(
        f"  {ls}  {btn('L3', state.l_stick_click)}   "
        f"{rs}  {btn('R3', state.r_stick_click)}")

    lines.append(
        f"  Back Grips: {btn('GL', state.gl)}  {btn('GZ', state.gz)}")

    lines.append(f"  {sep}")
    lines.append(
        f"  {C_DIM}Press Ctrl+C to exit{C_RESET}")
    lines.append("")

    sys.stdout.write("\033[H" + "\033[K\n".join(lines) + "\033[K\033[J")
    sys.stdout.flush()


def wait_for_controller(ctrl: SwitchProController):
    """Block until a controller is found, with a spinner animation."""
    spinner = ["/", "-", "\\", "|", "/", "-", "\\", "|"]
    idx = 0
    print(f"\n  {C_WARN}Waiting for Switch Pro Controller (USB)...{C_RESET}")
    print(f"  {C_DIM}Plug in your controller with a USB-C cable.{C_RESET}\n")

    while True:
        sys.stdout.write(
            f"\r  {C_TITLE}{spinner[idx % len(spinner)]}{C_RESET} "
            f"Scanning...   ")
        sys.stdout.flush()
        idx += 1

        if ctrl.find_and_connect():
            sys.stdout.write(
                f"\r  {C_OK}[OK] Found: {ctrl.controller_name}{C_RESET}"
                "                    \n")
            return
        time.sleep(0.5)


def render_diagnostic_screen(ctrl_name: str, pid: int):
    """Render a premium CLI diagnostics guide for genuine Switch 2 Pro Controller."""
    lines = []
    sep = f"{C_DIM}{'=' * 58}{C_RESET}"
    
    lines.append("")
    lines.append(f"  {C_TITLE}[!] Genuine Switch 2 Pro Controller Detected!{C_RESET}")
    lines.append(f"  {sep}")
    lines.append(f"  Device Name : {C_OK}{ctrl_name}{C_RESET}")
    lines.append(f"  Product ID  : {C_TITLE}0x{pid:04X}{C_RESET}")
    lines.append(f"  Status      : {C_WARN}Sleeping (Waiting for Wake Command...){C_RESET}")
    lines.append(f"  {sep}")
    lines.append(f"  {C_OK}[Auto-Wake in Progress]{C_RESET}")
    lines.append("  Nintendo's new Switch 2 Pro Controller requires a special")
    lines.append("  wake-up command over USB Bulk Transfer before it sends input.")
    lines.append("")
    lines.append(f"  {C_TITLE}What's happening now?{C_RESET}")
    lines.append("    1. Your browser will open automatically.")
    lines.append("    2. If you've paired before, it will wake up instantly.")
    lines.append("    3. If not, click 'Pair Controller' in the browser.")
    lines.append(f"    4. {C_WARN}Once the controller vibrates, the browser tab will close.{C_RESET}")
    lines.append("")
    lines.append("  As soon as it wakes up, this terminal will automatically switch")
    lines.append("  to the active dashboard and you're ready to play!")
    lines.append(f"  {sep}")
    lines.append(f"  {C_DIM}Listening for HID activation reports...{C_RESET}")
    lines.append("")

    # Move cursor to top, clear each line's tail during write, and clear trailing lines
    sys.stdout.write("\033[H" + "\033[K\n".join(lines) + "\033[K\033[J")
    sys.stdout.flush()


def request_admin():
    """Re-launch the script with admin privileges if not already admin."""
    if is_admin():
        return True
    try:
        # Re-run the script elevated
        script = os.path.abspath(sys.argv[0])
        params = ' '.join(sys.argv[1:])
        # Use the same Python executable
        python_exe = sys.executable
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", python_exe, f'"{script}" {params}', None, 1)
        sys.exit(0)  # Exit the non-elevated instance
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Switch Pro Controller → Xbox 360 Translator")
    parser.add_argument(
        "--layout", choices=["nintendo", "xbox"], default="xbox",
        help="Button layout mode (default: xbox = direct A->A, B->B)")
    parser.add_argument(
        "--deadzone", type=float, default=0.05,
        help="Stick deadzone 0.0-0.99 (default: 0.05)")
    parser.add_argument(
        "--no-invert-y", action="store_true",
        help="Do not invert stick Y axis (default: invert so up = positive)")
    parser.add_argument(
        "--ui", choices=["lite", "full", "off"], default="lite",
        help="Status UI: lite=one line (default), full=dashboard, off=silent")
    parser.add_argument(
        "--no-hide", action="store_true",
        help="Skip HidHide device hiding (not recommended)")
    parser.add_argument(
        "--unhide", action="store_true",
        help="Force-unhide all controllers and exit (use to restore Steam Input)")
    args = parser.parse_args()

    # Enable native ANSI colors in Windows console
    os.system('')
    setup_utf8()

    # Ensure immediate flushing of standard prints
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass

    clear_screen()

    # ── Handle --unhide: force-reset HidHide and exit ──
    if args.unhide:
        print(f"\n  {C_TITLE}[*] Force-unhiding all controllers...{C_RESET}\n", flush=True)
        if not is_admin():
            print(f"  {C_WARN}[!] 需要系統管理員權限{C_RESET}", flush=True)
            print(f"  {C_DIM}    正在請求管理員權限...{C_RESET}\n", flush=True)
            request_admin()
            print(f"  {C_ERR}    無法取得管理員權限{C_RESET}", flush=True)
            sys.exit(1)

        hider = DeviceHider()
        if hider.force_reset():
            print(f"  {C_OK}  [OK] 已恢復所有手把裝置的可見性！{C_RESET}", flush=True)
            print(f"  {C_OK}  [OK] Steam Input 現在應該可以偵測到手把了{C_RESET}", flush=True)
        else:
            print(f"  {C_WARN}  [WARN] HidHide 未安裝或無法執行{C_RESET}", flush=True)
        print(f"\n  {C_DIM}完成。可以關閉此視窗。{C_RESET}\n", flush=True)
        sys.exit(0)

    # Banner
    print(f"""
  {C_TITLE}+----------------------------------------------+
  |  [>] Switch -> Xbox Controller Translator    |
  |      v1.5  |  USB Wired  |  ViGEmBus        |
  +----------------------------------------------+{C_RESET}
    """, flush=True)

    # ── Step 0: Check admin for device hiding ──
    # start.bat already elevates; only re-launch if we are still non-admin
    # and the user did not pass --no-hide. request_admin() exits on success.
    device_hider = DeviceHider()

    if not args.no_hide and not is_admin():
        print(f"  {C_WARN}[!] 需要系統管理員權限來隱藏原始手把裝置{C_RESET}", flush=True)
        print(f"  {C_DIM}    正在請求管理員權限...{C_RESET}\n", flush=True)
        elevated = request_admin()
        if elevated is False or not is_admin():
            print(f"  {C_ERR}    無法取得管理員權限，跳過裝置隱藏{C_RESET}", flush=True)
            print(f"  {C_WARN}    遊戲中可能會不斷切換鍵盤/手把{C_RESET}\n", flush=True)
            # Refresh hider availability after failed elevation attempt
            device_hider = DeviceHider()

    # ── Step 1: Create virtual Xbox controller ──
    print(f"  {C_DIM}[1/3] Creating virtual Xbox 360 controller...{C_RESET}", flush=True)
    try:
        xbox = XboxEmulator()
        print(f"  {C_OK}  [OK] Virtual Xbox 360 controller created{C_RESET}\n", flush=True)
    except Exception as e:
        print(f"  {C_ERR}  [FAIL] Failed to create virtual controller!{C_RESET}", flush=True)
        print(f"  {C_ERR}    Error: {e}{C_RESET}", flush=True)
        print(f"\n  {C_WARN}Make sure ViGEmBus driver is installed.{C_RESET}", flush=True)
        print(f"  {C_DIM}Run: pip install vgamepad  (it will prompt to "
              f"install the driver){C_RESET}\n", flush=True)
        sys.exit(1)

    # ── Step 2: Find Switch Pro Controller ──
    print(f"  {C_DIM}[2/3] Looking for Switch Pro Controller...{C_RESET}", flush=True)
    ctrl = SwitchProController()

    if not ctrl.find_and_connect():
        wait_for_controller(ctrl)

    print(f"  {C_OK}  [OK] Connected: {ctrl.controller_name}"
          f" (PID: 0x{ctrl.product_id:04X}){C_RESET}\n", flush=True)

    # ── Step 3: Initialize controller ──
    print(f"  {C_DIM}[3/3] Initializing USB protocol...{C_RESET}", flush=True)
    init_success = ctrl.initialize()
    if init_success:
        print(f"  {C_OK}  [OK] Controller initialized (120Hz mode + vibration){C_RESET}\n", flush=True)
    else:
        print(f"  {C_WARN}  [WARN] Handshake failed or ignored. Standard Pro controller handshake protocol might not be supported by this device.{C_RESET}\n", flush=True)

    # ── Step 3.5: Hide the physical controller from games ──
    # This MUST happen AFTER we open the HID device (find_and_connect)
    # because our hidapi handle will keep working even after the device node is disabled.
    if not args.no_hide and device_hider.available:
        print(f"  {C_DIM}[*] 隱藏原始手把裝置...{C_RESET}", flush=True)
        if device_hider.setup():
            print(f"  {C_OK}  [OK] 已隱藏原始手把，遊戲只會看到 Xbox 360 手把{C_RESET}\n", flush=True)
        else:
            print(f"  {C_WARN}  [WARN] 無法隱藏裝置{C_RESET}\n", flush=True)

    # ── Create mapper (hot-path reusable output) ──
    mapper = InputMapper(
        layout=args.layout,
        deadzone=args.deadzone,
        invert_y=not args.no_invert_y,
    )
    mapped = MappedState()
    ui_mode = args.ui
    status_interval = (
        STATUS_FULL_INTERVAL if ui_mode == "full" else STATUS_LITE_INTERVAL
    )

    # Rumble callbacks arrive on a ViGEm worker thread; serialize HID writes.
    rumble_lock = threading.Lock()

    def on_rumble(client, target, large_motor, small_motor, led_number, user_data):
        """Forward Xbox rumble requests to the physical Switch controller."""
        with rumble_lock:
            ctrl.send_rumble(large_motor, small_motor)

    xbox.register_rumble_callback(on_rumble)

    # Test rumble: brief buzz to confirm vibration is working
    if init_success:
        print(f"  {C_DIM}[*] Testing vibration...{C_RESET}", flush=True)
        ctrl.test_rumble()
        print(f"  {C_OK}  [OK] Rumble forwarding enabled{C_RESET}\n", flush=True)
    else:
        print(f"  {C_WARN}  [WARN] Skipping rumble test (handshake not completed){C_RESET}\n", flush=True)

    if ui_mode == "lite":
        print(f"  {C_DIM}Lite UI on — use --ui full for dashboard, --ui off for silent{C_RESET}\n",
              flush=True)

    # ── Graceful shutdown ──
    running = True

    def signal_handler(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, signal_handler)

    # ── Main loop (hot path kept tight) ──
    if ui_mode == "full":
        clear_screen()
    frame_count = 0
    fps = 0.0
    fps_timer = time.perf_counter()
    last_display = 0.0

    last_data_received_time = time.perf_counter()
    last_keepalive_time = time.perf_counter()
    has_shown_diagnostic = False
    auto_wake_started = False
    latest_state = None
    xbox_warn_shown = False
    SWITCH2_WAKE_IDLE_SEC = 3.0
    GENERIC_IDLE_SEC = 5.0

    try:
        while running:
            # Wait + drain queue → always process the freshest report only
            latest_state = ctrl.read_latest(timeout_ms=8)
            now = time.perf_counter()

            # Keepalive is rare (~0.2 Hz) and never on the critical path of every frame
            if now - last_keepalive_time >= 5.0:
                with rumble_lock:
                    ctrl.send_keepalive()
                last_keepalive_time = now

            if latest_state is not None:
                mapper.translate_into(latest_state, mapped)
                xbox.update_mapped(mapped)
                if not xbox.active and not xbox_warn_shown:
                    print(f"\n  {C_ERR}[!] Virtual Xbox controller stopped responding.{C_RESET}",
                          flush=True)
                    print(f"  {C_DIM}    Check ViGEmBus driver / restart the app.{C_RESET}\n",
                          flush=True)
                    xbox_warn_shown = True
                frame_count += 1
                last_data_received_time = now
                has_shown_diagnostic = False

            # FPS once per second
            elapsed = now - fps_timer
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                fps_timer = now

            # UI is deliberately throttled so it never starves the input path
            if ui_mode != "off" and now - last_display >= status_interval:
                idle_for = now - last_data_received_time
                if idle_for < 2.0 and latest_state is not None:
                    if ui_mode == "full":
                        render_status(
                            latest_state, ctrl.controller_name, args.layout, fps)
                    else:
                        render_status_lite(
                            ctrl.controller_name, args.layout, fps, latest_state)
                elif ctrl.product_id == 0x2069 and idle_for >= SWITCH2_WAKE_IDLE_SEC:
                    if not has_shown_diagnostic:
                        if ui_mode == "full":
                            clear_screen()
                        has_shown_diagnostic = True
                        render_diagnostic_screen(
                            ctrl.controller_name, ctrl.product_id)
                        if not auto_wake_started:
                            auto_wake_started = True
                            threading.Thread(
                                target=auto_wake.trigger_auto_wake, daemon=True
                            ).start()
                elif idle_for >= GENERIC_IDLE_SEC and not has_shown_diagnostic:
                    has_shown_diagnostic = True
                    print(f"\n  {C_WARN}[!] No input reports for {idle_for:.0f}s{C_RESET}",
                          flush=True)
                    print(f"  {C_DIM}    Waiting for controller data... "
                          f"(press a button / check USB cable){C_RESET}\n", flush=True)
                last_display = now

            # Check for disconnection
            if not ctrl.connected:
                clear_screen()
                print(f"\n  {C_ERR}[!] Controller disconnected!{C_RESET}", flush=True)
                print(f"  {C_DIM}    Attempting to reconnect...{C_RESET}\n", flush=True)
                
                # Temporarily disable cloaking to ensure Windows reinitializes it and we can find it
                if not args.no_hide and device_hider.available:
                    device_hider.cleanup()
                
                ctrl.disconnect()
                time.sleep(RECONNECT_DELAY)

                ctrl = SwitchProController()
                if ctrl.find_and_connect():
                    ctrl.initialize()
                    xbox.register_rumble_callback(on_rumble)
                    if not args.no_hide and device_hider.available:
                        device_hider.setup()
                    clear_screen()
                    last_data_received_time = time.perf_counter()
                    has_shown_diagnostic = False
                    auto_wake_started = False
                else:
                    wait_for_controller(ctrl)
                    ctrl.initialize()
                    xbox.register_rumble_callback(on_rumble)
                    if not args.no_hide and device_hider.available:
                        device_hider.setup()
                    clear_screen()
                    last_data_received_time = time.perf_counter()
                    has_shown_diagnostic = False
                    auto_wake_started = False

    except Exception as e:
        print(f"\n  {C_ERR}Error: {e}{C_RESET}", flush=True)

    finally:
        # Clean shutdown
        print(f"\n\n  {C_DIM}Shutting down...{C_RESET}", flush=True)
        ctrl.disconnect()
        xbox.cleanup()
        # Restore device visibility
        if device_hider.disabled_devices:
            device_hider.cleanup()
            print(f"  {C_OK}[OK] 已恢復原始手把裝置可見性{C_RESET}", flush=True)
        print(f"  {C_OK}[OK] Virtual controller removed.{C_RESET}", flush=True)
        print(f"  {C_OK}[OK] Switch controller disconnected.{C_RESET}", flush=True)
        print(f"  {C_DIM}Goodbye!{C_RESET}\n", flush=True)


if __name__ == "__main__":
    main()
