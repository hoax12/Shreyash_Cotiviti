"""Single-page Streamlit demo for the PolicyEngine POC."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Allow imports when run as: streamlit run src/app.py (from project root)
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from audit_engine import EXAMPLE_CLAIMS, audit_claim
from evaluator import evaluate
from extractor import _groq_api_key_configured, extract_rules, load_policy_excerpt

_DATA_DIR = _SRC_DIR.parent / "data"
_GOLD_CSV = _DATA_DIR / "ncci_edit_table_subset.csv"

st.set_page_config(page_title="PolicyEngine POC", layout="wide")
st.title("PolicyEngine POC")
st.caption(
    "LLM extraction of CMS policy narrative into structured rules, "
    "evaluated against published NCCI edit data, then applied deterministically to test claims."
)

api_mode = "API" if _groq_api_key_configured() else "Simulation"
st.info(
    f"**Extraction mode: {api_mode}** — "
    + (
        "Using Groq API (open-source model) for rule extraction."
        if api_mode == "API"
        else "GROQ_API_KEY is not set; using hardcoded simulation output grounded in the policy excerpt."
    )
)

# --- Panel 1: Input policy text ---
st.header("Panel 1 — Input policy text")

if "policy_text" not in st.session_state:
    st.session_state.policy_text = load_policy_excerpt()

policy_text = st.text_area(
    "CMS NCCI policy narrative (editable)",
    value=st.session_state.policy_text,
    height=220,
)

col_run, col_reset = st.columns([1, 1])
with col_run:
    extract_clicked = st.button("Extract rules", type="primary")
with col_reset:
    if st.button("Reset to default excerpt"):
        st.session_state.policy_text = load_policy_excerpt()
        st.session_state.pop("extracted_rules", None)
        st.session_state.pop("eval_results", None)
        st.rerun()

if extract_clicked or "extracted_rules" not in st.session_state:
    with st.spinner("Extracting rules..."):
        st.session_state.extracted_rules = extract_rules(policy_text)
        st.session_state.eval_results = evaluate(
            st.session_state.extracted_rules,
            _GOLD_CSV,
            policy_text,
        )
    st.session_state.policy_text = policy_text

extracted_rules = st.session_state.get("extracted_rules", [])
eval_results = st.session_state.get("eval_results")

# --- Panel 2: Extracted JSON + evaluation score ---
st.header("Panel 2 — Extracted JSON + evaluation score")

if not extracted_rules:
    st.warning("Run extraction from Panel 1 to see results here.")
else:
    st.subheader("Extracted rules (JSON)")
    st.code(json.dumps(extracted_rules, indent=2), language="json")

    if eval_results:
        metrics = eval_results["pair_metrics"]
        hallucinations = eval_results["hallucination_check"]
        hallucination_count = eval_results["hallucination_count"]

        st.subheader("Evaluation vs gold NCCI edit table")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Precision", f"{metrics['precision']:.2%}")
        m2.metric("Recall", f"{metrics['recall']:.2%}")
        m3.metric("F1", f"{metrics['f1']:.2%}")
        m4.metric("Hallucinations", hallucination_count)

        st.caption(
            f"True positives: {metrics['true_positives']} · "
            f"False positives: {metrics['false_positives']} · "
            f"False negatives: {metrics['false_negatives']}"
        )

        if hallucination_count > 0:
            st.error(
                f"**{hallucination_count} hallucination flag(s):** "
                "rationale_quote text not found verbatim in the source policy."
            )
            for item in hallucinations:
                if item["is_hallucinated"]:
                    st.warning(
                        f"Rule {item['rule_index']} "
                        f"({item['column1_code']}/{item['column2_code']}): "
                        f'"{item["rationale_quote"][:120]}..."'
                    )
        else:
            st.success("No hallucination flags — all rationale quotes appear in the source text.")

# --- Panel 3: Live audit results ---
st.header("Panel 3 — Live audit results")

st.warning(
    "**Illustrative test inputs only.** The claims below were constructed by hand to "
    "exercise the deterministic audit logic. They are **not** real claims data, and "
    "no dollar amounts or recovery figures are shown."
)

if not extracted_rules:
    st.info("Extract rules in Panel 1 to run the audit engine.")
else:
    for label, claim in EXAMPLE_CLAIMS.items():
        result = audit_claim(extracted_rules, claim)
        verdict = result["verdict"].upper()
        icon = "✅" if result["verdict"] == "pass" else "❌"
        st.subheader(f"{icon} {label.upper()} example — {verdict}")
        st.markdown(f"**Reason:** {result['reason']}")
        with st.expander("Claim payload"):
            st.json(claim)
