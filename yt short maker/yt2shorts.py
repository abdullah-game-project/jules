#!/usr/bin/env python3
"""
yt2shorts — YouTube Long-Form → Shorts Converter
Professional CLI tool for converting long YouTube videos into viral short clips.
Uses Gemini AI for viral moment detection + local FFmpeg processing.
"""

# ────────────────────────────────────────────────
#  STANDARD-LIBRARY IMPORTS
# ────────────────────────────────────────────────
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import threading

# ────────────────────────────────────────────────
#  COLOUR / STYLE HELPERS
# ────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
BLUE    = "\033[94m"
CYAN    = "\033[96m"
WHITE   = "\033[97m"
MAGENTA = "\033[95m"


def c(text: str, *codes: str) -> str:
    """Wrap text in ANSI colour/style codes."""
    return "".join(codes) + str(text) + RESET


def banner() -> None:
    logo = r"""
  ╔═══════════════════════════════════════════════════════╗
  ║   ██╗   ██╗████████╗██████╗ ███████╗██╗  ██╗ ██████╗ ║
  ║   ╚██╗ ██╔╝╚══██╔══╝╚════██╗██╔════╝██║  ██║██╔═══██╗║
  ║    ╚████╔╝    ██║    █████╔╝███████╗███████║██║   ██║║
  ║     ╚██╔╝     ██║   ██╔═══╝ ╚════██║██╔══██║██║   ██║║
  ║      ██║      ██║   ███████╗███████║██║  ██║╚██████╔╝║
  ║      ╚═╝      ╚═╝   ╚══════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ║
  ║          YouTube → Shorts  |  Powered by Gemini AI    ║
  ╚═══════════════════════════════════════════════════════╝"""
    print(c(logo, CYAN, BOLD))
    print()


def show_menu() -> str:
    print("\n" + c("═" * 60, CYAN))
    print(c("  MAIN MENU", BOLD, WHITE))
    print(c("═" * 60, CYAN))
    print(f"  {c('1', CYAN, BOLD)}. {c('Make Shorts', GREEN)}        - Convert YouTube video to Shorts")
    print(f"  {c('2', CYAN, BOLD)}. {c('Cookies', YELLOW)}           - Import/Manage YouTube cookies (JSON format)")
    print(f"  {c('3', CYAN, BOLD)}. {c('Gemini API', MAGENTA)}       - Manage multiple Gemini API keys")
    print(f"  {c('4', CYAN, BOLD)}. {c('Exit', RED)}                 - Exit program")
    print(c("═" * 60, CYAN))
    return prompt("Select an option", "1").strip()


def _spinner_frames() -> List[str]:
    return ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def progress_bar(current: int, total: int, width: int = 40, label: str = "") -> str:
    pct = current / max(total, 1)
    fill = int(width * pct)
    bar = "█" * fill + "░" * (width - fill)
    return f"  {c(bar, GREEN)}  {c(f'{pct * 100:5.1f}%', BOLD, YELLOW)}  {label}"


def section(title: str) -> None:
    print(f"\n  {c('─' * 60, CYAN)}")
    print(f"  {c('  ' + title, BOLD, WHITE)}")
    print(f"  {c('─' * 60, CYAN)}")


def ok(msg: str) -> None:
    print(f"  {c('✓', GREEN, BOLD)}  {msg}")


def info(msg: str) -> None:
    print(f"  {c('ℹ', BLUE, BOLD)}  {msg}")


def warn(msg: str) -> None:
    print(f"  {c('⚠', YELLOW, BOLD)}  {msg}")


def err(msg: str) -> None:
    print(f"  {c('✗', RED, BOLD)}  {msg}")


