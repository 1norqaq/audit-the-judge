# Run OUR paired-comparison dataset (data/pairs.jsonl) through the judge inside
# OpenCompass. Here the *judge itself is the model under evaluation*: for each judge
# task it reads (question, answer_first, answer_second) and emits a verdict line.
#
#   cd ~/projects/opencompass
#   python run.py ~/projects/audit-the-judge/configs/eval_pairwise_audit.py
#
# OC writes the judge's verdict text to outputs/pairwise_audit/<ts>/predictions/**.json.
#
# NOTE ON ANALYSIS PATH:
#   The rigorous statistics (negative/positive controls, bootstrap, FDR) are computed by
#   src/report.py, which reads a tidy verdict table. The TESTED, recommended way to produce
#   that table is src/run_judge.py — it applies the *identical* judge prompt below and writes
#   pair_id/order/pair_type/true_label alongside each verdict, which the analysis needs.
#   This OC config exists to (a) learn the OC data flow and (b) cross-check the judge inside
#   the standard harness. parse_outputs.load_opencompass_results() is a best-effort reader of
#   the predictions dir, but OC's per-version JSON layout may not preserve our metadata columns
#   — so for the report, prefer run_judge.py.
import os

from opencompass.models.openai_api import OpenAISDK
from opencompass.openicl.icl_prompt_template import PromptTemplate
from opencompass.openicl.icl_retriever import ZeroRetriever
from opencompass.openicl.icl_inferencer import GenInferencer
from opencompass.openicl.icl_evaluator import AccEvaluator
from opencompass.datasets import CustomDataset

JUDGE_MODEL = os.environ.get("OC_JUDGE_MODEL", "deepseek-chat")
API_KEY = os.environ.get("OC_JUDGE_API_KEY", "ENV")
API_BASE = os.environ.get("OC_JUDGE_API_BASE", "https://api.deepseek.com/v1")
PAIRS = os.environ.get("OC_PAIRS_PATH", os.path.expanduser("~/projects/audit-the-judge/data/pairs.jsonl"))

# The judge prompt — kept identical in spirit to src/run_judge.py
JUDGE_PROMPT = (
    "You are an impartial evaluator comparing two AI answers to the same question. "
    "Judge only on quality (correctness, helpfulness, clarity, completeness); ignore "
    "order, length, and formatting. If they are essentially equal, say tie.\n\n"
    "[Question]\n{question}\n\n[Answer 1]\n{answer_first}\n\n[Answer 2]\n{answer_second}\n\n"
    "Give one sentence of reasoning, then end with exactly one of:\n"
    "Verdict: 1   |   Verdict: 2   |   Verdict: tie"
)

models = [
    dict(
        type=OpenAISDK,
        abbr=f"{JUDGE_MODEL}-as-judge",
        path=JUDGE_MODEL,
        key=API_KEY,
        openai_api_base=API_BASE,
        query_per_second=2,
        max_out_len=400,
        max_seq_len=8192,
        batch_size=8,
        temperature=0.0,
        retry=4,
    )
]

reader_cfg = dict(
    input_columns=["question", "answer_first", "answer_second"],
    output_column="true_label",
)

infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=dict(round=[dict(role="HUMAN", prompt=JUDGE_PROMPT)]),
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

# Trivial evaluator: OC requires one, but the meaningful analysis is downstream in report.py.
eval_cfg = dict(evaluator=dict(type=AccEvaluator))

datasets = [
    dict(
        type=CustomDataset,
        abbr="judge_pairwise_audit",
        path=os.path.dirname(PAIRS),
        file_name=os.path.basename(PAIRS),
        reader_cfg=reader_cfg,
        infer_cfg=infer_cfg,
        eval_cfg=eval_cfg,
    )
]

work_dir = "outputs/pairwise_audit"
