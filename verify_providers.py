"""
TripSync AI Provider Verification Script
Tests all 4 free-tier providers and logs results.
"""
import asyncio
import os
import time

# ── Load .env ────────────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
keys = {}
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    k, v = parts[0].strip(), parts[1].strip().strip('"').strip("'")
                    keys[k] = v
                    os.environ[k] = v

GEMINI_KEY       = keys.get("GEMINI_API_KEY", "")
GROQ_KEY         = keys.get("GROQ_API_KEY", "")
OPENROUTER_KEY   = keys.get("OPENROUTER_API_KEY", "")
HUGGINGFACE_KEY  = keys.get("HUGGINGFACE_API_KEY", "")

SEP = "=" * 60
PROMPT = "Reply with exactly: TRIPSYNC_AI_OK"

import httpx

# ── 1. Gemini ─────────────────────────────────────────────────────────────────
async def test_gemini():
    if not GEMINI_KEY:
        return None, "NOT CONFIGURED"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024}
    }
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            elapsed = round(time.time() - t0, 2)
            if res.status_code == 200:
                data = res.json()
                try:
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return text, f"HTTP 200 in {elapsed}s"
                except KeyError:
                    return None, f"HTTP 200, structure error: {data}"
            else:
                return None, f"HTTP {res.status_code}: {res.text[:200]}"
    except Exception as e:
        return None, f"Exception: {e}"

# ── 2. Groq ───────────────────────────────────────────────────────────────────
async def test_groq():
    if not GROQ_KEY:
        return None, "NOT CONFIGURED"
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a test assistant. Always respond with exactly what the user says."},
            {"role": "user",   "content": PROMPT}
        ],
        "temperature": 0.0,
        "max_tokens": 20
    }
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payload, headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            })
            elapsed = round(time.time() - t0, 2)
            if res.status_code == 200:
                text = res.json()["choices"][0]["message"]["content"].strip()
                return text, f"HTTP 200 in {elapsed}s"
            else:
                return None, f"HTTP {res.status_code}: {res.text[:200]}"
    except Exception as e:
        return None, f"Exception: {e}"

# ── 3. OpenRouter ─────────────────────────────────────────────────────────────
async def test_openrouter():
    if not OPENROUTER_KEY:
        return None, "NOT CONFIGURED"
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "google/gemma-4-31b-it:free",
        "messages": [
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user",   "content": PROMPT}
        ],
        "temperature": 0.0
    }
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payload, headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json"
            })
            elapsed = round(time.time() - t0, 2)
            if res.status_code == 200:
                text = res.json()["choices"][0]["message"]["content"].strip()
                return text, f"HTTP 200 in {elapsed}s"
            else:
                return None, f"HTTP {res.status_code}: {res.text[:200]}"
    except Exception as e:
        return None, f"Exception: {e}"

