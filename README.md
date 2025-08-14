# StoryShort‑Lite (Fixed Build)

A minimal StoryShort-style MVP you can deploy on **Streamlit Community Cloud**.

## What’s in this build
- ✅ Works on Python **3.13** (no `pydub` / `audioop` dependency)
- ✅ Handles Pillow 10+ (ANTIALIAS removal) via a small shim
- ✅ Fixes the Streamlit/Rich conflict by pinning `rich==13.7.1`

## Quick Deploy (Streamlit Cloud)
1. Create a new **public GitHub repo** and upload these files:
   - `app.py`, `utils.py`, `requirements.txt`, `README.md`
   - (Optional) `runtime.txt` to pin Python 3.11.9
2. On Streamlit Cloud, click **New app** → select the repo → **Main file** = `app.py` → **Deploy**.
3. In **Settings → Secrets**, add at least:
```toml
PEXELS_API_KEY = "your_pexels_key_here"
# optional:
OPENAI_API_KEY = "sk-..."
ELEVENLABS_API_KEY = "..." 
```

## Notes
- Uses Pexels for free stock images (commercial-friendly license; always verify): https://www.pexels.com/license/
- Voice: ElevenLabs (if key) → falls back to gTTS (free) for prototyping.
- Outputs a 1080×1920 vertical MP4 with crossfades.

Generated: 2025-08-14
