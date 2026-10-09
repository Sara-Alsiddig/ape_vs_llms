import json
import sys
from collections import Counter
import random
import csv
SHUFFLE_SEED = 2026  # fixed so IDs are identical on every run
from pathlib import Path

import networkx as nx

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
sys.path.insert(0, str(REPO_ROOT / "checker"))
from graph_adapters import cwl_to_graph,  llm_json_to_graph

RATING_DIR = REPO_ROOT / "eval" / "rating"

USE_CASES = ["no1", "no2", "no3", "no4"]

def graph_to_sequence(graph):
    # The sheet shows workflows as a linear tool sequence, which is only
    # honest if the workflow really is linear -- fail loudly otherwise.
    for node in graph.nodes:
        if graph.in_degree(node) > 1 or graph.out_degree(node) > 1:
            raise ValueError("non-linear workflow, can't show it as a sequence")
    return tuple(graph.nodes[n]["tool"] for n in nx.topological_sort(graph))

def load_ape(use_case):
    # Returns a list of (source_file, tool_sequence). No2 is UNSAT, so it
    # has no CWL folder and returns an empty list.
    cwl_dir = RESULTS_DIR / use_case / "CWL"
    if not cwl_dir.exists():
        return []
    return [(p.name, graph_to_sequence(cwl_to_graph(p))) for p in sorted(cwl_dir.glob("*.cwl"))]

def parse_llm_response(text):
    # Some responses wrap the JSON in a ```json ... ``` fence. Strip only
    # that exact wrapper; anything else unexpected should fail loudly.
    lines = text.strip().splitlines()
    if lines[0] in ("```json", "```") and lines[-1] == "```":
        lines = lines[1:-1]
    return json.loads("\n".join(lines))

def load_llm(use_case):
    # Returns (workflows, skipped). workflows is a list of
    # (source, model, tool_sequence); skipped lists the runs that answered
    # UNSAT, since they have no workflow to rate.
    workflows, skipped = [], []
    for p in sorted((RESULTS_DIR / use_case / "llm").glob("*/*/run*.txt")):
        variant, model = p.parent.parent.name, p.parent.name
        source = f"{variant}/{model}/{p.name}"
        response = parse_llm_response(p.read_text())
        if response["unsatisfiable"]:
            skipped.append(source)
        else:
            sequence = graph_to_sequence(llm_json_to_graph(response))
            workflows.append((source, model, sequence))
    return workflows, skipped

def collect(use_case):
    # Group every workflow_producing file under its tool sequence, so each
    # distinct workflow is rated once and its score maps back to all sources.
    groups = {}
    for name, seq in load_ape(use_case):
        groups.setdefault(seq, []).append(("ape", name))
    llm, skipped = load_llm(use_case)
    for source, model, seq in llm:
        groups.setdefault(seq, []).append((model, source))

    # Count files on disk, not what the loaders returned: every CWL file and
    # every run file must end up either in a group or in skipped.
    n_files = (len(list((RESULTS_DIR / use_case / "CWL").glob("*.cwl")))
               + len(list((RESULTS_DIR / use_case / "llm").glob("*/*/run*.txt"))))
    n_accounted = sum(len(sources) for sources in groups.values()) + len(skipped)
    assert n_accounted == n_files, f"{use_case}: {n_accounted} accounted vs {n_files} files"
    return groups, skipped

def assign_ids(use_case, groups):
    # Sort first so the shuffle doesn't depend on load order, then shuffle
    # with a fixed seed: rows end up in an order that says nothing about the
    # source system, and rerunning gives exactly the same IDs.
    sequences = sorted(groups)
    random.Random(f"{SHUFFLE_SEED}-{use_case}").shuffle(sequences)
    prefix = "N" + use_case[2:]
    return [(f"{prefix}-{i:02d}", seq, groups[seq]) for i, seq in enumerate(sequences, start=1)]

def write_key(all_rows, all_skipped):
    # Private key: maps every source file to the sheet row it was rated
    # under. Never sent to raters. Skipped (UNSAT) runs are listed with no
    # row_id so every one of the files is accounted for.
    RATING_DIR.mkdir(parents=True, exist_ok=True)
    path = RATING_DIR / "rating_key.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["row_id", "use_case", "system", "source", "sequence"])
        for use_case, rows in all_rows.items():
            for row_id, seq, sources in rows:
                for system, source in sources:
                    writer.writerow([row_id, use_case, system, source, " -> ".join(seq)])
        for use_case, skipped in all_skipped.items():
            for source in skipped:
                model = source.split("/")[1]
                writer.writerow(["", use_case, model, source, "UNSAT (no workflow)"])
    return path

if __name__ == "__main__":
    all_rows, all_skipped = {}, {}
    for uc in USE_CASES:
        groups, all_skipped[uc] = collect(uc)
        all_rows[uc] = assign_ids(uc, groups)
    key_path = write_key(all_rows, all_skipped)
    print("wrote", key_path)
