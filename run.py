#!/usr/bin/env python3
"""
clipYT Launcher
Runs the standalone clipYT AI Video Clipper server and launches the UI in your default browser.
"""

import sys
import webbrowser
import threading
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.config import PORT, HOST, check_system_tools

def open_browser():
    time.sleep(1.2)
    url = f"http://{HOST}:{PORT}"
    print(f"\n🚀 Opening clipYT UI at: {url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

if __name__ == "__main__":
    tools = check_system_tools()
    print("=" * 60)
    print("🎬 clipYT - Standalone AI YouTube Viral Video Clipper")
    print("=" * 60)
    print(f"• FFmpeg installed:          {'✅ Yes' if tools['ffmpeg'] else '❌ Missing'}")
    print(f"• yt-dlp installed:          {'✅ Yes' if tools['yt_dlp'] else '❌ Missing'}")
    print(f"• Gemini API Key configured: {'✅ Yes' if tools['gemini_api_key_configured'] else '⚠️ Missing (check .env)'}")
    print(f"• Canary ASR (NVIDIA NIM):   {'✅ Configured' if tools['nvidia_canary_configured'] else '⚠️ Missing (check .env)'}")
    print(f"• YouTube Cookies:           {'✅ Loaded (cookies.txt)' if tools['cookies_configured'] else '⚠️ None (check cookies.txt)'}")
    print("=" * 60)

    if not tools['ffmpeg']:
        print("⚠️ Warning: FFmpeg is required for video rendering. Ensure it is added to your PATH.")
    if not tools['yt_dlp']:
        print("⚠️ Warning: yt-dlp is required for downloading videos. Install via: pip install yt-dlp")

    # Start browser opener in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
