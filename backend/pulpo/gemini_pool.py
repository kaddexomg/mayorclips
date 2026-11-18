import time
import json
import random
import re
import asyncio
from typing import Optional, Dict, Any, List
import httpx
from sqlmodel import Session
from app.config import GEMINI_API_KEYS
from app.db import engine
from app.models import PulpoUsage

MODELS_PRIMARY = [
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite"
]

MODELS_FALLBACK = [
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite-preview"
]

class GeminiPool:
    def __init__(self, keys: List[str] = None):
        self.keys = keys or list(GEMINI_API_KEYS)
        self.key_index = random.randint(0, max(0, len(self.keys) - 1)) if self.keys else 0
        self.cooldowns: Dict[str, float] = {} # key -> timestamp when available
        self.dead_keys: set[str] = set()
        self.stats: Dict[str, Dict[str, int]] = {k: {"calls": 0, "errors": 0, "tokens": 0} for k in self.keys}

    def get_available_key(self) -> Optional[str]:
        if not self.keys:
            return None
        now = time.time()
        for _ in range(len(self.keys)):
            k = self.keys[self.key_index]
            self.key_index = (self.key_index + 1) % len(self.keys)
            if k in self.dead_keys:
                continue
            if self.cooldowns.get(k, 0) <= now:
                return k
        # If all keys in cooldown, pick the one that clears earliest
        living_keys = [k for k in self.keys if k not in self.dead_keys]
        if not living_keys:
            return None
        living_keys.sort(key=lambda k: self.cooldowns.get(k, 0))
        earliest = living_keys[0]
        wait_sec = max(0.5, self.cooldowns.get(earliest, 0) - now)
        if wait_sec > 30.0:
            wait_sec = 5.0 # cap wait
        time.sleep(min(wait_sec, 5.0))
        return earliest

    def mark_cooldown(self, key: str, seconds: float = 60.0):
        self.cooldowns[key] = time.time() + seconds
        if key in self.stats:
            self.stats[key]["errors"] += 1

    def mark_dead(self, key: str):
        self.dead_keys.add(key)

    def log_usage(self, key: str, model: str, task: str, input_tokens: int, output_tokens: int, status_code: int, latency_ms: int):
        if key in self.stats:
            self.stats[key]["calls"] += 1
            self.stats[key]["tokens"] += (input_tokens + output_tokens)
        try:
            with Session(engine) as session:
                record = PulpoUsage(
                    key_prefix=key[:12] if key else "unknown",
                    model=model,
                    task=task,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status_code=status_code,
                    latency_ms=latency_ms
                )
                session.add(record)
                session.commit()
        except Exception:
            pass

    async def generate_json(self, prompt: str, system_instruction: str = "", task_name: str = "general", max_retries: int = 4) -> Dict[str, Any]:
        """Calls Gemini API with automatic key rotation, rate-limit backoff, and JSON response guarantee."""
        model = MODELS_PRIMARY[0]
        attempts = 0

        while attempts < max_retries:
            key = self.get_available_key()
            if not key:
                raise RuntimeError("No hay API Keys de Gemini disponibles o todas están bloqueadas.")

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.4,
                    "responseMimeType": "application/json"
                }
            }
            if system_instruction:
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction}]
                }

            start_t = time.time()
            async with httpx.AsyncClient(timeout=45.0) as client:
                try:
                    res = await client.post(url, json=payload)
                    latency = int((time.time() - start_t) * 1000)

                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if not candidates:
                            raise ValueError("Gemini no devolvió candidatos.")
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        
                        usage_meta = data.get("usageMetadata", {})
                        in_tok = usage_meta.get("promptTokenCount", 0)
                        out_tok = usage_meta.get("candidatesTokenCount", 0)
                        self.log_usage(key, model, task_name, in_tok, out_tok, 200, latency)

                        # Clean and parse JSON
                        cleaned = text.strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned[7:]
                        if cleaned.startswith("```"):
                            cleaned = cleaned[3:]
                        if cleaned.endswith("```"):
                            cleaned = cleaned[:-3]
                        
                        try:
                            return json.loads(cleaned.strip())
                        except json.JSONDecodeError:
                            # Attempt regex extract
                            match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', cleaned)
                            if match:
                                return json.loads(match.group(1))
                            raise

                    elif res.status_code == 429:
                        print(f"[PULPO] 429 Cuota excedida en key {key[:10]}... Conmutando clave.")
                        self.mark_cooldown(key, seconds=65.0)
                        attempts += 1
                        model = MODELS_FALLBACK[0] # Degrade to lite
                        await asyncio.sleep(1.0)
                        continue

                    elif res.status_code == 401 or res.status_code == 403:
                        print(f"[PULPO] Key inválida {key[:10]}... Marcada como muerta.")
                        self.mark_dead(key)
                        attempts += 1
                        continue

                    elif res.status_code >= 500:
                        print(f"[PULPO] Servidor Gemini {res.status_code}. Conmutando a modelo lite.")
                        model = MODELS_FALLBACK[0]
                        attempts += 1
                        await asyncio.sleep(2.0)
                        continue

                    else:
                        print(f"[PULPO ERROR {res.status_code}] {res.text[:200]}")
                        attempts += 1
                        await asyncio.sleep(1.5)

                except Exception as e:
                    print(f"[PULPO EXCEPTION] Key {key[:10]}: {str(e)}")
                    attempts += 1
                    await asyncio.sleep(1.0)

        raise RuntimeError(f"Fallo en Pulpo Gemini tras {max_retries} reintentos en el pool de llaves.")

# Global singleton
gemini_pool = GeminiPool()
