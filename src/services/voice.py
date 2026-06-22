import os
import httpx

class VoiceService:
    def __init__(self):
        self.groq_key         = os.environ.get("GROQ_API_KEY", "")
        self.huggingface_key  = os.environ.get("HUGGINGFACE_API_KEY", "")
        self.openai_key       = os.environ.get("OPENAI_API_KEY", "")

        # Automatically load from backend/.env if it exists
        self._load_env_file()

    def _load_env_file(self):
        current_dir  = os.path.dirname(os.path.abspath(__file__))
        backend_dir  = os.path.dirname(os.path.dirname(current_dir))
        env_path     = os.path.join(backend_dir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                k, v = parts[0].strip(), parts[1].strip().strip('"').strip("'")
                                if k == "GROQ_API_KEY" and not self.groq_key:
                                    self.groq_key = v
                                elif k == "HUGGINGFACE_API_KEY" and not self.huggingface_key:
                                    self.huggingface_key = v
                                elif k == "OPENAI_API_KEY" and not self.openai_key:
                                    self.openai_key = v
            except Exception as e:
                print(f"[VOICE] Warning: Failed to read backend/.env: {e}")

    async def transcribe_audio(self, file_path: str) -> str:
        """
        Transcribes audio using a prioritised free-provider chain:
          1. Groq Whisper-large-v3   (primary  — always network-reachable)
          2. HuggingFace Whisper-v3  (backup 1 — requires open DNS to api-inference.huggingface.co)
          3. OpenAI Whisper-1        (backup 2 — only if OPENAI_API_KEY present; never hardcoded)
        """

        # ── 1. Groq Whisper (primary) ─────────────────────────────────────────
        if self.groq_key:
            try:
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                headers = {"Authorization": f"Bearer {self.groq_key}"}
                async with httpx.AsyncClient(timeout=30.0) as client:
                    with open(file_path, "rb") as f:
                        audio_bytes = f.read()
                    files = {
                        "file": (os.path.basename(file_path), audio_bytes, "audio/m4a"),
                        "model": (None, "whisper-large-v3"),
                    }
                    res = await client.post(url, headers=headers, files=files)
                    if res.status_code == 200:
                        text = res.json().get("text", "").strip()
                        print(f"[VOICE] Transcribed via Groq Whisper ({len(text)} chars)")
                        return text
                    else:
                        print(f"[VOICE] Groq Whisper returned HTTP {res.status_code}: {res.text[:200]}")
            except Exception as e:
                print(f"[VOICE] Groq Whisper transcription failed: {e}")

        # ── 2. HuggingFace Whisper (backup 1) ────────────────────────────────
        if self.huggingface_key:
            try:
                url     = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"
                headers = {"Authorization": f"Bearer {self.huggingface_key}"}
                # 10 s timeout — avoids 30 s hang when DNS is blocked
                async with httpx.AsyncClient(timeout=10.0) as client:
                    with open(file_path, "rb") as f:
                        audio_data = f.read()
                    res = await client.post(url, headers=headers, content=audio_data)
                    if res.status_code == 200:
                        text = res.json().get("text", "").strip()
                        print(f"[VOICE] Transcribed via HuggingFace Whisper ({len(text)} chars)")
                        return text
                    else:
                        print(f"[VOICE] HuggingFace Whisper HTTP {res.status_code}: {res.text[:200]}")
            except Exception as e:
                print(f"[VOICE] HuggingFace Whisper failed (likely DNS block): {e}")

        # ── 3. OpenAI Whisper (backup 2, only if key explicitly configured) ──
        if self.openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_key)
                with open(file_path, "rb") as audio_file:
                    transcription = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                    text = transcription.text.strip()
                    print(f"[VOICE] Transcribed via OpenAI Whisper ({len(text)} chars)")
                    return text
            except Exception as e:
                print(f"[VOICE] OpenAI Whisper fallback failed: {e}")

        print("[VOICE] All transcription providers failed — returning empty string")
        return ""


voice_service = VoiceService()
