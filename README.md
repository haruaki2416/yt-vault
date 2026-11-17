# YT Vault

A small web app for packaging a video and a subtitle file into one MP4 with selectable embedded captions.

## What it does

- Accepts video files in MP4, M4V, MOV, MKV, and WebM formats.
- Accepts SRT and WebVTT subtitle files.
- Uses FFmpeg to mux captions into an MP4 subtitle track (`mov_text`).
- Copies the video stream without re-encoding where the source codec is compatible with MP4.
- Copies compatible audio streams; if the audio codec cannot be muxed into MP4, it retries with AAC audio while keeping the video stream untouched.
- Streams the resulting MP4 back as a download and removes temporary server files afterward.

Use only videos and subtitle files you own or are authorized to process. This first version is a file-based converter; it does not fetch or extract videos from YouTube.

## Run locally

Requires Python 3.12+ and FFmpeg installed on the machine.

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000.

## Deploy on Railway

The repository includes a Dockerfile and `railway.toml`. Create a Railway service from this GitHub repository and deploy it using the Dockerfile builder.

Optional environment variable:

- `MAX_UPLOAD_GB`: maximum accepted size for each uploaded file. Defaults to 12 GB.

## Large-file notes

Four-hour files are supported by the processing flow, but successful uploads depend on the service's available disk space, request limits, network stability, and resource plan. Railway's container filesystem is ephemeral; add a suitable volume if you need persistent working storage. Temporary job files are deleted after the response finishes.

## Current limitations

- Upload a video and its SRT/VTT captions; automatic caption discovery is not included.
- MP4 subtitle tracks use the `mov_text` codec. Compatibility depends on the player.
- Video codecs that MP4 cannot contain are not automatically transcoded in this first version.
- The upload progress bar tracks transfer; processing itself currently reports a packaging state rather than a precise FFmpeg percentage.
