"""Render the static dashboard to PNG screenshots for the README.

Uses headless Chrome, which ships with Google Chrome on macOS and is available on
Linux CI images. If no Chrome binary is found the script exits non-zero with an
explanation rather than producing a placeholder image — a fabricated screenshot
would misrepresent the deliverable.

Usage
-----
    python scripts/capture_screenshots.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import config  # noqa: E402

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)

# Heights are the rendered page height at 1280px wide. If a panel is added the
# full-page shot must be re-measured, or the capture silently truncates.
SHOTS = (
    ("dashboard_full.png", 1280, 6650),
    ("dashboard_overview.png", 1280, 1135),
)


def find_chrome() -> str | None:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def capture(chrome: str, source: Path, out: Path, width: int, height: int,
            timeout_s: int = 90) -> None:
    """Screenshot one page.

    Chrome writes the PNG and then does not always exit on macOS, so the process
    is polled for the output file and terminated once it appears rather than
    waited on.
    """
    out.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--force-color-profile=srgb",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            "--screenshot=" + str(out),
            "--virtual-time-budget=4000",
            source.as_uri(),
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + timeout_s
        try:
            while time.monotonic() < deadline:
                if out.exists() and out.stat().st_size > 0:
                    time.sleep(0.4)          # let the write settle
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    proc.kill()

    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"Chrome produced no screenshot at {out}")


def main() -> int:
    source = config.DASHBOARD_DIR / "dashboard.html"
    if not source.exists():
        print("dashboard.html not found. Run: make dashboard", file=sys.stderr)
        return 1

    chrome = find_chrome()
    if not chrome:
        print(
            "BLOCKED: no Chrome/Chromium binary found, so dashboard screenshots "
            "cannot be captured in this environment. The dashboard itself is built "
            "and viewable at 05_dashboard/dashboard.html.",
            file=sys.stderr,
        )
        return 2

    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Using: {chrome}")
    for name, width, height in SHOTS:
        out = config.ASSETS_DIR / name
        capture(chrome, source, out, width, height)
        print(f"  [out] {out.relative_to(REPO_ROOT)} "
              f"({out.stat().st_size / 1024:,.0f} KB, {width}x{height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
