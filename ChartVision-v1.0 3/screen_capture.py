"""
Screen Capture Module
Handles taking screenshots of a specific screen region at configurable intervals.
"""

import io
import time
import base64
import threading
from PIL import Image

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False


def get_monitors():
    """
    Returns a list of all connected monitors.
    Each entry: {"index": i, "left": x, "top": y, "width": w, "height": h, "label": str}
    Index 0 = combined virtual desktop, 1+ = individual monitors.
    """
    if not MSS_AVAILABLE:
        return []
    with mss.mss() as sct:
        monitors = []
        for i, m in enumerate(sct.monitors):
            if i == 0:
                continue   # skip the "all screens" combined monitor
            monitors.append({
                "index":  i,
                "left":   m["left"],
                "top":    m["top"],
                "width":  m["width"],
                "height": m["height"],
                "label":  f"Screen {i}  ({m['width']}×{m['height']})",
            })
        return monitors


class ScreenCapture:
    """Captures screenshots of a defined screen region."""

    def __init__(self, region=None):
        """
        Args:
            region: dict with keys 'left', 'top', 'width', 'height' (in pixels)
                    If None, captures the full primary monitor.
        """
        self.region = region
        self._running = False
        self._thread = None

    def set_region(self, left, top, width, height):
        """Set the capture region."""
        self.region = {
            "left": int(left),
            "top": int(top),
            "width": int(width),
            "height": int(height),
        }

    def set_monitor(self, monitor_index: int):
        """Set region to capture an entire monitor by index (1-based)."""
        if not MSS_AVAILABLE:
            return
        with mss.mss() as sct:
            if monitor_index < len(sct.monitors):
                m = sct.monitors[monitor_index]
                self.set_region(m["left"], m["top"], m["width"], m["height"])

    def capture_once(self) -> Image.Image:
        """Take a single screenshot of the defined region. Returns a PIL Image."""
        if not MSS_AVAILABLE:
            raise RuntimeError("mss library is not installed. Run: pip install mss")

        with mss.mss() as sct:
            monitor = self.region if self.region else sct.monitors[1]
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return img

    def capture_to_base64(self, max_size=(1200, 800)) -> str:
        """
        Capture screenshot and return as base64-encoded JPEG string.
        Resizes to max_size to keep API costs down.
        """
        img = self.capture_once()
        img.thumbnail(max_size, Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        buffer.seek(0)
        return base64.standard_b64encode(buffer.read()).decode("utf-8")

    def start_continuous(self, interval_seconds, callback):
        """
        Start capturing at regular intervals in a background thread.

        Args:
            interval_seconds: Time between captures.
            callback: Function called with each PIL Image capture.
        """
        self._running = True

        def _loop():
            while self._running:
                try:
                    img = self.capture_once()
                    callback(img)
                except Exception as e:
                    print(f"[ScreenCapture] Error: {e}")
                time.sleep(interval_seconds)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop continuous capture."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None


def image_to_base64(img: Image.Image, max_size=(1200, 800)) -> str:
    """Convert a PIL Image to base64 JPEG string."""
    img_copy = img.copy()
    img_copy.thumbnail(max_size, Image.LANCZOS)
    buffer = io.BytesIO()
    img_copy.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return base64.standard_b64encode(buffer.read()).decode("utf-8")
