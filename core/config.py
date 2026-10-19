import os
import shutil
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "output"))).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load .env if present
def load_env_file():
    candidates = [BASE_DIR / ".env", BASE_DIR.parent / ".env"]
    for path in candidates:
        if path.is_file():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and not os.getenv(k):
                            os.environ[k] = v
            except Exception:
                pass

load_env_file()

# Configuration Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_ASR_MODEL = os.getenv("NVIDIA_ASR_MODEL", "canary-1b-asr").strip()
NVIDIA_ASR_FUNCTION_ID = os.getenv("NVIDIA_ASR_FUNCTION_ID", "b0e8b4a5-217c-40b7-9b96-17d84e666317").strip()
NVIDIA_RIVA_URI = os.getenv("NVIDIA_RIVA_URI", "grpc.nvcf.nvidia.com:443").strip()
PORT = int(os.getenv("PORT", "8787"))
HOST = os.getenv("HOST", "127.0.0.1")
MAX_VIDEO_BYTES = int(os.getenv("MAX_VIDEO_BYTES", str(2 * 1024 * 1024 * 1024))) # 2 GB limit
COOKIES_PATH = Path(os.getenv("COOKIES_PATH", str(BASE_DIR / "cookies.txt"))).resolve()

def get_yt_dlp_cookie_args():
    """Returns yt-dlp cookie arguments using an isolated temporary runtime copy
    to prevent yt-dlp from overwriting or corrupting the master cookies.txt file upon exit."""
    cookie_file = None
    if COOKIES_PATH.is_file() and COOKIES_PATH.stat().st_size > 10:
        cookie_file = COOKIES_PATH
    else:
        local_candidate = BASE_DIR / "cookies.local.txt"
        if local_candidate.is_file() and local_candidate.stat().st_size > 10:
            cookie_file = local_candidate

    if cookie_file:
        try:
            import tempfile
            runtime_cookie = Path(tempfile.gettempdir()) / "clipyt_runtime_cookies.txt"
            shutil.copyfile(cookie_file, runtime_cookie)
            return ["--cookies", str(runtime_cookie)]
        except Exception:
            return ["--cookies", str(cookie_file)]
    return []

def get_yt_dlp_base_args():
    """Returns base yt-dlp flags: cookies, Node JS challenge solver, and EJS components."""
    args = ["--no-warnings"]
    args.extend(get_yt_dlp_cookie_args())

    node_bin = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
    if os.path.exists(node_bin):
        args.extend(["--js-runtimes", f"node:{node_bin}", "--remote-components", "ejs:github"])
    else:
        args.extend(["--remote-components", "ejs:github"])
    return args

def check_system_tools():
    """Verify system binaries ffmpeg and yt-dlp exist."""
    return {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "yt_dlp": shutil.which("yt-dlp") is not None,
        "gemini_api_key_configured": bool(GEMINI_API_KEY),
        "nvidia_canary_configured": bool(NVIDIA_API_KEY),
        "cookies_configured": bool(get_yt_dlp_cookie_args())
    }

