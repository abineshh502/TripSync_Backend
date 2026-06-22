import os
import httpx
import json

class AIProvider:
    def __init__(self):
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self.groq_key = os.environ.get("GROQ_API_KEY", "")
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.huggingface_key = os.environ.get("HUGGINGFACE_API_KEY", "")

        # Automatically load from backend/.env if it exists
        self._load_env_file()

        # Configured fallback order
        self.provider_chain = ["gemini", "groq", "openrouter", "huggingface"]

    def _load_env_file(self):
        # Look for .env in the backend folder (which is backend/src/services/../../)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(os.path.dirname(current_dir))
        env_path = os.path.join(backend_dir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                k, v = parts[0].strip(), parts[1].strip().strip('"').strip("'")
                                if k == "GEMINI_API_KEY" and not self.gemini_key:
                                    self.gemini_key = v
                                elif k == "GROQ_API_KEY" and not self.groq_key:
                                    self.groq_key = v
                                elif k == "OPENROUTER_API_KEY" and not self.openrouter_key:
                                    self.openrouter_key = v
                                elif k == "HUGGINGFACE_API_KEY" and not self.huggingface_key:
                                    self.huggingface_key = v
            except Exception as e:
                print(f"⚠️ Failed to read backend/.env configuration: {e}")

    async def generate_text(self, system_instruction: str, prompt: str, history: list = None, force_json: bool = False) -> str:
        """
        Runs through the fallback chain of free AI API providers to generate a response.
        Failover order: Gemini -> Groq -> OpenRouter -> HuggingFace -> RuntimeError
        Every attempt is logged so demo-day logs show exactly which provider responded.
        """
        errors = []
        prompt_preview = prompt[:80].replace("\n", " ") if prompt else ""

        for provider in self.provider_chain:
            if provider == "gemini" and self.gemini_key:
                try:
                    res = await self._call_gemini(system_instruction, prompt, history, force_json)
                    if res:
                        print(f"[AI] Provider=Gemini | OK | prompt='{prompt_preview}'")
                        return res
                except Exception as e:
                    print(f"[AI] Provider=Gemini | FAIL | {e}")
                    errors.append(f"Gemini: {e}")

            elif provider == "groq" and self.groq_key:
                try:
                    res = await self._call_groq(system_instruction, prompt, history, force_json)
                    if res:
                        print(f"[AI] Provider=Groq | OK | prompt='{prompt_preview}'")
                        return res
                except Exception as e:
                    print(f"[AI] Provider=Groq | FAIL | {e}")
                    errors.append(f"Groq: {e}")

            elif provider == "openrouter" and self.openrouter_key:
                try:
                    res = await self._call_openrouter(system_instruction, prompt, history, force_json)
                    if res:
                        print(f"[AI] Provider=OpenRouter | OK | prompt='{prompt_preview}'")
                        return res
                except Exception as e:
                    print(f"[AI] Provider=OpenRouter | FAIL | {e}")
                    errors.append(f"OpenRouter: {e}")

            elif provider == "huggingface" and self.huggingface_key:
                try:
                    res = await self._call_huggingface(system_instruction, prompt, force_json)
                    if res:
                        print(f"[AI] Provider=HuggingFace | OK | prompt='{prompt_preview}'")
                        return res
                except Exception as e:
                    print(f"[AI] Provider=HuggingFace | FAIL | {e}")
                    errors.append(f"HuggingFace: {e}")

        # All configured providers failed
        raise RuntimeError(
            f"[AI] All providers failed. Errors: {'; '.join(errors)}"
        )

    async def _call_gemini(self, system_instruction: str, prompt: str, history: list = None, force_json: bool = False) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_key}"
        
        contents = []
        if history:
            for h in history:
                role = "user" if h.get("role") == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": h.get("content", "")}]
                })
        
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048
            }
        }
        
        if force_json:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            if res.status_code == 200:
                data = res.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except KeyError:
                    raise ValueError(f"Invalid Gemini response structure: {data}")
            else:
                raise ValueError(f"Gemini API returned status {res.status_code}: {res.text}")

    async def _call_groq(self, system_instruction: str, prompt: str, history: list = None, force_json: bool = False) -> str:
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        messages = [{"role": "system", "content": system_instruction}]
        if history:
            for h in history:
                messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024
        }

        if force_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
            else:
                raise ValueError(f"Groq API returned status {res.status_code}: {res.text}")

    async def _call_openrouter(self, system_instruction: str, prompt: str, history: list = None, force_json: bool = False) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        messages = [{"role": "system", "content": system_instruction}]
        if history:
            for h in history:
                messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "google/gemma-4-31b-it:free",
            "messages": messages,
            "temperature": 0.7
        }
        
        if force_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
            else:
                raise ValueError(f"OpenRouter API returned status {res.status_code}: {res.text}")

    async def _call_huggingface(self, system_instruction: str, prompt: str, force_json: bool = False) -> str:
        url = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-1B-Instruct"
        
        headers = {
            "Authorization": f"Bearer {self.huggingface_key}",
            "Content-Type": "application/json"
        }
        
        combined_prompt = f"<|system|>\n{system_instruction}\n<|user|>\n{prompt}\n<|assistant|>\n"
        
        payload = {
            "inputs": combined_prompt,
            "parameters": {
                "max_new_tokens": 512,
                "temperature": 0.7
            }
        }

        # 10 s timeout: avoids 30 s hang when api-inference.huggingface.co is DNS-blocked
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    out = data[0].get("generated_text", "")
                    if out.startswith(combined_prompt):
                        out = out[len(combined_prompt):]
                    return out
                return str(data)
            else:
                raise ValueError(f"HuggingFace API returned status {res.status_code}: {res.text}")

ai_provider = AIProvider()
