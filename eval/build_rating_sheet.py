import json
import sys
import networkx as nx
from collections import Counter
import random
import csv
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
sys.path.insert(0, str(REPO_ROOT / "checker"))

from graph_adapters import cwl_to_graph,  llm_json_to_graph
sys.path.insert(0, str(REPO_ROOT / "llm"))
from prompt_builder import load_spec, constraint_to_sentence
from tool_catalog import load_term_labels, load_tools

RATING_DIR = REPO_ROOT / "eval" / "rating"

USE_CASES = ["no1", "no2", "no3", "no4"]
SHUFFLE_SEED = 2026  # fixed so IDs are identical on every run

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
    # (source, model, tool_sequence); skipped lists (source, reason) for runs with no workflow
    # to rate: UNSAT answers and answers that aren't valid JSON.
    workflows, skipped = [], []
    for p in sorted((RESULTS_DIR / use_case / "llm").glob("*/*/run*.txt")):
        variant, model = p.parent.parent.name, p.parent.name
        source = f"{variant}/{model}/{p.name}"
        try:
            response = parse_llm_response(p.read_text())
        except json.JSONDecodeError:
            skipped.append((source, "invalid JSON (not rated)"))
            continue
        if response["unsatisfiable"]:
            skipped.append((source, "unsatisfiable (not rated)"))
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
    # under. Never sent to raters. Skipped runs (UNSAT or invalid JSON) 
    # are listed with no row_id.
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
            for source, reason in skipped:
                model = source.split("/")[1]
                writer.writerow(["", use_case, model, source, reason])
    return path

ANY_FORMAT = "format_1915"  # EDAM root: the spec accepts any format

def slot_text(slot, term_labels):
    data = " or ".join(term_labels[d] for d in slot["data_0006"])
    formats = [f for f in slot["format_1915"] if f != ANY_FORMAT]
    fmt = " or ".join(term_labels[f] for f in formats) if formats else "any format"
    return f"{data} (format: {fmt})"

def task_context(use_case):
    # Same scenario text and constraint sentences the LLMs got in the NL
    # prompt variant, so raters judge against exactly the same task.
    spec = load_spec(use_case)
    term_labels = load_term_labels()
    # data_0945's current EDAM label is "Peptide identification"; Lamprecht
    # et al. 2019 use its exact synonym "Protein identification". Show both so
    # raters who know the paper recognise the term. Sheet only, prompts unchanged.
    term_labels["data_0945"] = "Peptide/Protein identification"
    tools_by_id = {t["id"]: t for t in load_tools()}
    return {
        "scenario": spec["nl_description"],
        "inputs": [slot_text(s, term_labels) for s in spec["inputs"]],
        "outputs": [slot_text(s, term_labels) for s in spec["outputs"]],
        "constraints": [constraint_to_sentence(c, term_labels, tools_by_id) for c in spec["constraints"]],
    }

def tool_labels():
    return {t["id"]: t["label"] for t in load_tools()}
# Rating scale verbatim from APE in the Wild (Kasalica et al. 2021,
# J Proteome Res 20(4):2157-2165, doi:10.1021/acs.jproteome.0c00983).
SCALE = [
    (0, "I know that it will not work"),
    (1, "Might work, but does not seem very useful or has unnecessary steps"),
    (2, "Interesting suggestion, seems viable, could work, worth trying"),
    (3, "Good workflow, have seen it or similar before, I know it will work"),
]
TEXT_WIDTH = 100  # width of column B, in characters

def wrapped(cell, text):
    cell.value = text
    cell.alignment = Alignment(wrap_text=True, vertical="top")

def fit_height(ws, row, text):
    # openpyxl can't auto-fit row heights, so estimate from text length.
    lines = len(text) // TEXT_WIDTH + 1
    ws.row_dimensions[row].height = 15 * lines

def write_sheet(all_rows):
    labels = tool_labels()
    wb = Workbook()

    info = wb.active
    info.title = "Instructions"
    info["A1"] = "Workflow plausibility rating"
    info["A1"].font = Font(bold=True, size=14)
    intro = ("Each tab describes one data-analysis task, followed by candidate workflows "
             "for it. Please rate how plausible each workflow is as a solution to that "
             "task, using the scale below. Comments are optional but very welcome.")
    wrapped(info["B3"], intro)
    fit_height(info, 3, intro)
    info["A5"], info["B5"] = "Score", "Meaning"
    info["A5"].font = info["B5"].font = Font(bold=True)
    for i, (score, meaning) in enumerate(SCALE, start=6):
        info.cell(i, 1, score)
        wrapped(info.cell(i, 2), meaning)
    info.column_dimensions["A"].width = 12
    info.column_dimensions["B"].width = TEXT_WIDTH

    for use_case, rows in all_rows.items():
        ws = wb.create_sheet(title="No" + use_case[2:])
        ctx = task_context(use_case)
        context = ([("Task", ctx["scenario"]),
                    ("Input", "; ".join(ctx["inputs"])),
                    ("Output", "; ".join(ctx["outputs"]))]
                   + [("Constraint", c) for c in ctx["constraints"]])
        for label, text in context:
            ws.append([label])
            ws.cell(ws.max_row, 1).font = Font(bold=True)
            wrapped(ws.cell(ws.max_row, 2), text)
            fit_height(ws, ws.max_row, text)

        ws.append([])
        ws.append(["ID", "Workflow", "Rating (0-3)", "Comment"])
        header_row = ws.max_row
        for cell in ws[header_row]:
            cell.font = Font(bold=True)

        # Sources are deliberately left out: they only live in the key file.
        for row_id, seq, _sources in rows:
            ws.append([row_id, " → ".join(labels[t] for t in seq)])

        rating_check = DataValidation(type="whole", operator="between",
                                    formula1="0", formula2="3", showErrorMessage=True,
                                    error="Please enter a whole number from 0 to 3.")
        ws.add_data_validation(rating_check)
        rating_check.add(f"C{header_row + 1}:C{ws.max_row}")

        ws.freeze_panes = ws.cell(header_row + 1, 1)
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = TEXT_WIDTH
        ws.column_dimensions["C"].width = 14
        ws.column_dimensions["D"].width = 50

    path = RATING_DIR / "rating_sheet.xlsx"
    wb.save(path)
    return path

if __name__ == "__main__":
    all_rows, all_skipped = {}, {}
    for uc in USE_CASES:
        groups, all_skipped[uc] = collect(uc)
        all_rows[uc] = assign_ids(uc, groups)
    key_path = write_key(all_rows, all_skipped)
    print("wrote", key_path)
    sheet_path = write_sheet(all_rows)
    print("wrote", sheet_path)
