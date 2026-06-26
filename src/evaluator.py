"""Evaluate extracted rules against gold NCCI edit table and source text."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def normalize_code(code) -> str:
    """Normalize CPT codes for pair matching (strip whitespace, int-like codes)."""
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    text = str(code).strip()
    if text.isdigit():
        return str(int(text))
    return text


def rules_to_pairs(rules: list[dict]) -> set[tuple[str, str]]:
    """Convert extracted rules to a set of (column1, column2) code pairs."""
    pairs: set[tuple[str, str]] = set()
    for rule in rules:
        c1 = normalize_code(rule.get("column1_code"))
        c2 = normalize_code(rule.get("column2_code"))
        if c1 and c2:
            pairs.add((c1, c2))
    return pairs


def load_gold_pairs(csv_path: Path | str) -> set[tuple[str, str]]:
    """Load gold-standard code pairs from the NCCI edit table CSV."""
    df = pd.read_csv(csv_path)
    pairs: set[tuple[str, str]] = set()
    for _, row in df.iterrows():
        c1 = normalize_code(row["Column1"])
        c2 = normalize_code(row["Column2"])
        if c1 and c2:
            pairs.add((c1, c2))
    return pairs


def compute_pair_metrics(
    predicted: set[tuple[str, str]],
    gold: set[tuple[str, str]],
) -> dict:
    """Compute precision, recall, and F1 for extracted code pairs vs gold."""
    true_positives = len(predicted & gold)
    false_positives = len(predicted - gold)
    false_negatives = len(gold - predicted)

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "predicted_pairs": sorted(predicted),
        "gold_pairs": sorted(gold),
    }


def hallucination_check(rules: list[dict], source_text: str) -> list[dict]:
    """Flag rationale_quote values that do not appear verbatim in the source text."""
    results: list[dict] = []
    for index, rule in enumerate(rules):
        quote = rule.get("rationale_quote", "") or ""
        is_hallucinated = bool(quote) and quote not in source_text
        results.append(
            {
                "rule_index": index,
                "column1_code": rule.get("column1_code"),
                "column2_code": rule.get("column2_code"),
                "rationale_quote": quote,
                "is_hallucinated": is_hallucinated,
            }
        )
    return results


def evaluate(
    extracted_rules: list[dict],
    gold_csv_path: Path | str,
    source_text: str,
) -> dict:
    """Run pair metrics and hallucination check; return structured results."""
    predicted = rules_to_pairs(extracted_rules)
    gold = load_gold_pairs(gold_csv_path)
    pair_metrics = compute_pair_metrics(predicted, gold)
    hallucinations = hallucination_check(extracted_rules, source_text)

    return {
        "pair_metrics": pair_metrics,
        "hallucination_check": hallucinations,
        "hallucination_count": sum(1 for h in hallucinations if h["is_hallucinated"]),
    }


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


if __name__ == "__main__":
    from extractor import extract_rules, load_policy_excerpt

    data_dir = _default_data_dir()
    policy_text = load_policy_excerpt(data_dir / "ncci_policy_excerpt.txt")
    gold_csv = data_dir / "ncci_edit_table_subset.csv"

    print("Running evaluator with simulation extractor output...")
    rules = extract_rules(policy_text)
    results = evaluate(rules, gold_csv, policy_text)
    print(json.dumps(results, indent=2))
