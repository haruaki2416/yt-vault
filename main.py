import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

app = FastAPI(title="YT Vault", docs_url=None, redoc_url=None)
BASE_DIR = Path(__file__).parent
MAX_UPLOAD_BYTES = int(float(os.getenv("MAX_UPLOAD_GB", "12")) * 1024**3)
CHUNK_SIZE = 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".webm"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}


def safe_name(value: str) -> str:
    value = Path(value or "video").name
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return value[:120] or "video"


def remove_dir(path: str):
    shutil.rmtree(path, ignore_errors=True)


async def save_upload(upload: UploadFile, destination: Path):
    total = 0
    with destination.open("wb") as output:
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"Upload exceeds the configured {MAX_UPLOAD_BYTES / 1024**3:.1f} GB limit.")
            output.write(chunk)
    if total == 0:
        raise HTTPException(400, "The uploaded file is empty.")
    return total


def run(command: list[str], timeout: int = 8 * 60 * 60):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Processing timed out. Try a smaller source file or a larger worker.")
    if result.returncode != 0:
        detail = (result.stderr or "FFmpeg could not process these files.")[-1800:]
        raise HTTPException(422, detail)
    return result


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"status": "ok", "ffmpeg": shutil.which("ffmpeg") is not None}


@app.post("/api/mux")
async def mux(video: UploadFile = File(...), subtitles: UploadFile = File(...)):
    video_name = safe_name(video.filename or "video.mp4")
    subtitle_name = safe_name(subtitles.filename or "subtitles.srt")
    video_ext = Path(video_name).suffix.lower()
    subtitle_ext = Path(subtitle_name).suffix.lower()

    if video_ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "Choose a supported video file: MP4, M4V, MOV, MKV or WebM.")
    if subtitle_ext not in SUBTITLE_EXTENSIONS:
        raise HTTPException(400, "Choose an SRT or WebVTT subtitle file.")

    workdir = Path(tempfile.mkdtemp(prefix="ytvault-"))
    input_video = workdir / f"source{video_ext}"
    input_subs = workdir / f"captions{subtitle_ext}"
    output = workdir / "YT-Vault-with-subtitles.mp4"

    try:
        await save_upload(video, input_video)
        await save_upload(subtitles, input_subs)

        probe = run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
            str(input_video)
        ], timeout=120)
        if not probe.stdout.strip():
            raise HTTPException(422, "The uploaded file does not contain a readable video stream.")

        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(input_video), "-i", str(input_subs),
            "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
            "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=und",
            "-disposition:s:0", "default", "-movflags", "+faststart",
            str(output)
        ]
        try:
            run(command)
        except HTTPException as first_error:
            # Some audio codecs (for example Opus) cannot be copied into MP4.
            # Retry by converting audio only; the video stream remains untouched.
            if "FFmpeg" in str(first_error.detail) or first_error.status_code == 422:
                retry = command.copy()
                retry[retry.index("-c:a") + 1] = "aac"
                retry[retry.index("-c:a") + 2] = "192k"
                run(retry)
            else:
                raise

        if not output.exists() or output.stat().st_size == 0:
            raise HTTPException(500, "The MP4 output was not created.")
        return FileResponse(
            output,
            media_type="video/mp4",
            filename=f"{Path(video_name).stem}-with-subtitles.mp4",
            background=BackgroundTask(remove_dir, str(workdir)),
        )
    except Exception:
        remove_dir(str(workdir))
        raise
    finally:
        await video.close()
        await subtitles.close()
