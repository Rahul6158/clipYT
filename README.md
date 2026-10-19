# 🎬 clipYT — Standalone AI YouTube Viral Clipper

**clipYT** is an AI-powered standalone desktop web app that turns long YouTube videos into viral short-form clips (Shorts, Reels, TikTok) with smart vertical framing and dynamic captions.

**Zero n8n required.** Completely standalone with a full-stack FastAPI backend and modern dark glassmorphic web UI.

---

## ✨ Features & Solved Challenges

### 1. 💬 Professional, Dynamic Captions (No More Overflow!)
- **Word Burst Chunker**: Segments long speech cues into short, punchy 3-5 word bursts (1-2 seconds each) matching TikTok/Shorts pacing.
- **Safe Zone Placement**: Positioned in the lower-third with margins (`MarginL=80, MarginR=80, MarginV=260`) so words **never exceed the aspect ratio** or get blocked by mobile UI icons.
- **High-Contrast Styling**: Vibrant yellow or crisp white font with thick black outline/stroke and drop shadow. Guaranteed readable on any video background.
- **Top Hook Badge**: AI hook banner rendered at the top of the video to maximize viewer retention in the first 5 seconds.

### 2. 📐 Smart Aspect Ratio & Framing (No More Awkward Peepholes!)
- **Blurred Backdrop (Recommended)**: Keeps **100% of the widescreen video content visible** in the center while dynamically generating a zoomed, heavily blurred aesthetic background behind it. Perfect for podcasts, tutorials, slides, and gaming.
- **Center Fill**: Fills the entire 9:16 vertical canvas. Great for centered single-speaker talking heads.
- **Landscape 16:9**: Native widescreen clips for standard YouTube or Twitter/X.

### 3. 🎯 Gemini AI Virality Engine
- Evaluates transcript for strong hooks, emotional peaks, surprise factors, and punchlines.
- Auto-generates viral scores (e.g., 95/100), hook titles, and ready-to-post social captions with trending hashtags.
- Powered by `gemini-3.8-flash` with automatic fallback to `gemini-3.5-flash` and `gemini-3.1-flash-lite`.

### 4. 🎙️ Automatic Speech-to-Text with NVIDIA Canary-1B ASR (Zero Subtitles Needed!)
- When a video has **no native subtitles or transcription**, clipYT automatically extracts the high-fidelity audio stream and transcribes it using **NVIDIA Canary-1B-ASR NIM**.
- High-speed parallel chunking transcribes full videos in seconds with automatic sentence segmentation and aligned WebVTT generation.

### 5. ⚡ Live Real-Time Dashboard
- Live SSE progress bar with 4-stage pipeline tracker.
- In-browser video player with custom controls.
- One-click copy buttons for Captions, Hashtags, and Hooks.
- Direct MP4 download button.

---

## 🍪 Setting Up YouTube Cookies (`cookies.txt`)

YouTube enforces strict bot detection and download throttling on automated tools. Providing session cookies via `cookies.txt` bypasses "Sign in to confirm you're not a bot" errors and unlocks 1080p/4K stream extraction.

An empty `cookies.txt` file is included in this repository. Follow these steps to copy and paste your cookies:

### Step-by-Step Instructions:
1. **Install the Chrome Extension**:
   - Install **"Get cookies.txt LOCALLY"** (or **"copy cookies.txt locally"**) from the Chrome Web Store:
     [Get cookies.txt LOCALLY on Chrome Web Store](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. **Open YouTube & Log In**:
   - Go to [YouTube](https://www.youtube.com) in Google Chrome and ensure you are signed in to your account.
3. **Copy the Cookies**:
   - Click the extension icon in your Chrome toolbar while on `youtube.com`.
   - Click the **"Copy"** button (or export) to copy all cookies formatted in Netscape HTTP format directly to your clipboard.
4. **Paste into `cookies.txt`**:
   - Open the `cookies.txt` file located in the root of this project folder (`cookies.txt`).
   - Paste the clipboard contents into `cookies.txt` and save the file (`Ctrl + S`).
5. **Verify**:
   - Run `python run.py`. You will see `• YouTube Cookies: ✅ Loaded (cookies.txt)` in the startup terminal check!

> **Security Note:** Never commit your personal `cookies.txt` containing sensitive session tokens to public repositories.

---

## 🚀 Quick Start

### Method 1: Run Natively (Fastest & Recommended)

Ensure Python and FFmpeg are available on your system:

```powershell
python run.py
```
This automatically launches the FastAPI server and opens `http://127.0.0.1:8787` in your default browser!

### Method 2: Run with Docker

```powershell
docker compose up --build -d
```
Then visit: [http://localhost:8787](http://localhost:8787)

---

## ⚙️ Configuration (`.env`)

Create or update `.env` in the root directory:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash
PORT=8787
HOST=127.0.0.1
OUTPUT_DIR=output
NVIDIA_API_KEY=your_nvidia_nim_api_key_here
NVIDIA_ASR_MODEL=canary-1b-asr
```
