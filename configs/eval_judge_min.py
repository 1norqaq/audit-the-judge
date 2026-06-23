# Day 1-2 smoke config: run ONE LLM-as-judge evaluation through OpenCompass to learn
# its data flow (input data -> judge call -> per-judgment results -> summary csv).
#
# This is a minimal adaptation of opencompass/examples/eval_llm_judge.py, rewired so
# BOTH the candidate model and the judge model are any OpenAI-compatible endpoint read
# from your environment (OC_JUDGE_MODEL / OC_JUDGE_API_KEY / OC_JUDGE_API_BASE).
#
# Run:
#   cd ~/projects/opencompass
#   python run.py ~/projects/audit-the-judge/configs/eval_judge_min.py
# Then inspect:
#   outputs/judge_min/<ts>/summary/*.csv          <- the report
#   outputs/judge_min/<ts>/results/**/*.json      <- one record per judgment
#   outputs/judge_min/<ts>/predictions/**/*.json  <- candidate generations
import os

from mmengine.config import read_base
from opencompass.models.openai_api import OpenAISDK
from opencompass.openicl.icl_prompt_template import PromptTemplate
from opencompass.openicl.icl_retriever import ZeroRetriever
from opencompass.openicl.icl_inferencer import GenInferencer
from opencompass.evaluator import GenericLLMEvaluator
from opencompass.datasets import generic_llmjudge_postprocess, CustomDataset

JUDGE_MODEL = os.environ.get("OC_JUDGE_MODEL", "deepseek-chat")
API_KEY = os.environ.get("OC_JUDGE_API_KEY", "ENV")
API_BASE = os.environ.get("OC_JUDGE_API_BASE", "https://api.deepseek.com/v1")

_api_model = dict(
    type=OpenAISDK,
    abbr=JUDGE_MODEL,
    path=JUDGE_MODEL,
    key=API_KEY,
    openai_api_base=API_BASE,
    query_per_second=2,
    max_out_len=2048,
    max_seq_len=4096,
    batch_size=8,
    temperature=0.0,
    retry=4,
)

# Candidate model = the same endpoint (we just need *some* answers to grade for the smoke test)
models = [dict(_api_model, abbr=f"{JUDGE_MODEL}-candidate")]

math_reader_cfg = dict(input_columns=["problem"], output_column="answer")
math_reader_cfg["test_range"] = "[0:8]"  # tiny: 8 examples

math_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=dict(round=[dict(role="HUMAN", prompt="{problem}\nPut your final answer in \\boxed{}.")]),
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

GRADER = (
    "Judge whether the candidate's final answer matches the standard answer. "
    "Reply with exactly 'A' (CORRECT) or 'B' (INCORRECT).\n\n"
    "<Question>\n{problem}\n</Question>\n"
    "<Gold>\n{answer}\n</Gold>\n"
    "<Predicted>\n{prediction}\n</Predicted>\n"
)

math_eval_cfg = dict(
    evaluator=dict(
        type=GenericLLMEvaluator,
        prompt_template=dict(
            type=PromptTemplate,
            template=dict(round=[dict(role="HUMAN", prompt=GRADER)]),
        ),
        dataset_cfg=dict(
            type=CustomDataset,
            path="opencompass/math",
            file_name="test_prm800k_500.jsonl",
            reader_cfg=math_reader_cfg,
        ),
        judge_cfg=_api_model,
        dict_postprocessor=dict(type=generic_llmjudge_postprocess),
    ),
)

datasets = [
    dict(
        type=CustomDataset,
        abbr="math_smoke",
        path="opencompass/math",
        file_name="test_prm800k_500.jsonl",
        reader_cfg=math_reader_cfg,
        infer_cfg=math_infer_cfg,
        eval_cfg=math_eval_cfg,
    )
]

work_dir = "outputs/judge_min"
