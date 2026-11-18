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

# Models ordered by measured reliability and speed
MODELS_CYCLE = [
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
]


class GeminiPool:
    def __init__(self, keys: List[str] = None):
        self.keys = keys or list(GEMINI_API_KEYS)
        self.key_index = random.randint(0, max(0, len(self.keys) - 1)) if self.keys else 0
        self.cooldowns: Dict[str, float] = {}
        self.dead_keys: set[str] = set()
        self.stats: Dict[str, Dict[str, int]] = {
            k: {"calls": 0, "errors": 0, "tokens": 0} for k in self.keys
        }

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
        living_keys = [k for k in self.keys if k not in self.dead_keys]
        if not living_keys:
            return None
        living_keys.sort(key=lambda k: self.cooldowns.get(k, 0))
        return living_keys[0]

    def mark_cooldown(self, key: str, seconds: float = 60.0):
        self.cooldowns[key] = time.time() + seconds
        if key in self.stats:
            self.stats[key]["errors"] += 1

    def mark_dead(self, key: str):
        self.dead_keys.add(key)

    def log_usage(
        self,
        key: str,
        model: str,
        task: str,
        input_tokens: int,
        output_tokens: int,
        status_code: int,
        latency_ms: int,
    ):
        if key in self.stats:
            self.stats[key]["calls"] += 1
            self.stats[key]["tokens"] += input_tokens + output_tokens
        try:
            with Session(engine) as session:
                record = PulpoUsage(
                    key_prefix=key[:12] if key else "unknown",
                    model=model,
                    task=task,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status_code=status_code,
                    latency_ms=latency_ms,
                )
                session.add(record)
                session.commit()
        except Exception:
            pass

    def _parse_json_response(self, text: str) -> Any:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
            if match:
                return json.loads(match.group(1))
            raise

    async def generate_json(
        self,
        prompt: str,
        system_instruction: str = "",
        task_name: str = "general",
        media_parts: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 7,
    ) -> Any:
        """Calls Gemini API (text or multimodal audio/vision) with 7-key rotation and model failover."""
        attempts = 0
        model_idx = 0

        while attempts < max_retries:
            key = self.get_available_key()
            if not key:
                raise RuntimeError("No hay API Keys de Gemini disponibles o todas están bloqueadas.")

            model = MODELS_CYCLE[model_idx % len(MODELS_CYCLE)]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

            parts = []
            if media_parts:
                parts.extend(media_parts)
            parts.append({"text": prompt})

            gen_config: Dict[str, Any] = {
                "temperature": 0.3,
                "responseMimeType": "application/json",
            }
            # Disable slow thinking tokens on 3-flash for fast <7s multimodal responses
            if "gemini-3-flash" in model:
                gen_config["thinkingConfig"] = {"thinkingBudget": 0}

            payload: Dict[str, Any] = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": gen_config,
            }
            if system_instruction:
                payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

            start_t = time.time()
            async with httpx.AsyncClient(timeout=90.0) as client:
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
                        return self._parse_json_response(text)

                    elif res.status_code == 429:
                        print(f"[PULPO] 429 en key {key[:10]} ({model}). Rotando clave...")
                        self.mark_cooldown(key, seconds=65.0)
                        attempts += 1
                        await asyncio.sleep(0.5)
                        continue

                    elif res.status_code in (401, 403):
                        print(f"[PULPO] Key inválida {key[:10]} ({res.status_code}). Marcada como muerta.")
                        self.mark_dead(key)
                        attempts += 1
                        continue

                    elif res.status_code == 400 and "thinking" in res.text.lower():
                        model_idx += 1
                        attempts += 1
                        continue

                    elif res.status_code >= 500 or res.status_code == 404:
                        print(f"[PULPO] {res.status_code} en {model}. Cambiando modelo...")
                        model_idx += 1
                        attempts += 1
                        await asyncio.sleep(0.8)
                        continue

                    else:
                        print(f"[PULPO ERROR {res.status_code}] {res.text[:200]}")
                        attempts += 1
                        model_idx += 1
                        await asyncio.sleep(1.0)

                except Exception as e:
                    print(f"[PULPO EXCEPTION] Key {key[:10]} ({model}): {str(e)}")
                    attempts += 1
                    model_idx += 1
                    await asyncio.sleep(0.8)

        raise RuntimeError(f"Fallo en Pulpo Gemini tras {max_retries} reintentos en el pool de llaves.")


gemini_pool = GeminiPool()
