import os, streamlit as st
from utils import generate_script, fetch_pexels_images, download_image_bytes, build_voiceover, make_vertical_video

st.set_page_config(page_title="StoryShort-Lite", page_icon="🎬", layout="centered")

st.title("🎬 StoryShort‑Lite (MVP) — Fixed Build")
st.write("Create simple **faceless vertical videos** from a topic in minutes.")

with st.expander("🔑 Configure API keys (optional)", expanded=False):
    st.caption("You can also set these in **Settings → Secrets** on Streamlit Cloud.")
    openai_in = st.text_input("OpenAI API Key (optional):", type="password", help="Used to auto-write your script.")
    pexels_in = st.text_input("PEXELS API Key (required to fetch images):", type="password")
    eleven_in = st.text_input("ElevenLabs API Key (optional):", type="password", help="Used for high-quality voice.")
    if st.button("Save to session"):
        if openai_in: os.environ["OPENAI_API_KEY"] = openai_in
        if pexels_in: os.environ["PEXELS_API_KEY"] = pexels_in
        if eleven_in: os.environ["ELEVENLABS_API_KEY"] = eleven_in
        st.success("Saved (for this session).")

topic = st.text_input("🧠 Topic", placeholder="e.g. The day Apollo 11 landed on the moon")
duration = st.slider("Target duration (seconds)", 20, 120, 50, 5)
images_wanted = st.slider("Images per video", 3, 12, 7, 1)

st.divider()
st.subheader("1) Script")

default_script = ""
if topic:
    with st.spinner("Generating script… (or leave blank and paste your own)"):
        default_script = generate_script(topic, duration_sec=duration)

script = st.text_area("Script (edit freely — leave blank if you'll paste your own):",
                      value=default_script, height=180,
                      placeholder="Paste or write your voiceover script here if you didn't add an OpenAI key.")

st.divider()
st.subheader("2) Images")

if st.button("Fetch images from Pexels"):
    if not os.environ.get("PEXELS_API_KEY") and "PEXELS_API_KEY" not in st.secrets:
        st.error("Please add your PEXELS API key (above) first.")
    else:
        try:
            urls = fetch_pexels_images(topic or "space history", count=images_wanted)
            st.session_state["pexels_urls"] = urls
            st.success(f"Fetched {len(urls)} images.")
        except Exception as e:
            st.error(f"Image fetch failed: {e}")

thumbs = st.session_state.get("pexels_urls", [])
if thumbs:
    st.caption("Preview:")
    st.image(thumbs, width=140)

st.divider()
st.subheader("3) Voice & Video")

voice_provider = st.selectbox("Voice provider", ["auto (ElevenLabs → gTTS)", "ElevenLabs only", "gTTS only"], index=0)

if st.button("Generate Video"):
    if not script.strip():
        st.error("Please enter a script first (or add an OpenAI key and topic).")
        st.stop()
    urls = st.session_state.get("pexels_urls", [])
    if not urls:
        st.warning("No images selected yet — fetching generic ones…")
        try:
            urls = fetch_pexels_images(topic or "history", count=images_wanted)
        except Exception as e:
            st.error(f"Image fetch failed: {e}")
            st.stop()

    with st.spinner("Downloading images…"):
        images_bytes = []
        for u in urls:
            try:
                images_bytes.append(download_image_bytes(u))
            except Exception:
                pass
        if len(images_bytes) < 1:
            st.error("Couldn't download images.")
            st.stop()

    with st.spinner("Synthesizing voice…"):
        provider = "auto"
        if voice_provider.startswith("ElevenLabs"):
            provider = "elevenlabs"
        elif voice_provider.startswith("gTTS"):
            provider = "gtts"
        try:
            mp3_path, voice_dur = build_voiceover(script, provider=provider)
        except Exception as e:
            st.error(f"Voice generation failed: {e}")
            st.stop()

    with st.spinner("Rendering video… (this can take ~30–90s)"):
        try:
            out_path = make_vertical_video(images_bytes, mp3_path)
        except Exception as e:
            st.error(f"Video render failed: {e}")
            st.stop()

    st.success("Done!")
    st.video(out_path)
    with open(out_path, "rb") as f:
        st.download_button("Download MP4", data=f.read(), file_name="storyshort.mp4", mime="video/mp4")

st.caption("Tip: Upload your MP4 to YouTube Shorts or TikTok. For captions, paste your script into YouTube as subtitles.")
