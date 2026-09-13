"""Round-trip sanity check for graph_adapters.py.

Verifies that APE's CWL output and an equivalent hand-written custom-JSON
workflow normalize to the identical graph, and that the check is actually
sensitive to real differences (wrong order, wrong tool) rather than trivially
passing everything.

Run: venv/bin/python3 checker/check_graph_roundtrip.py
"""

from pathlib import Path

from graph_adapters import cwl_to_graph, graphs_match, llm_json_to_graph

REPO_ROOT = Path(__file__).resolve().parent.parent
CWL_PATH = REPO_ROOT / "results/no1/CWL/candidate_workflow_1.cwl"

# Hand-written equivalent of candidate_workflow_1.cwl:
# msConvert -> Comet -> PeptideProphet -> rt (verified by reading the file).
EQUIVALENT_JSON = {
    "steps": [
        {"id": "step1", "tool": "http://edamontology.org/msconvert", "in": ["workflow_input_1"]},
        {"id": "step2", "tool": "http://edamontology.org/comet", "in": ["step1"]},
        {"id": "step3", "tool": "http://edamontology.org/peptideprophet", "in": ["step2"]},
        {"id": "step4", "tool": "http://edamontology.org/rt", "in": ["step3"]},
    ],
    "workflow_output": "step4",
}

# Same tools, wrong order -- must NOT match.
WRONG_ORDER_JSON = {
    "steps": [
        {"id": "step1", "tool": "http://edamontology.org/msconvert", "in": ["workflow_input_1"]},
        {"id": "step2", "tool": "http://edamontology.org/peptideprophet", "in": ["step1"]},
        {"id": "step3", "tool": "http://edamontology.org/comet", "in": ["step2"]},
        {"id": "step4", "tool": "http://edamontology.org/rt", "in": ["step3"]},
    ],
    "workflow_output": "step4",
}

# Same order, one tool substituted -- must NOT match.
WRONG_TOOL_JSON = {
    "steps": [
        {"id": "step1", "tool": "http://edamontology.org/msconvert", "in": ["workflow_input_1"]},
        {"id": "step2", "tool": "http://edamontology.org/comet", "in": ["step1"]},
        {"id": "step3", "tool": "http://edamontology.org/peptideprophet", "in": ["step2"]},
        {"id": "step4", "tool": "http://edamontology.org/ptmprophet", "in": ["step3"]},
    ],
    "workflow_output": "step4",
}


def report(label, expected, actual):
    status = "PASS" if expected == actual else "FAIL"
    print(f"[{status}] {label}: expected match={expected}, got match={actual}")
    return status == "PASS"


def main():
    graph_cwl = cwl_to_graph(CWL_PATH)
    print(f"Parsed {CWL_PATH.name}: {graph_cwl.number_of_nodes()} nodes, "
          f"{graph_cwl.number_of_edges()} edges")
    print("  tools in order:", [graph_cwl.nodes[n]["tool"] for n in graph_cwl.nodes])

    results = []
    results.append(report(
        "identical workflow, different container (CWL vs JSON)",
        True, graphs_match(graph_cwl, llm_json_to_graph(EQUIVALENT_JSON)),
    ))
    results.append(report(
        "same tools, wrong order",
        False, graphs_match(graph_cwl, llm_json_to_graph(WRONG_ORDER_JSON)),
    ))
    results.append(report(
        "same order, one tool substituted",
        False, graphs_match(graph_cwl, llm_json_to_graph(WRONG_TOOL_JSON)),
    ))

    if all(results):
        print("\nAll round-trip checks passed.")
    else:
        print("\nSome round-trip checks FAILED -- see above.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
