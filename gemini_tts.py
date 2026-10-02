"""
Gemini TTS client (Google AI Studio voices).

Uses the Gemini generateContent API with responseModalities AUDIO.
Returns 16-bit PCM mono 24kHz -> wrapped into WAV with pure stdlib
(no ffmpeg needed on the host).

Auth: GEMINI_API_KEY env var.
"""

import base64
import json
import os
import urllib.request
import wave

MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Curated voice buttons shown in the bot (masculine-leaning first).
VOICES = ["Charon", "Fenrir", "Orus", "Puck", "Kore", "Aoede"]
DEFAULT_VOICE = "Charon"


def generate_gemini_audio(text, voice=DEFAULT_VOICE, api_key=None):
    """Synthesize text with a Gemini prebuilt voice. Returns local .wav path."""
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    if voice not in VOICES:
        voice = DEFAULT_VOICE

    url = f"{API_BASE}/{MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            obj = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Gemini TTS request failed: {type(e).__name__}: {e}")

    try:
        inline = obj["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm = base64.b64decode(inline["data"])
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Gemini TTS bad response: {e}")

    import uuid
    dest = f"/tmp/gemini_{uuid.uuid4().hex}.wav"
    with wave.open(dest, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return dest
