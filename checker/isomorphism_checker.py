"""Compare one LLM-produced workflow against APE's exported candidate set for
the same use case, via graph isomorphism.

Reference set is capped at the 25 exported CWL candidates per use case (not
APE's full up-to-1000-solution search space), which matches the resolved 25-cap
used everywhere else in the study (see ape-vs-llms-comparison-eval-plan
memory). This is a binary match/no-match signal, not a scored metric: no
partial-credit or edit-distance matching.
"""

import json
from pathlib import Path

from graph_adapters import cwl_to_graph, graphs_match, llm_json_to_graph


def load_ape_candidates(cwl_dir):
    cwl_dir = Path(cwl_dir)
    candidates = []
    for cwl_path in sorted(cwl_dir.glob("*.cwl")):
        candidates.append((cwl_path.name, cwl_to_graph(cwl_path)))
    return candidates


def check_llm_against_ape(llm_workflow, cwl_dir):
    if isinstance(llm_workflow, (str, Path)):
        with open(llm_workflow) as f:
            llm_workflow = json.load(f)

    try:
        llm_graph = llm_json_to_graph(llm_workflow)
    except (KeyError, TypeError, AttributeError) as e:
        return {"matched": None, "matched_candidates": [], "error": f"unparseable: {e}"}

    candidates = load_ape_candidates(cwl_dir)
    matched_candidates = [
        name for name, ape_graph in candidates if graphs_match(llm_graph, ape_graph)
    ]

    return {"matched": bool(matched_candidates), "matched_candidates": matched_candidates}


if __name__ == "__main__":
    REPO_ROOT = Path(__file__).resolve().parent.parent
    CWL_DIR = REPO_ROOT / "results/no1/CWL"

    # Demo/smoke test: reload one of APE's own candidates as if it were LLM
    # output (via the CWL adapter, not the JSON one, but the resulting graph
    # is what check_llm_against_ape actually compares) -- must match itself.
    reused_graph = cwl_to_graph(CWL_DIR / "candidate_workflow_1.cwl")

    candidates = load_ape_candidates(CWL_DIR)
    self_match = [name for name, g in candidates if graphs_match(reused_graph, g)]
    print(f"[{'PASS' if 'candidate_workflow_1.cwl' in self_match else 'FAIL'}] "
          f"APE's own candidate_workflow_1 matches itself among the 25: {self_match}")

    # A workflow with a tool not in the domain -- must report matched=False,
    # not crash.
    bogus_workflow = {
        "steps": [
            {"id": "step1", "tool": "http://edamontology.org/not_a_real_tool", "in": ["workflow_input_1"]},
        ],
        "workflow_output": "step1",
    }
    result = check_llm_against_ape(bogus_workflow, CWL_DIR)
    print(f"[{'PASS' if result['matched'] is False else 'FAIL'}] "
          f"bogus single-tool workflow: {result}")

    # Malformed input (missing required field) -- must report matched=None
    # with an error, not crash.
    malformed_workflow = {"steps": [{"id": "step1"}]}
    result = check_llm_against_ape(malformed_workflow, CWL_DIR)
    print(f"[{'PASS' if result['matched'] is None else 'FAIL'}] "
          f"malformed workflow: {result}")
