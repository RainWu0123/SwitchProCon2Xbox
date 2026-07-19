"""
Starts a local HTTP server and opens a browser to automatically wake up
the Switch 2 controller via WebUSB.
Exits automatically once the wake command is sent or if it times out.
"""
import http.server
import socketserver
import threading
import webbrowser
import json
import time
import sys
import os

PORT = 58249


class WakeHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            directory=os.path.dirname(os.path.abspath(__file__)),
            **kwargs,
        )

    def do_GET(self):
        if self.path == "/":
            self.path = "/wake.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/done":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except (TypeError, ValueError):
                content_length = 0

            post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

            try:
                data = json.loads(post_data.decode("utf-8") or "{}")
                success = data.get("success", False)
                if success:
                    print("  [OK] Auto-wake successful!")
                    self.server.wake_success = True
                else:
                    print("  [FAIL] Auto-wake failed.")
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                pass

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def trigger_auto_wake():
    print("\n  [*] Starting WebUSB Auto-Wake...")

    socketserver.TCPServer.allow_reuse_address = True

    try:
        # Bind to localhost only — no need to expose on all interfaces
        httpd = socketserver.TCPServer(("127.0.0.1", PORT), WakeHandler)
    except OSError as e:
        print(f"  [!] Failed to start server: {e}")
        return False

    httpd.wake_success = False

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{PORT}/wake.html"
    print(f"  [>] Opening {url}")

    browser_opened = False
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in chrome_paths:
        if os.path.exists(path):
            try:
                webbrowser.register(
                    "webusb_browser", None, webbrowser.BackgroundBrowser(path)
                )
                webbrowser.get("webusb_browser").open(url)
                browser_opened = True
                break
            except Exception:
                pass

    if not browser_opened:
        webbrowser.open(url)

    timeout = 60
    start_time = time.time()

    while server_thread.is_alive():
        if time.time() - start_time > timeout:
            print("  [!] Auto-wake timed out (60s).")
            try:
                httpd.shutdown()
            except Exception:
                pass
            break
        time.sleep(0.5)

    try:
        httpd.server_close()
    except Exception:
        pass
    return httpd.wake_success


if __name__ == "__main__":
    success = trigger_auto_wake()
    sys.exit(0 if success else 1)
