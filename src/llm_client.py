"""Thin OpenAI-compatible chat client with retries.

Used by both the answer generator (build_pairs.py) and the judge runner
(run_judge.py). Any OpenAI-compatible endpoint works — DeepSeek, OpenAI,
a local vLLM server, etc. — selected purely by environment variables:

    OC_JUDGE_MODEL / OC_JUDGE_API_KEY / OC_JUDGE_API_BASE   (judge)
    OC_GEN_MODEL   / OC_GEN_API_KEY   / OC_GEN_API_BASE     (generator; falls
                                                             back to the judge vars)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass


@dataclass
class ModelSpec:
    model: str
    api_key: str
    api_base: str

    @classmethod
    def from_env(cls, role: str) -> "ModelSpec":
        """role is 'JUDGE' or 'GEN'. GEN falls back to JUDGE vars."""
        role = role.upper()

        def pick(suffix: str) -> str | None:
            v = os.getenv(f"OC_{role}_{suffix}")
            if (v is None or v == "") and role == "GEN":
                v = os.getenv(f"OC_JUDGE_{suffix}")
            return v

        model = pick("MODEL")
        api_key = pick("API_KEY")
        api_base = pick("API_BASE")
        missing = [n for n, v in [("MODEL", model), ("API_KEY", api_key), ("API_BASE", api_base)] if not v]
        if missing:
            raise RuntimeError(
                f"Missing env var(s) for {role}: "
                + ", ".join(f"OC_{role}_{m}" for m in missing)
                + ".  Copy .env.example to .env, fill it in, and `source .env`."
            )
        return cls(model=model, api_key=api_key, api_base=api_base)


def _client(spec: ModelSpec):
    from openai import OpenAI  # imported lazily so non-API code paths need no key

    return OpenAI(api_key=spec.api_key, base_url=spec.api_base)


def chat(
    spec: ModelSpec,
    messages: list[dict],
    *,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    retries: int = 4,
) -> str:
    """One chat completion -> assistant text. Retries with backoff on transient errors."""
    client = _client(spec)
    last = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=spec.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001 - surface after retries
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"chat() failed after {retries} attempts: {last}")
