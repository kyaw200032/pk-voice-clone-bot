"""
VoxCPM2 voice-cloning API client.

Talks to the public VoxCPM2 demo Gradio API (no GPU needed on our side):
  1. upload reference voice  -> /gradio_api/upload
  2. join generation queue    -> /gradio_api/queue/join   (fn_index 2 = /generate)
  3. poll for completion      -> /gradio_api/queue/data    (SSE)
  4. download result audio    -> /gradio_api/file=<path>

Proven end-to-end 2026-10-03 (Burmese text -> 15s MP3).
"""

import json
import mimetypes
import os
import time
import urllib.request
import uuid

BASE = os.environ.get("VOXCPM_API_BASE", "https://openbmb-voxcpm-demo.hf.space")
FN_INDEX = 2  # /generate endpoint


def _log(*a):
    print("[voxcpm]", *a, flush=True)


def _with_retries(fn, *args, tries=4, **kw):
    last = None
    for i in range(tries):
        try:
            return fn(*args, **kw)
        except Exception as e:  # noqa: BLE001 - network flakes, retry all
            last = e
            _log(f"retry {i + 1}/{tries}: {type(e).__name__}: {e}")
            time.sleep(3 + i * 3)
    raise last


def _upload(path):
    boundary = uuid.uuid4().hex
    fname = os.path.basename(path)
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        raw = f.read()
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
        f'filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'
    ).encode() + raw + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + "/gradio_api/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def _join(session, data):
    payload = {
        "data": data,
        "event_data": None,
        "fn_index": FN_INDEX,
        "session_hash": session,
        "trigger_id": 11,
    }
    req = urllib.request.Request(
        BASE + "/gradio_api/queue/join",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def _poll_once(session):
    req = urllib.request.Request(
        BASE + "/gradio_api/queue/data?session_hash=" + session,
        headers={"Accept": "text/event-stream"},
    )
    with urllib.request.urlopen(req, timeout=150) as r:
        return r.read().decode("utf-8", errors="ignore")


def _download(url, dest):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=180) as r:
        blob = r.read()
    with open(dest, "wb") as f:
        f.write(blob)
    return dest


def generate_cloned_audio(text, reference_audio_path, control_instruction="",
                          cfg=2.0, timeout=900):
    """Generate cloned-voice speech. Returns local path of the MP3 file."""
    session = uuid.uuid4().hex

    _log("uploading reference audio...")
    up = _with_retries(_upload, reference_audio_path)
    ref = {"path": up[0], "meta": {"_type": "gradio.FileData"}}

    data = [text, control_instruction, ref, False, "", cfg, False, False]
    _log("joining queue...")
    _with_retries(_join, session, data)

    _log("waiting for generation...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            raw = _poll_once(session)
        except Exception as e:  # noqa: BLE001
            _log("poll error:", type(e).__name__, e)
            time.sleep(5)
            continue
        for line in raw.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                msg = json.loads(line[6:])
            except Exception:  # noqa: BLE001
                continue
            mtype = msg.get("msg")
            if mtype == "process_completed":
                out = msg["output"]["data"][0]
                out_path = out["path"] if isinstance(out, dict) else out
                dest = f"/tmp/voxcpm_{session}.mp3"
                _log("downloading result...")
                _with_retries(_download, BASE + "/gradio_api/file=" + out_path, dest)
                return dest
            if mtype == "error":
                raise RuntimeError(f"VoxCPM2 generation error: {msg}")
        time.sleep(3)
    raise TimeoutError("VoxCPM2 generation timed out")