# ── 4. HuggingFace ────────────────────────────────────────────────────────────
async def test_huggingface():
    if not HUGGINGFACE_KEY:
        return None, "NOT CONFIGURED"
    url = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-1B-Instruct"
    combined_prompt = f"<|system|>\nYou are a test assistant.\n<|user|>\n{PROMPT}\n<|assistant|>\n"
    payload = {
        "inputs": combined_prompt,
        "parameters": {"max_new_tokens": 20, "temperature": 0.1}
    }
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload, headers={
                "Authorization": f"Bearer {HUGGINGFACE_KEY}",
                "Content-Type": "application/json"
            })
            elapsed = round(time.time() - t0, 2)
            if res.status_code == 200:
                data = res.json()
                out = ""
                if isinstance(data, list) and data:
                    out = data[0].get("generated_text", "")
                    if out.startswith(combined_prompt):
                        out = out[len(combined_prompt):]
                return out.strip(), f"HTTP 200 in {elapsed}s"
            else:
                return None, f"HTTP {res.status_code}: {res.text[:200]}"
    except Exception as e:
        return None, f"Exception: {e}"

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print(SEP)
    print("  TripSync AI Provider Verification")
    print(SEP)

    # Key presence check
    print("\n[1] API KEY LOAD STATUS")
    print(f"  GEMINI_API_KEY     : {'LOADED (' + GEMINI_KEY[:12] + '...)' if GEMINI_KEY else 'MISSING'}")
    print(f"  GROQ_API_KEY       : {'LOADED (' + GROQ_KEY[:12] + '...)' if GROQ_KEY else 'MISSING'}")
    print(f"  OPENROUTER_API_KEY : {'LOADED (' + OPENROUTER_KEY[:12] + '...)' if OPENROUTER_KEY else 'MISSING'}")
    print(f"  HUGGINGFACE_API_KEY: {'LOADED (' + HUGGINGFACE_KEY[:12] + '...)' if HUGGINGFACE_KEY else 'MISSING'}")

    print(f"\n[2] LIVE PROVIDER TESTS  (prompt: '{PROMPT}')")
    print(SEP)

    results = {}

    print("\n  >>> Testing Gemini 2.5 Flash ...")
    g_resp, g_status = await test_gemini()
    results["Gemini"] = (g_resp, g_status)
    status_icon = "PASS" if g_resp else "FAIL"
    print(f"  [{status_icon}] Status  : {g_status}")
    print(f"  [{status_icon}] Response: {g_resp or 'N/A'}")

    print("\n  >>> Testing Groq LLaMA-3.3-70B ...")
    gr_resp, gr_status = await test_groq()
    results["Groq"] = (gr_resp, gr_status)
    status_icon = "PASS" if gr_resp else "FAIL"
    print(f"  [{status_icon}] Status  : {gr_status}")
    print(f"  [{status_icon}] Response: {gr_resp or 'N/A'}")

    print("\n  >>> Testing OpenRouter (Gemma-2-9B) ...")
    or_resp, or_status = await test_openrouter()
    results["OpenRouter"] = (or_resp, or_status)
    status_icon = "PASS" if or_resp else "FAIL"
    print(f"  [{status_icon}] Status  : {or_status}")
    print(f"  [{status_icon}] Response: {or_resp or 'N/A'}")

    print("\n  >>> Testing HuggingFace (Llama-3.2-1B) ...")
    hf_resp, hf_status = await test_huggingface()
    results["HuggingFace"] = (hf_resp, hf_status)
    status_icon = "PASS" if hf_resp else "FAIL"
    print(f"  [{status_icon}] Status  : {hf_status}")
    print(f"  [{status_icon}] Response: {hf_resp or 'N/A'}")

    print(f"\n[3] PROVIDER SUMMARY")
    print(SEP)
    active_providers = [name for name, (resp, _) in results.items() if resp]
    fallback_only    = [name for name, (resp, _) in results.items() if not resp]

    for name, (resp, status) in results.items():
        icon = "ACTIVE (Real AI)" if resp else "OFFLINE / FAILED"
        print(f"  {name:<14}: {icon}")

    print(f"\n[4] ACTIVE PROVIDER (first in fallback chain that succeeded)")
    if active_providers:
        primary = active_providers[0]
        print(f"  --> PRIMARY : {primary}")
        if len(active_providers) > 1:
            print(f"  --> BACKUPS : {', '.join(active_providers[1:])}")
    else:
        print("  --> ALL PROVIDERS FAILED — running on LOCAL FALLBACK TEMPLATES")

    print(f"\n[5] AI MODE")
    if active_providers:
        print(f"  System is using: REAL AI RESPONSES (via {primary})")
        print(f"  Local fallback : INACTIVE (not needed)")
    else:
        print(f"  System is using: LOCAL FALLBACK LOGIC (no live AI)")

    print(f"\n{SEP}")
    print("  Verification complete.")
    print(SEP)

asyncio.run(main())
