"""Create a desktop shortcut for start.bat (optional helper).

Usage:
    python setup_shortcut.py
    python setup_shortcut.py --icon path/to/icon.png
"""
import argparse
import os
import subprocess
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(PROJECT_DIR, "icon.ico")
BAT_PATH = os.path.join(PROJECT_DIR, "start.bat")


def find_desktop() -> str:
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "桌面")
    if os.path.isdir(desktop):
        return desktop
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    if os.path.isdir(desktop):
        return desktop
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True, text=True,
    )
    path = (result.stdout or "").strip()
    if path and os.path.isdir(path):
        return path
    raise FileNotFoundError("Could not locate Desktop folder")


def ensure_ico(icon_src: Optional[str]) -> str:
    if os.path.isfile(ICO_PATH):
        return ICO_PATH
    if not icon_src:
        return ICO_PATH  # may be missing; shortcut still works
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; skip ICO conversion. "
              "Install with: pip install pillow")
        return ICO_PATH

    if not os.path.isfile(icon_src):
        print(f"Icon source not found: {icon_src}")
        return ICO_PATH

    img = Image.open(icon_src).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    imgs = [img.resize(size, Image.LANCZOS) for size in sizes]
    imgs[0].save(ICO_PATH, format="ICO", sizes=sizes, append_images=imgs[1:])
    print(f"ICO saved: {ICO_PATH}")
    return ICO_PATH


def create_shortcut(icon_path: str) -> str:
    desktop = find_desktop()
    shortcut_path = os.path.join(desktop, "Switch to Xbox.lnk")

    # Escape for PowerShell double-quoted strings
    def ps_escape(s: str) -> str:
        return s.replace("'", "''")

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{ps_escape(shortcut_path)}')
$Shortcut.TargetPath = '{ps_escape(BAT_PATH)}'
$Shortcut.WorkingDirectory = '{ps_escape(PROJECT_DIR)}'
$Shortcut.IconLocation = '{ps_escape(icon_path)}, 0'
$Shortcut.Description = 'Switch Pro Controller to Xbox 360 Translator'
$Shortcut.WindowStyle = 1
$Shortcut.Save()
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error creating shortcut: {result.stderr}")
        sys.exit(1)
    return shortcut_path


def main():
    parser = argparse.ArgumentParser(description="Create desktop shortcut")
    parser.add_argument(
        "--icon", default=None,
        help="Optional PNG path to convert into icon.ico",
    )
    args = parser.parse_args()

    if not os.path.isfile(BAT_PATH):
        print(f"start.bat not found at {BAT_PATH}")
        sys.exit(1)

    icon = ensure_ico(args.icon)
    path = create_shortcut(icon if os.path.isfile(icon) else BAT_PATH)
    print(f"Desktop shortcut created: {path}")
    print("All done!")


if __name__ == "__main__":
    main()
