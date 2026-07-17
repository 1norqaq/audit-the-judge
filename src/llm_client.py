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
import re
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
    temperature: float | None = 0.0,
    max_tokens: int = 1024,
    token_param: str = "max_tokens",
    extra_body: dict | None = None,
    retries: int = 4,
) -> str:
    """One chat completion -> assistant text. Retries with backoff on transient errors.

    Auto-adapts to provider parameter quirks that are self-described in the 400 error, so
    the same call works across OpenAI-compatible endpoints without per-model config:
      * reasoning models that reject `max_tokens`   -> resend as `max_completion_tokens`
      * models that reject a custom temperature      -> drop it (use the model default)
      * models that require `temperature == 1`        -> set it to 1
    Adaptations retry immediately (no backoff) and are bounded so a persistent 400 still
    surfaces. To skip the adaptation round-trip, set the correct `token_param` /
    `temperature` up front (the registry does this per model). temperature=None omits it.
    """
    client = _client(spec)
    temp = temperature
    last = None
    adapt_budget = 3
    attempt = 0
    while attempt < retries:
        kwargs: dict = {"model": spec.model, "messages": messages, token_param: max_tokens}
        if temp is not None:
            kwargs["temperature"] = temp
        if extra_body:
            kwargs["extra_body"] = extra_body
        try:
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001 - surface after retries
            msg = str(e).lower()
            if adapt_budget > 0:
                if "max_completion_tokens" in msg and token_param == "max_tokens":
                    token_param = "max_completion_tokens"; adapt_budget -= 1; continue
                if "temperature" in msg and "deprecated" in msg and temp is not None:
                    temp = None; adapt_budget -= 1; continue
                if "temperature" in msg and ("only" in msg or "must be" in msg):
                    # e.g. "only 0.6 is allowed" / "must be 1" — read the required value off the error
                    m = re.search(r"(?:only|must be)\s+([0-9]*\.?[0-9]+)", msg)
                    if m and temp != float(m.group(1)):
                        temp = float(m.group(1)); adapt_budget -= 1; continue
            last = e
            attempt += 1
            time.sleep(2 ** attempt)
    raise RuntimeError(f"chat() failed after {retries} attempts: {last}")