def prompt(msg: str, default: str = "") -> str:
    hint = f" [{c(default, DIM)}]" if default else ""
    try:
        val = input(f"\n  {c('▶', MAGENTA, BOLD)} {msg}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val or default


def confirm(msg: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    try:
        raw = input(f"\n  {c('?', CYAN, BOLD)} {msg} {c(hint, DIM)}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if not raw:
        return default
    return raw in ("y", "yes")


def choose(msg: str, options: List[Tuple[str, str]], multi: bool = False) -> Any:
    """Display a numbered list and return selected index (or list of indices)."""
    print(f"\n  {c('▶', MAGENTA, BOLD)} {msg}")
    for i, (label, desc) in enumerate(options, 1):
        print(f"    {c(str(i), CYAN, BOLD)}. {c(label, BOLD)}  {c(desc, DIM)}")
    if multi:
        raw = prompt("Enter numbers separated by commas (e.g. 1,3,5)", "1")
        indices: List[int] = []
        for part in raw.split(","):
            try:
                v = int(part.strip()) - 1
                if 0 <= v < len(options):
                    indices.append(v)
            except ValueError:
                pass
        return indices or [0]
    else:
        raw = prompt("Enter number", "1")
        try:
            v = int(raw) - 1
            return max(0, min(v, len(options) - 1))
        except ValueError:
            return 0


# ────────────────────────────────────────────────
#  ASYNC SPINNER WRAPPER
# ────────────────────────────────────────────────
def run_with_spinner(worker_func, *args, label: str = "Processing", **kwargs) -> Any:
    """Execute a blocking function on a background thread with an animated spinner."""
    frames = _spinner_frames()
    idx = 0
    exception: Optional[BaseException] = None
    result = None

    def _target():
        nonlocal result, exception
        try:
            result = worker_func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            exception = e

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_target)
        while not future.done():
            sys.stdout.write(f"\r  {c(frames[idx % len(frames)], CYAN, BOLD)} {label}...")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.1)
        sys.stdout.write("\r" + " " * 72 + "\r")
        sys.stdout.flush()

    if exception:
        raise exception  # type: ignore[misc]
    return result


# ────────────────────────────────────────────────
#  ROBUST AI RESPONSE SANITISATION
# ────────────────────────────────────────────────
def clean_gemini_json(raw_text: str) -> Dict[str, Any]:
    """Extract and parse JSON even when wrapped inside Markdown code fences."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty response received from Gemini API")

    # 1. Try JSON inside a fenced code block first
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
    json_str = match.group(1) if match else raw_text

    # 2. Fallback: locate the outermost JSON object
    if not match:
        obj_match = re.search(r"\{[\s\S]*\}", raw_text)
        if obj_match:
            json_str = obj_match.group(0)

    json_str = json_str.strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Best-effort repair: remove trailing commas
        repaired = re.sub(r",\s*([}\]])", r"\1", json_str)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as final_err:
            raise ValueError(
                f"Could not parse Gemini JSON response: {final_err}\n"
                f"Raw text (first 500 chars): {raw_text[:500]}"
            ) from final_err


# ────────────────────────────────────────────────
#  DATA MODELS
# ────────────────────────────────────────────────
@dataclass
class Clip:
    start: float
    end: float
    title: str = ""
    score: float = 0.0
    hook: str = ""
    tags: List[str] = field(default_factory=list)
    heatmap_peak: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start

    @staticmethod
    def _fmt_time(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def __str__(self) -> str:
        marker = c(" 🔥", RED) if self.heatmap_peak else ""
        return (
            f"[{self._fmt_time(self.start)} → {self._fmt_time(self.end)}] "
            f"{c(self.title or 'Clip', BOLD)}  "
            f"Score: {c(f'{self.score:.1f}/10', YELLOW)}{marker}"
        )


@dataclass
class VideoMeta:
    url: str
    title: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 30.0
    filepath: str = ""
    transcript: str = ""
    heatmap: List[float] = field(default_factory=list)


# ────────────────────────────────────────────────
#  DEPENDENCY CHECK
# ────────────────────────────────────────────────
REQUIRED_BINS: Dict[str, str] = {
    "ffmpeg":  "brew install ffmpeg  /  apt install ffmpeg",
    "ffprobe": "(installed alongside ffmpeg)",
    "yt-dlp":  "pip install yt-dlp",
}
REQUIRED_PKGS: Dict[str, str] = {
    "google.generativeai": "pip install google-generativeai",
}


def check_dependencies() -> bool:
    section("Checking dependencies")
    all_ok = True
    for binary, hint in REQUIRED_BINS.items():
        if shutil.which(binary):
            ok(f"{binary} found")
        else:
            err(f"{binary} not found — {hint}")
            all_ok = False
    for pkg, hint in REQUIRED_PKGS.items():
        try:
            __import__(pkg.split(".")[0])
            ok(f"{pkg} found")
        except ImportError:
            warn(f"{pkg} not installed — {hint}")
            # Not a hard failure; tool still works without AI
    return all_ok


# ────────────────────────────────────────────────
#  CONFIG MANAGEMENT
# ────────────────────────────────────────────────
CONFIG_PATH = Path.home() / ".yt2shorts.json"
_CONFIG_LOCK = threading.Lock()

_DEFAULT_CONFIG: Dict[str, Any] = {
    "gemini_api_keys": [],
    "cookies": {},
    "api_key_usage": {},
    "current_api_key_index": -1,
    "default_api_key_index": 0,
}


def load_config() -> Dict[str, Any]:
    with _CONFIG_LOCK:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                # Merge defaults so new keys are always present
                cfg = {**_DEFAULT_CONFIG, **data}
                return cfg
            except (json.JSONDecodeError, OSError) as e:
                warn(f"Config file corrupt, resetting: {e}")
        return dict(_DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any]) -> None:
    with _CONFIG_LOCK:
        try:
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except OSError as e:
            warn(f"Could not save config: {e}")


def get_api_keys(cfg: Dict[str, Any]) -> List[str]:
    """Return all configured API keys, merging legacy single-key field and env var."""
    keys: List[str] = list(cfg.get("gemini_api_keys", []))

    # Back-compat: migrate old single-key field
    legacy = cfg.get("gemini_api_key", "")
    if legacy and legacy not in keys:
        keys.append(legacy)
        cfg["gemini_api_keys"] = keys
        save_config(cfg)

    # Environment variable takes last-priority slot if not already present
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key and env_key not in keys:
        keys.append(env_key)

    return keys


def get_active_api_key(cfg: Dict[str, Any]) -> Optional[str]:
    keys = get_api_keys(cfg)
    if not keys:
        return None
    idx = cfg.get("default_api_key_index", 0)
    return keys[idx] if 0 <= idx < len(keys) else keys[0]


# ────────────────────────────────────────────────
#  API RATE-LIMITING WITH KEY ROTATION
# ────────────────────────────────────────────────
_RATE_LIMIT_MARKERS = ("429", "QuotaExceeded", "RESOURCE_EXHAUSTED", "quota")
_MODEL_NOT_FOUND_MARKERS = ("404", "not found", "model not found")


def invoke_gemini_with_fallback(
    cfg: Dict[str, Any],
    prompt_payload: str,
    model_name: str,
) -> Tuple[str, str]:
    """
    Call the Gemini API, automatically rotating API keys on quota errors.

    Returns:
        (response_text, api_key_used)
    Raises:
        RuntimeError if every key is exhausted.
        ValueError  if no keys are configured.
    """
    try:
        import google.generativeai as genai  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "google-generativeai is not installed. Run: pip install google-generativeai"
        ) from exc

    keys = get_api_keys(cfg)
    if not keys:
        raise ValueError("No Gemini API keys configured. Add one via the Gemini API menu.")

    start_idx = cfg.get("current_api_key_index", -1)

    for offset in range(len(keys)):
        idx = (start_idx + 1 + offset) % len(keys)
        api_key = keys[idx]

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt_payload,
                generation_config={"temperature": 0.4, "max_output_tokens": 2048},
            )

            # Persist usage stats
            usage = cfg.setdefault("api_key_usage", {})
            usage[api_key] = usage.get(api_key, 0) + 1
            cfg["current_api_key_index"] = idx
            save_config(cfg)

            return response.text, api_key

        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if any(m.lower() in msg for m in _RATE_LIMIT_MARKERS):
                warn(f"API key #{idx + 1} rate-limited — rotating to next key…")
                continue
            if any(m.lower() in msg for m in _MODEL_NOT_FOUND_MARKERS):
                warn(f"Model '{model_name}' unavailable with key #{idx + 1} — skipping…")
                continue
            raise  # Unexpected error — surface it

    raise RuntimeError(
        "All configured Gemini API keys are exhausted or rate-limited. "
        "Please wait or add more keys via the Gemini API menu."
    )


# ────────────────────────────────────────────────
#  COOKIE MANAGEMENT
# ────────────────────────────────────────────────
def manage_cookies(cfg: Dict[str, Any]) -> None:
    section("Cookie Management")
    cookies: Dict[str, str] = cfg.setdefault("cookies", {})

    while True:
        print()
        if cookies:
            info(f"Cookies configured for {len(cookies)} domain(s):")
            for domain, cookie_file in cookies.items():
                status = c("✓", GREEN) if Path(cookie_file).exists() else c("missing", RED)
                print(f"  {c('•', CYAN)} {domain}: {c(cookie_file, DIM)}  [{status}]")
        else:
            warn("No cookies configured")

        options = [
            ("Import cookies (JSON format)", "Import from a Netscape JSON cookie file"),
            ("Remove cookies", "Remove cookies for a specific domain"),
            ("Return to main menu", "Go back"),
        ]
        idx = choose("Manage cookies", options)

        if idx == 0:
            domain = prompt("YouTube domain", "youtube.com")
            cookie_path_str = prompt("Path to JSON cookie file")
            if not cookie_path_str:
                warn("No path entered.")
                continue
            cookie_path = Path(cookie_path_str).expanduser()
            if not cookie_path.exists():
                err(f"File not found: {cookie_path}")
                continue
            try:
                data = json.loads(cookie_path.read_text(encoding="utf-8"))
                if not (isinstance(data, list) and data and "name" in data[0]):
                    warn("Invalid cookie format. Expected a JSON array of cookie objects with a 'name' field.")
                    continue
                cookies[domain] = str(cookie_path)
                cfg["cookies"] = cookies
                save_config(cfg)
                ok(f"Cookies imported for {domain} ({len(data)} cookies)")
            except json.JSONDecodeError as e:
                err(f"JSON parse error: {e}")
            except OSError as e:
                err(f"Could not read file: {e}")

        elif idx == 1:
            if not cookies:
                warn("No cookies to remove.")
                continue
            domains = list(cookies.keys())
            rm_idx = choose(
                "Select domain to remove cookies for",
                [(d, cookies[d]) for d in domains],
            )
            removed = domains[rm_idx]
            del cookies[removed]
            cfg["cookies"] = cookies
            save_config(cfg)
            ok(f"Removed cookies for {removed}")

        else:
            break


def get_cookie_args(cfg: Dict[str, Any]) -> List[str]:
    """Return yt-dlp --cookies argument if a valid cookie file is configured."""
    for cookie_path in cfg.get("cookies", {}).values():
        if Path(cookie_path).exists():
            return ["--cookies", cookie_path]
    return []


# ────────────────────────────────────────────────
#  API KEY MANAGEMENT
# ────────────────────────────────────────────────
def manage_api_keys(cfg: Dict[str, Any]) -> None:
    section("Gemini API Key Management")

    while True:
        keys = get_api_keys(cfg)
        print()
        if keys:
            info(f"Configured API keys ({len(keys)}):")
            default_idx = cfg.get("default_api_key_index", 0)
            for i, key in enumerate(keys):
                masked = (key[:8] + "…" + key[-4:]) if len(key) > 12 else "***"
                usage = cfg.get("api_key_usage", {}).get(key, 0)
                marker = c(" ← default", GREEN) if i == default_idx else ""
                print(f"  {c(str(i + 1), CYAN, BOLD)}. {masked}  {c(f'used {usage}×', DIM)}{marker}")
        else:
            warn("No API keys configured")

        options = [("Add new API key", "Paste a Gemini API key")]
        if keys:
            options.append(("Remove API key", "Delete an existing key"))
            options.append(("Set default key", "Choose which key to use first"))
        options.append(("Return to main menu", "Go back"))

        idx = choose("Manage API keys", options)

        if idx == 0:
            key = prompt("Paste your Gemini API key").strip()
            current_keys = get_api_keys(cfg)
            if not key:
                warn("No key entered.")
            elif key in current_keys:
                warn("This key is already configured.")
            else:
                cfg.setdefault("gemini_api_keys", []).append(key)
                save_config(cfg)
                ok("API key added successfully.")

        elif idx == 1 and keys:
            if len(keys) == 1:
                warn("Cannot remove the only API key.")
            else:
                rm_idx = choose(
                    "Select key to remove",
                    [(f"Key {i + 1}", k[:8] + "…") for i, k in enumerate(keys)],
                )
                removed = keys.pop(rm_idx)
                cfg["gemini_api_keys"] = keys
                if cfg.get("default_api_key_index", 0) >= len(keys):
                    cfg["default_api_key_index"] = 0
                save_config(cfg)
                ok(f"Removed key ending in …{removed[-4:]}")

        elif idx == 2 and keys:
            def_idx = choose(
                "Select default API key",
                [(f"Key {i + 1}", k[:8] + "…") for i, k in enumerate(keys)],
            )
            cfg["default_api_key_index"] = def_idx
            save_config(cfg)
            ok(f"Default key set to: {keys[def_idx][:8]}…")

        else:
            break


# ────────────────────────────────────────────────
#  YT-DLP HELPERS
# ────────────────────────────────────────────────
_YT_DLP_BASE_ARGS = [
    "--no-playlist",
    "--merge-output-format", "mp4",
    "--user-agent",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "--sleep-interval", "2",
    "--max-sleep-interval", "5",
    "--retries", "10",
    "--fragment-retries", "10",
    "--retry-sleep", "5",
    "--no-check-certificate",
    "--extractor-retries", "5",
    "--force-ipv4",
    "--add-header", "Accept-Language:en-US,en;q=0.9",
    "--add-header", "Sec-Fetch-Mode:navigate",
]


def build_ytdlp_args(cfg: Dict[str, Any], extra_args: Optional[List[str]] = None) -> List[str]:
    args = list(_YT_DLP_BASE_ARGS)
    args.extend(get_cookie_args(cfg))
    if extra_args:
        args.extend(extra_args)
    return args


def _run(
    cmd: List[str],
    capture: bool = False,
    timeout: int = 600,
) -> Tuple[int, str]:
    """Run a subprocess and return (returncode, combined_output)."""
    try:
        if capture:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return result.returncode, result.stdout + result.stderr
        else:
            result = subprocess.run(cmd, timeout=timeout)
            return result.returncode, ""
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT: process exceeded time limit"
    except FileNotFoundError as exc:
        return -1, f"Command not found: {exc}"


# ────────────────────────────────────────────────
#  VIDEO METADATA EXTRACTION
# ────────────────────────────────────────────────
def fetch_video_info(url: str, cfg: Dict[str, Any]) -> Optional[VideoMeta]:
    section("Fetching video metadata")
    info("Querying YouTube (this may take a moment)…")

    # Build command — note: avoid duplicating --extractor-retries from base args
    cmd = ["yt-dlp", "--dump-json"] + build_ytdlp_args(cfg) + [url]

    code, out = run_with_spinner(
        lambda: _run(cmd, capture=True, timeout=60),
        label="Querying video metadata",
    )

    if code != 0 or not out.strip():
        warn("Standard fetch failed. Retrying with browser cookie extraction…")
        fallback_cmd = [
            "yt-dlp", "--dump-json", "--no-playlist",
            "--cookies-from-browser", "chrome", "--force-ipv4", url,
        ]
        code, out = run_with_spinner(
            lambda: _run(fallback_cmd, capture=True, timeout=60),
            label="Retrying with browser cookies",
        )

    if code != 0 or not out.strip():
        err("Failed to fetch video metadata. Check your URL or internet connection.")
        return None

    try:
        # yt-dlp may print one JSON object per line; use the first non-empty one
        first_line = next((ln for ln in out.splitlines() if ln.strip().startswith("{")), None)
        if not first_line:
            err("No JSON found in yt-dlp output.")
            return None

        data = json.loads(first_line)
        meta = VideoMeta(url=url)
        meta.title = data.get("title", "Unknown Title")
        meta.duration = float(data.get("duration") or 0.0)

        ok(f"Title    : {c(meta.title, BOLD)}")
        ok(f"Duration : {c(_fmt_dur(meta.duration), BOLD)}")

        # Parse YouTube crowdsourced heatmap
        hm_raw: List[Dict] = data.get("heatmap") or []
        if hm_raw:
            dur_s = int(meta.duration) + 1
            meta.heatmap = [0.0] * dur_s
            for seg in hm_raw:
                s = int(float(seg.get("start_time", 0.0)))
                e = int(float(seg.get("end_time", s + 1)))
                v = float(seg.get("value", 0.0))
                for t in range(s, min(e, dur_s)):
                    meta.heatmap[t] = max(meta.heatmap[t], v)
            ok(f"Heatmap  : {c(f'{len(hm_raw)} engagement windows mapped', GREEN)}")

        return meta

    except (json.JSONDecodeError, StopIteration, ValueError) as exc:
        err(f"Failed to parse metadata: {exc}")
        return None


def download_video(
    meta: VideoMeta,
    output_dir: str,
    quality: str = "1080",
    cfg: Optional[Dict[str, Any]] = None,
) -> bool:
    section("Downloading video")
    cfg = cfg or {}

    fmt = (
        f"bestvideo[ext=mp4][height<={quality}]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={quality}]+bestaudio/best[ext=mp4]/best"
    )
    out_tmpl = str(Path(output_dir) / "%(title)s.%(ext)s")

    cmd = ["yt-dlp"] + build_ytdlp_args(cfg, ["--format", fmt, "--output", out_tmpl, meta.url])
    info(f"Downloading (quality ≤ {quality}p)…")

    try:
        code, _ = run_with_spinner(
            lambda: _run(cmd, timeout=3600),
            label="Downloading video",
        )
    except Exception as exc:  # noqa: BLE001
        err(f"Download error: {exc}")
        return False

    if code != 0:
        warn("Primary download failed. Retrying with minimal flags…")
        fallback_cmd = [
            "yt-dlp", "--no-playlist", "--force-ipv4", "--no-check-certificate",
            "--retries", "10",
            "--user-agent",
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "--output", out_tmpl,
            meta.url,
        ]
        code, _ = _run(fallback_cmd, timeout=3600)

    if code != 0:
        err("Download failed after all retries. Check your URL or network connection.")
        return False

    # Locate the downloaded file
    video_exts = {".mp4", ".mkv", ".webm", ".mov"}
    for f in Path(output_dir).iterdir():
        if f.suffix.lower() in video_exts:
            meta.filepath = str(f)
            ok(f"Saved to: {c(meta.filepath, CYAN)}")
            return True

    err("Download appeared to succeed, but no video file was found in the output directory.")
    return False


def download_section(
    meta: VideoMeta,
    start: float,
    end: float,
    output_dir: str,
    quality: str = "1080",
    cfg: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Download only a specific time range from the video using yt-dlp --download-sections."""
    cfg = cfg or {}

    fmt = (
        f"bestvideo[ext=mp4][height<={quality}]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={quality}]+bestaudio/best[ext=mp4]/best"
    )

    # yt-dlp --download-sections format: "*START-END"
    start_h = int(start // 3600)
    start_m = int((start % 3600) // 60)
    start_s = int(start % 60)
    end_h = int(end // 3600)
    end_m = int((end % 3600) // 60)
    end_s = int(end % 60)
    section_str = f"*{start_h:02d}:{start_m:02d}:{start_s:02d}-{end_h:02d}:{end_m:02d}:{end_s:02d}"

    # Use a unique filename per section
    safe_name = re.sub(r"[^\w\-. ]", "_", meta.title)[:40]
    out_tmpl = str(Path(output_dir) / f"{safe_name}_{start:.0f}-{end:.0f}.%(ext)s")

    cmd = ["yt-dlp"] + build_ytdlp_args(cfg, [
        "--format", fmt,
        "--download-sections", section_str,
        "--force-keyframes-at-cuts",
        "--output", out_tmpl,
        meta.url,
    ])

    code, output = _run(cmd, capture=True, timeout=600)
    if code != 0:
        warn(f"Section download failed for {section_str}: {output[-200:]}")
        return None

    # Locate the downloaded file
    video_exts = {".mp4", ".mkv", ".webm", ".mov"}
    for f in Path(output_dir).iterdir():
        if f.suffix.lower() in video_exts and f"{start:.0f}-{end:.0f}" in f.name:
            return str(f)

    # Fallback: find any video file that wasn't there before
    for f in Path(output_dir).iterdir():
        if f.suffix.lower() in video_exts:
            return str(f)

    return None


def probe_video(meta: VideoMeta) -> bool:
    """Populate meta.width, meta.height and meta.fps using ffprobe."""
    if not meta.filepath:
        return False
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", meta.filepath]
    code, out = _run(cmd, capture=True)
    if code != 0:
        warn("ffprobe failed; using default resolution values.")
        return False
    try:
        data = json.loads(out)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                meta.width = int(stream.get("width", meta.width or 0))
                meta.height = int(stream.get("height", meta.height or 0))
                fps_str = stream.get("r_frame_rate", "30/1")
                num, den = (fps_str + "/1").split("/")[:2]
                meta.fps = float(num) / max(float(den), 1.0)
                ok(f"Video: {meta.width}×{meta.height} @ {meta.fps:.2f} fps")
                break
    except (json.JSONDecodeError, ValueError, ZeroDivisionError) as exc:
        warn(f"Could not parse ffprobe output: {exc}")
        return False
    return True


# ────────────────────────────────────────────────
#  TRANSCRIPT EXTRACTION
# ────────────────────────────────────────────────
def extract_transcript(meta: VideoMeta, cfg: Dict[str, Any]) -> str:
    section("Extracting transcript / captions")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "yt-dlp", "--skip-download",
            "--write-auto-sub", "--write-sub",
            "--sub-lang", "en", "--sub-format", "vtt",
            "--no-playlist", "--force-ipv4", "--no-check-certificate",
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "--output", str(Path(tmp) / "sub"),
            meta.url,
        ]
        cmd.extend(get_cookie_args(cfg))

        try:
            run_with_spinner(
                lambda: _run(cmd, capture=True, timeout=120),
                label="Extracting captions",
            )
        except Exception as exc:  # noqa: BLE001
            warn(f"Caption extraction error: {exc}")
            return ""

        vtt_files = sorted(Path(tmp).glob("*.vtt"))
        if not vtt_files:
            warn("No captions found for this video.")
            return ""

        # Prefer manually created subtitles (shorter filename) over auto-generated
        vtt_path = vtt_files[0]
        raw = vtt_path.read_text(encoding="utf-8", errors="replace")
        text = _parse_vtt(raw)
        ok(f"Transcript: {len(text.split())} words extracted")
        return text


def _parse_vtt(raw: str) -> str:
    """Parse WebVTT subtitle data into a timestamped plain-text transcript."""
    lines: List[str] = []
    current_time = ""
    current_text: List[str] = []
    seen: set = set()

    for line in raw.splitlines():
        line = line.strip()
        if "-->" in line:
            # Flush previous cue
            if current_text and current_time:
                ts = _vtt_time_to_sec(current_time)
                lines.append(f"[{ts:.1f}] {' '.join(current_text)}")
            current_time = line.split("-->")[0].strip()
            current_text = []
        elif line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        elif line and not line.isdigit():
            # Strip HTML tags and HTML entities
            clean = re.sub(r"<[^>]+>", "", line).strip()
            clean = re.sub(r"&amp;", "&", clean)
            clean = re.sub(r"&lt;", "<", clean)
            clean = re.sub(r"&gt;", ">", clean)
            clean = re.sub(r"&nbsp;", " ", clean)
            clean = " ".join(clean.split())  # Normalise whitespace
            if clean and clean not in seen:
                current_text.append(clean)
                seen.add(clean)
        elif not line and current_text and current_time:
            ts = _vtt_time_to_sec(current_time)
            lines.append(f"[{ts:.1f}] {' '.join(current_text)}")
            current_text = []

    # Flush any trailing cue
    if current_text and current_time:
        ts = _vtt_time_to_sec(current_time)
        lines.append(f"[{ts:.1f}] {' '.join(current_text)}")

    return "\n".join(lines)


def _vtt_time_to_sec(ts: str) -> float:
    """Convert a VTT timestamp (HH:MM:SS.mmm or MM:SS.mmm) to seconds."""
    ts = ts.split(".")[0].strip()  # Drop milliseconds
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return 0.0


def _fmt_dur(secs: float) -> str:
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"


# ────────────────────────────────────────────────
#  CINEMATIC 9:16 SMART CROP (FFmpeg)
# ────────────────────────────────────────────────
def process_cinematic_short(meta: VideoMeta, clip: Clip, out_dir: Path) -> Optional[Path]:
    """
    Render a 9:16 Short from a horizontal source video.

    Strategy:
      - Split the video into two streams.
      - Blur + crop the background layer to full 1080×1920.
      - Scale the foreground layer to fit width (1080px), preserving aspect ratio.
      - Overlay foreground centred on the blurred background.
    """
    safe_title = re.sub(r"[^\w\-. ]", "_", clip.title or "clip")[:50].strip()
    out_path = out_dir / f"Short_{int(clip.start)}_{safe_title}.mp4"

    filter_graph = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=25:15[bg_blurred];"
        "[fg]scale=1080:-2[fg_scaled];"  # -2 ensures height divisible by 2 (required by libx264)
        "[bg_blurred][fg_scaled]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2[out_v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{clip.start:.3f}",
        "-t",  f"{clip.duration:.3f}",
        "-i",  meta.filepath,
        "-filter_complex", filter_graph,
        "-map", "[out_v]",
        "-map", "0:a?",          # "?" makes audio optional (silent video won't fail)
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",   # Maximum compatibility (required for iOS/TikTok)
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",  # Enables streaming before full download
        str(out_path),
    ]

    code, output = _run(cmd, capture=True)
    if code == 0:
        size_mb = out_path.stat().st_size / 1_048_576
        ok(f"Rendered: {out_path.name} ({size_mb:.1f} MB)")
        return out_path

    err(f"FFmpeg failed:\n{output[-400:]}")
    return None


def process_clip_from_segment(
    segment_path: str,
    clip: Clip,
    out_dir: Path,
) -> Optional[Path]:
    """
    Render a 9:16 Short from an already-downloaded segment file.
    The segment is already clipped to the right time range, so we just apply the cinematic crop.
    """
    safe_title = re.sub(r"[^\w\-. ]", "_", clip.title or "clip")[:50].strip()
    out_path = out_dir / f"Short_{safe_title}.mp4"

    filter_graph = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=25:15[bg_blurred];"
        "[fg]scale=1080:-2[fg_scaled];"
        "[bg_blurred][fg_scaled]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2[out_v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", segment_path,
        "-filter_complex", filter_graph,
        "-map", "[out_v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    code, output = _run(cmd, capture=True)
    if code == 0:
        size_mb = out_path.stat().st_size / 1_048_576
        ok(f"Rendered: {out_path.name} ({size_mb:.1f} MB)")
        return out_path

    err(f"FFmpeg failed:\n{output[-400:]}")
    return None


# ────────────────────────────────────────────────
#  AI VIRALITY ANALYSIS (Gemini)
# ────────────────────────────────────────────────
GEMINI_MODELS = [
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

_AI_PROMPT_TEMPLATE = """
You are an expert short-form video producer specialising in viral YouTube Shorts, TikToks, and Instagram Reels.

Below is a time-stamped transcript from a YouTube video. Identify the **top 5 clips** that would perform best as standalone Short-form content.

REQUIREMENTS FOR EACH CLIP:
- Duration MUST be between 15 and 59 seconds (end_time - start_time)
- Must be a self-contained moment — viewers should understand it without prior context
- Should have a strong hook in the first 3 seconds
- Prioritise: emotional peaks, surprising facts, how-tos, jokes, or strong opinions

Respond with ONLY valid JSON — no preamble, no markdown code fences, no trailing text:

{{
  "clips": [
    {{
      "start": 12.5,
      "end": 52.0,
      "title": "Short, punchy title for YouTube Shorts",
      "score": 9.2,
      "hook": "One-sentence hook (the first thing viewers hear/see)",
      "tags": ["tag1", "tag2", "tag3"]
    }}
  ]
}}

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"
""".strip()


def analyze_viral_moments(meta: VideoMeta, cfg: Dict[str, Any]) -> List[Clip]:
    """Use Gemini AI to identify the most viral-worthy moments in the transcript."""
    section("AI Virality Analysis")

    if not meta.transcript:
        warn("No transcript available. Falling back to evenly-spaced time windows.")
        return _generate_fallback_clips(meta)

    # Trim transcript to avoid exceeding token limits (~8 000 chars ≈ 2 000 tokens)
    transcript_excerpt = meta.transcript[:8000]
    prompt_text = _AI_PROMPT_TEMPLATE.format(transcript=transcript_excerpt)

    for model_name in GEMINI_MODELS:
        try:
            info(f"Querying {c(model_name, CYAN)}…")
            response_text, used_key = run_with_spinner(
                invoke_gemini_with_fallback,
                cfg, prompt_text, model_name,
                label=f"Waiting for {model_name}",
            )

            parsed = clean_gemini_json(response_text)
            clips = _parse_ai_clips(parsed, meta)

            if clips:
                ok(f"AI returned {len(clips)} clip(s) via {model_name}")
                return sorted(clips, key=lambda x: x.score, reverse=True)

            warn(f"{model_name} returned no usable clips — trying next model.")

        except Exception as exc:  # noqa: BLE001
            warn(f"{model_name} failed: {str(exc)[:120]}")
            continue

    err("AI analysis failed for all models.")
    warn("Falling back to evenly-spaced time windows.")
    return _generate_fallback_clips(meta)


def _parse_ai_clips(data: Dict[str, Any], meta: VideoMeta) -> List[Clip]:
    """Convert raw AI JSON into validated Clip objects."""
    clips: List[Clip] = []
    for item in data.get("clips", []):
        try:
            start = float(item["start"])
            end   = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue

        # Clamp to video length
        start = max(0.0, start)
        end   = min(end, meta.duration)

        duration = end - start
        if not (15.0 <= duration <= 60.0):
            # Attempt to salvage by trimming
            if duration > 60.0:
                end = start + 60.0
            elif duration < 15.0:
                continue  # Too short to be useful

        clip = Clip(
            start=start,
            end=end,
            title=str(item.get("title", "Untitled Clip")),
            score=min(float(item.get("score", 5.0)), 10.0),
            hook=str(item.get("hook", "")),
            tags=[str(t) for t in item.get("tags", [])],
        )

        # Boost score if this segment overlaps a heatmap peak
        if meta.heatmap:
            seg = meta.heatmap[int(start): min(int(end), len(meta.heatmap))]
            if seg and max(seg) > 0.75:
                clip.heatmap_peak = True
                clip.score = min(clip.score + 1.0, 10.0)

        clips.append(clip)

    return clips


def _generate_fallback_clips(meta: VideoMeta, num: int = 5, window: int = 30) -> List[Clip]:
    """Return evenly-spaced clips when no transcript or AI is available."""
    total = int(meta.duration)
    step = max(window, total // max(num, 1))
    clips = []
    for i, start in enumerate(range(0, min(total, step * num), step)):
        end = min(start + window, meta.duration)
        if end - start >= 15:
            clips.append(Clip(start=float(start), end=float(end), title=f"Segment {i + 1}", score=5.0))
    return clips


# ────────────────────────────────────────────────
#  HEATMAP ANALYSIS (Local fallback)
# ────────────────────────────────────────────────
def heatmap_peaks(
    heatmap: List[float],
    window: int = 60,
    min_duration: int = 30,
    max_duration: int = 90,
    top_k: int = 10,
) -> List[Clip]:
    """Identify high-engagement windows from YouTube's crowdsourced heatmap data."""
    if not heatmap:
        return []

    n = len(heatmap)
    half = window // 2

    # Smooth with a sliding mean
    smoothed = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        smoothed.append(sum(heatmap[lo:hi]) / (hi - lo))

    peak_val = max(smoothed) or 1.0
    smoothed = [v / peak_val for v in smoothed]

    threshold = 0.6
    in_peak = False
    peak_start = 0
    peak_score = 0.0
    candidates: List[Clip] = []

    for i, v in enumerate(smoothed):
        if v >= threshold:
            if not in_peak:
                in_peak = True
                peak_start = i
                peak_score = v
            else:
                peak_score = max(peak_score, v)
        else:
            if in_peak:
                in_peak = False
                peak_end = i
                dur = peak_end - peak_start
                if dur >= min_duration:
                    # Centre the clip on the maximum point within the peak
                    local = smoothed[peak_start:peak_end]
                    peak_idx = peak_start + local.index(max(local))
                    half_clip = min(max_duration // 2, dur // 2)
                    cs = max(0, peak_idx - half_clip)
                    ce = min(n - 1, peak_idx + half_clip)
                    ce = max(ce, cs + min_duration)
                    ce = min(ce, cs + max_duration)
                    candidates.append(Clip(
                        start=float(cs),
                        end=float(ce),
                        score=round(peak_score * 10, 2),
                        heatmap_peak=True,
                        title=f"Peak @ {_fmt_dur(float(peak_idx))}",
                    ))

    candidates.sort(key=lambda x: x.score, reverse=True)

    # De-duplicate overlapping clips
    deduped: List[Clip] = []
    for cand in candidates:
        overlap = any(
            not (cand.end <= kept.start or cand.start >= kept.end)
            for kept in deduped
        )
        if not overlap:
            deduped.append(cand)
        if len(deduped) >= top_k:
            break

    return deduped


# ────────────────────────────────────────────────
#  MAIN SHORTS PIPELINE
# ────────────────────────────────────────────────
def run_shorts_pipeline(args: argparse.Namespace, cfg: Dict[str, Any]) -> None:
    """End-to-end pipeline: metadata → analyse → download segments → render."""

    # ── Gather inputs ──────────────────────────────────────────
    url = args.url or prompt("YouTube video URL")
    if not url:
        warn("No URL provided.")
        return

    # Normalise youtu.be short links
    if "youtu.be/" in url:
        vid = url.split("youtu.be/")[-1].split("?")[0]
        url = f"https://www.youtube.com/watch?v={vid}"

    default_out = str(Path.home() / "yt2shorts_output")
    out_dir_str = args.output or cfg.get("output_dir") or prompt("Output directory", default_out)
    out_dir = Path(out_dir_str).expanduser()

    num_clips = args.clips or int(prompt("How many Shorts to generate?", "5"))
    max_dur   = args.max_dur or int(prompt("Max clip duration (seconds)?", "60"))
    quality   = args.quality or prompt("Download quality (720/1080/1440/best)", "1080")

    # ── Step 1: Fetch metadata (no download yet) ───────────────
    meta = fetch_video_info(url, cfg)
    if not meta:
        err("Cannot proceed without video metadata.")
        return

    if meta.duration < 60:
        warn(f"Video is only {_fmt_dur(meta.duration)} long — it may already be short-form.")
        if not confirm("Continue anyway?"):
            return

    # ── Step 2: Extract transcript ─────────────────────────────
    if not args.skip_transcript:
        meta.transcript = extract_transcript(meta, cfg)

    # ── Step 3: Analyse — heatmap + AI (before any download) ───
    heatmap_clips: List[Clip] = []
    if meta.heatmap:
        section("Heatmap Analysis")
        heatmap_clips = heatmap_peaks(
            meta.heatmap,
            window=90,
            min_duration=max(15, max_dur // 4),
            max_duration=max_dur,
            top_k=num_clips * 2,
        )
        ok(f"Found {len(heatmap_clips)} high-engagement window(s) from heatmap")

    api_keys = get_api_keys(cfg)
    if api_keys:
        discovered_clips = analyze_viral_moments(meta, cfg)
    else:
        warn("No Gemini API keys configured — using heatmap-only detection.")
        discovered_clips = heatmap_clips[:num_clips]

    # Merge heatmap clips as bonus candidates if AI found fewer than requested
    if heatmap_clips and len(discovered_clips) < num_clips:
        existing_starts = {c.start for c in discovered_clips}
        for hc in heatmap_clips:
            if hc.start not in existing_starts:
                discovered_clips.append(hc)

    if not discovered_clips:
        err("No viable clips could be identified. Try a different video or check your API key.")
        return

    discovered_clips.sort(key=lambda clip: clip.score, reverse=True)

    # ── Step 4: Clip selection ─────────────────────────────────
    if len(discovered_clips) > 1 and not args.auto:
        selected = _interactive_clip_review(discovered_clips, meta)
    else:
        selected = discovered_clips[:num_clips]

    if not selected:
        warn("No clips selected for export.")
        return

    # ── Step 5: Download only selected segments ────────────────
    section("Downloading Selected Segments")
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: List[Path] = []

    for i, clip in enumerate(selected, 1):
        info(f"[{i}/{len(selected)}] {clip.title}  ({_fmt_dur(clip.start)} → {_fmt_dur(clip.end)})")

        with tempfile.TemporaryDirectory() as seg_dir:
            segment_file = run_with_spinner(
                download_section,
                meta, clip.start, clip.end, seg_dir, quality, cfg,
                label=f"Downloading segment {i}/{len(selected)}",
            )

            if not segment_file:
                err(f"Failed to download segment {i}: {clip.title}")
                continue

            # ── Step 6: Render cinematic 9:16 short ────────────
            output_file = run_with_spinner(
                process_clip_from_segment,
                segment_file, clip, out_dir,
                label=f"Encoding clip {i}/{len(selected)}",
            )

            if output_file:
                rendered.append(output_file)
                if clip.hook:
                    print(f"    {c('Hook:', MAGENTA, BOLD)} {clip.hook}")
                if clip.tags:
                    tags_str = " ".join(f"#{t}" for t in clip.tags)
                    print(f"    {c('Tags:', DIM)} {tags_str}")
            else:
                err(f"Failed to render clip {i}: {clip.title}")

    # ── Summary ────────────────────────────────────────────────
    if rendered:
        _write_manifest(selected, rendered, meta, out_dir)
        section("Done!")
        ok(f"{len(rendered)} short(s) exported → {c(str(out_dir), CYAN, BOLD)}")
    else:
        err("No clips were rendered successfully.")


def _interactive_clip_review(clips: List[Clip], meta: VideoMeta) -> List[Clip]:
    section("Clip Review & Selection")
    info(f"{len(clips)} candidate clip(s) found:")

    for i, clip in enumerate(clips, 1):
        hp = c(" ★ HEATMAP PEAK", RED, BOLD) if clip.heatmap_peak else ""
        print(f"\n  {c(str(i), CYAN, BOLD)}.  {clip}{hp}")
        if clip.hook:
            print(f"      {c('Hook:', DIM)} {clip.hook}")
        if clip.tags:
            print(f"      {c('Tags:', DIM)} #{' #'.join(clip.tags)}")

    indices = choose(
        "Select clips to export",
        [
            (f"Clip {i}", f"{cl.title} ({_fmt_dur(cl.duration)}, score {cl.score:.1f}/10)")
            for i, cl in enumerate(clips, 1)
        ],
        multi=True,
    )
    # Guard against out-of-bounds indices
    selected = [clips[i] for i in indices if i < len(clips)]
    if not selected:
        selected = clips[:1]
    ok(f"{len(selected)} clip(s) selected for export.")
    return selected


def _write_manifest(
    clips: List[Clip],
    exported: List[Path],
    meta: VideoMeta,
    out_dir: Path,
) -> None:
    records = [
        {
            "file":          path.name,
            "title":         clip.title,
            "start_sec":     clip.start,
            "end_sec":       clip.end,
            "duration_sec":  round(clip.duration, 2),
            "virality_score": clip.score,
            "hook":          clip.hook,
            "tags":          clip.tags,
            "heatmap_peak":  clip.heatmap_peak,
        }
        for clip, path in zip(clips, exported)
    ]
    manifest = {
        "source_title":    meta.title,
        "source_url":      meta.url,
        "source_duration": meta.duration,
        "clips":           records,
        "exported_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator":       "yt2shorts",
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    ok(f"Manifest → {c(str(manifest_path), CYAN)}")


# ────────────────────────────────────────────────
#  MAIN INTERACTIVE LOOP
# ────────────────────────────────────────────────
def main_interactive(args: argparse.Namespace) -> None:
    banner()
    cfg = load_config()

    if not check_dependencies():
        if not confirm("Some required tools are missing. Continue anyway?", default=False):
            sys.exit(1)

    while True:
        try:
            choice = show_menu()
            if choice == "1":
                run_shorts_pipeline(args, cfg)
                input(f"\n  {c('Press Enter to return to menu…', DIM)}")
            elif choice == "2":
                manage_cookies(cfg)
            elif choice == "3":
                manage_api_keys(cfg)
            elif choice == "4":
                ok("Goodbye! Happy rendering 🎬")
                break
            else:
                warn("Invalid selection. Please choose 1–4.")
        except KeyboardInterrupt:
            print()
            ok("Session interrupted. Goodbye!")
            break
        except Exception as exc:  # noqa: BLE001
            err(f"Unexpected error: {exc}")
            if os.environ.get("YT2SHORTS_DEBUG"):
                traceback.print_exc()
            else:
                info("Set YT2SHORTS_DEBUG=1 for a full traceback.")


# ────────────────────────────────────────────────
#  CLI ARGUMENT PARSER
# ────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yt2shorts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""
        ┌─────────────────────────────────────────────────────────┐
        │  yt2shorts — YouTube Long-Form to Shorts Converter      │
        │  Local processing + Gemini AI viral detection           │
        └─────────────────────────────────────────────────────────┘

        Examples:
          python yt2shorts.py
          python yt2shorts.py --url "https://youtu.be/dQw4w9WgXcQ"
          python yt2shorts.py --url URL --clips 3 --max-dur 45 --auto
          python yt2shorts.py --file /path/to/video.mp4 --clips 5
          python yt2shorts.py --check
        """),
    )
    p.add_argument("--url",          metavar="URL",  help="YouTube video URL to convert")
    p.add_argument("--file",         metavar="FILE", help="Use a local video file instead of downloading")
    p.add_argument("--output", "-o", metavar="DIR",  help="Output directory (default: ~/yt2shorts_output)")
    p.add_argument("--clips",  "-n", metavar="N",    type=int, help="Number of Shorts to generate (default: 5)")
    p.add_argument("--max-dur", "-d", metavar="SECS", type=int, dest="max_dur",
                   help="Maximum clip duration in seconds (default: 60)")
    p.add_argument("--quality", "-q", metavar="P",   help="Download quality: 720/1080/1440/best (default: 1080)")
    p.add_argument("--auto",         action="store_true", help="Non-interactive mode; use defaults for all prompts")
    p.add_argument("--skip-transcript", action="store_true", help="Skip caption/transcript extraction")
    p.add_argument("--check",        action="store_true", help="Check dependencies only, then exit")
    return p


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    if args.check:
        banner()
        sys.exit(0 if check_dependencies() else 1)

    try:
        main_interactive(args)
    except KeyboardInterrupt:
        print()
        warn("Interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        print()
        err(f"Fatal error: {exc}")
        if os.environ.get("YT2SHORTS_DEBUG"):
            traceback.print_exc()
        else:
            info("Set YT2SHORTS_DEBUG=1 for a full traceback.")
        sys.exit(1)
