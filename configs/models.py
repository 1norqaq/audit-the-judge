"""Model registry for the multi-judge comparison (src/run_compare.py).

Every entry is an OpenAI-compatible endpoint, so the same llm_client.chat() drives
all of them — only (model, api_base, api_key) change. Fill the API keys into .env
(see .env.example) and refer to them here by env-var NAME; keys are never written
into this file, so it is safe to commit.

Edit the `model` fields to whatever you are entitled to call (deployment/version IDs
differ per account). Comment a judge out to skip it.

Provider notes / gotchas
------------------------
* OpenAI  (ChatGPT)   base = https://api.openai.com/v1
* Moonshot (Kimi)     base = https://api.moonshot.ai/v1   (use api.moonshot.cn for CN)
* Google  (Gemini)    base = https://generativelanguage.googleapis.com/v1beta/openai/
      OpenAI-compat layer; needs the trailing slash. Some tiers reject temperature=0 —
      if a judge errors, set its "temperature" here to 0.0->0.01 or 1.0 (see below).
* Anthropic (Claude)  base = https://api.anthropic.com/v1/
      OpenAI-compat layer; needs the trailing slash and a real "max_tokens".
* DeepSeek            base = https://api.deepseek.com/v1   (the repo's original default)

Reasoning models (o-series, some Gemini/Claude "thinking" tiers) can force
temperature=1; give that judge an explicit "temperature": 1.0 below rather than the
audit default of 0.0.
"""
from __future__ import annotations

# The model that writes the seed QUESTION bank (data/questions.jsonl), via
# data/make_questions.py. Deliberately a strong, neutral THIRD-PARTY model — decoupled
# from both the answer generator and the judges — so the questions themselves are not
# authored by anything under audit. Only used when you (re)generate the question bank.
QUESTION_GENERATOR = {
    "name": "claude-opus-4-8",
    "model": "claude-opus-4-8",
    "api_base": "https://api.anthropic.com/v1/",
    "api_key_env": "ANTHROPIC_API_KEY",
}

# The ONE generator that builds the answer pairs (data/pairs.jsonl). Held fixed so every
# judge scores the exact same answers (a fair comparison). Kept neutral/cheap by default.
GENERATOR = {
    "name": "deepseek",
    "model": "deepseek-chat",
    "api_base": "https://api.deepseek.com/v1",
    "api_key_env": "DEEPSEEK_API_KEY",
}

# The judges to audit and compare. `name` is the label used in filenames/figures.
# Optional per-judge overrides:
#   "temperature": float   default 0.0 (deterministic). Some reasoning tiers force 1.0.
#   "max_tokens": int      default 400. REASONING judges (Luna, Kimi K2.6) emit hidden
#                          thinking tokens BEFORE the verdict; 400 can be exhausted mid-
#                          thought so no "Verdict:" line is produced (-> unparsed, wasted
#                          spend). Give them a larger budget. Raising this raises output
#                          cost, so keep it modest.
JUDGES = [
    {
        "name": "gpt-5.6-luna",
        "model": "gpt-5.6-luna",
        "api_base": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "temperature": 1.0,   # reasoning tier: rejects temperature != 1
        "max_tokens": 2000,   # leave room for reasoning tokens + the verdict line
        "token_param": "max_completion_tokens",  # reasoning tier rejects `max_tokens`
    },
    {
        "name": "claude-sonnet-5",
        "model": "claude-sonnet-5",
        "api_base": "https://api.anthropic.com/v1/",
        "api_key_env": "ANTHROPIC_API_KEY",
        "temperature": None,  # Sonnet 5 rejects `temperature` ("deprecated") — omit it
        "max_tokens": 1200,   # it sometimes writes a long comparison; 400 truncated ~5.6% before the verdict
    },
    {
        "name": "gemini-3.5-flash",
        "model": "gemini-3.5-flash",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "max_tokens": 3000,   # usually terse, but occasionally writes a long derivation; headroom avoids truncation
    },
    {
        "name": "kimi-k2.6",
        "model": "kimi-k2.6",
        "api_base": "https://api.moonshot.ai/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        # K2.6 defaults to a thinking mode whose hidden reasoning exhausts the token budget
        # (empty output -> unparsed) AND costs ~20x more. A pairwise judge wants a fast
        # verdict, not a chain of thought, so we disable thinking. With thinking OFF the
        # API requires temperature == 0.6 (with thinking ON it requires 1.0).
        "temperature": 0.6,
        "extra_body": {"thinking": {"type": "disabled"}},
        "max_tokens": 400,
    },
    {
        "name": "deepseek-v4",
        "model": "deepseek-chat",  # "deepseek-chat" points to the latest DeepSeek-V* chat model
        "api_base": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
]
