import os, io, time, math, tempfile, requests, re
from typing import List, Optional, Tuple
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from moviepy.audio.fx.all import audio_loop
from pydub import AudioSegment

# --- Simple helpers ---
def _get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    # Read from env first, then from Streamlit secrets if available
    v = os.getenv(key, default)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default

def clean_topic_for_query(topic: str) -> str:
    topic = topic.strip()
    topic = re.sub(r'\s+', ' ', topic)
    return topic

# --- Script generation ---
def generate_script(topic: str, duration_sec: int = 45) -> str:
    """
    Try to generate a ~N-second voiceover script about the topic.
    Uses OpenAI if OPENAI_API_KEY present; otherwise returns a simple template
    instructing the user to paste a script in the UI (handled in app.py).
    """
    topic = topic.strip()
    api_key = _get_secret("OPENAI_API_KEY")
    approx_words = int(duration_sec * 2.5)  # ~2.5 w/s
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            prompt = f"""
Write an engaging, concise voiceover script about "{topic}" for a short vertical video.
Length target: {approx_words} words.
Tone: curious, cinematic but clear. No fluff. Short sentences.
Return JUST the script (plain text), no headings.
"""
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a concise scriptwriter for viral short videos."},
                    {"role": "user", "content": prompt.strip()},
                ],
                temperature=0.7,
            )
            script = resp.choices[0].message.content.strip()
            # Safety squeeze: cap to ~1.2x target
            words = script.split()
            if len(words) > int(approx_words*1.2):
                script = " ".join(words[:int(approx_words*1.2)])
            return script
        except Exception as e:
            # Fall back
            pass
    # Fallback: return empty so UI can ask user to paste
    return ""

# --- Pexels imagery ---
def fetch_pexels_images(topic: str, count: int = 6) -> List[str]:
    """
    Returns a list of image URLs (prefer vertical-friendly) from Pexels.
    """
    key = _get_secret("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("Missing PEXELS_API_KEY. Add it to Streamlit secrets or environment.")
    headers = {"Authorization": key}
    q = clean_topic_for_query(topic)
    urls = []
    page = 1
    per_page = min(30, max(6, count*2))
    while len(urls) < count and page <= 5:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params={"query": q, "per_page": per_page, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        for p in data.get("photos", []):
            src = p.get("src", {})
            # choose portrait or large2x then fallback
            url = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
            if url:
                urls.append(url)
            if len(urls) >= count:
                break
        page += 1
        if not data.get("photos"):
            break
    return urls[:count]

def download_image_bytes(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content

# --- TTS ---
def tts_elevenlabs(text: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> bytes:
    """
    Uses ElevenLabs Text-to-Speech.
    Default voice_id is a commonly available example voice id.
    """
    api_key = _get_secret("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY")
    headers = {
        "accept": "audio/mpeg",
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.content

def tts_gtts(text: str, lang: str = "en") -> bytes:
    tts = gTTS(text=text, lang=lang)
    with io.BytesIO() as buf:
        tts.write_to_fp(buf)
        return buf.getvalue()

def build_voiceover(script: str, provider: str = "auto") -> tuple[str, float]:
    """
    provider: 'auto' (try ElevenLabs then gTTS), 'elevenlabs', or 'gtts'
    Returns (path_to_mp3, duration_sec)
    """
    # Create temp mp3
    tmpdir = tempfile.mkdtemp(prefix="voice_")
    mp3_path = os.path.join(tmpdir, "voiceover.mp3")
    audio_bytes = None
    if provider in ("auto", "elevenlabs"):
        try:
            audio_bytes = tts_elevenlabs(script)
        except Exception:
            if provider == "elevenlabs":
                raise
    if audio_bytes is None:
        # fall back to gTTS
        audio_bytes = tts_gtts(script)

    with open(mp3_path, "wb") as f:
        f.write(audio_bytes)

    # Duration via pydub
    seg = AudioSegment.from_file(mp3_path)
    duration_sec = len(seg) / 1000.0
    return mp3_path, duration_sec

# --- Video assembly ---
def make_vertical_video(image_bytes_list: List[bytes], audio_path: str, target_h: int = 1920, target_w: int = 1080, crossfade: float = 0.4) -> str:
    """
    Stitches images into a vertical video that matches the audio duration.
    Returns path to mp4.
    """
    if len(image_bytes_list) < 1:
        raise ValueError("Need at least 1 image")

    # durations
    audio = AudioSegment.from_file(audio_path)
    audio_duration = len(audio) / 1000.0

    # Compute per-image duration with small overlaps for crossfade
    n = len(image_bytes_list)
    if n == 1:
        per = audio_duration
        crossfade = 0.0
    else:
        per = (audio_duration + (n - 1) * crossfade) / n

    clips = []
    for b in image_bytes_list:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
            t.write(b)
            t.flush()
            img_clip = ImageClip(t.name).resize(height=target_h)
            # center-crop to 1080x1920 portrait
            w, h = img_clip.size
            if w < target_w:
                img_clip = img_clip.resize(width=target_w)
                w, h = img_clip.size
            x1 = max(0, (w - target_w) // 2)
            img_clip = img_clip.crop(x1=x1, y1=0, x2=min(w, x1 + target_w), y2=target_h).set_duration(per)
            clips.append(img_clip)

    # Add crossfades
    video = clips[0]
    for i in range(1, len(clips)):
        video = concatenate_videoclips([video, clips[i]], method="compose", padding=-crossfade)

    # Attach audio
    aclip = AudioFileClip(audio_path)
    video = video.set_audio(aclip).set_fps(30)

    # Write mp4
    out_path = os.path.join(tempfile.mkdtemp(prefix="video_"), "output.mp4")
    video.write_videofile(out_path, codec="libx264", audio_codec="aac", bitrate="2000k", fps=30, threads=2, verbose=False, logger=None)
    return out_path
