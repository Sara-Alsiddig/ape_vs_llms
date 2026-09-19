import json
from pathlib import Path
from tool_catalog import load_term_labels, catalog_text

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "specs"

TASK_FRAMING = """
You are designing a computational workflow for a proteomics data-analysis task. You will be given:
(1) a natural-language description of the scientific scenario,
(2) the required input and output data types,
(3) a set of constraints the workflow must satisfy,
(4) a catalog of the exact tools available to you.

Design a workflow — an ordered sequence of tool invocations connected by data flow — that solves
the task using only the tools provided in the catalog below.
"""

CATALOG_READING_NOTES = """
Each tool below is listed with the operation(s) it performs and its required input/output slots.
A tool's "operations" list describes everything that tool is known to do — it performs all of
them together as one step, not a menu to choose from. Within one input or output slot, multiple
listed data/format options are alternatives — any one of them satisfies that slot, not all of
them at once. A tool with multiple separate input slots requires all of those slots to be
satisfied simultaneously (see rule above on multi-input steps).
"""

OUTPUT_SCHEMA_INSTRUCTIONS = """
Respond with a JSON object describing your workflow, using exactly this schema:

{
  "steps": [
    {"id": "step1", "tool": "<tool id>", "in": []},
    {"id": "step2", "tool": "<tool id>", "in": []},
    {"id": "step3", "tool": "<tool id>", "in": ["step1", "step2"]}
  ]
}

Rules:
- Each step must have a unique "id".
- "tool" must be one of the exact tool IDs listed in the catalog above (e.g. "comet", "msconvert") — do not invent tool IDs or substitute a tool's label for its id.
- "in" lists the ids of steps whose output feeds into this step. A step that consumes the workflow's initial input (nothing upstream) has an empty "in" list. A step can list more than one id in "in" when the tool it uses requires multiple inputs at once (e.g. step3 above, using a tool that needs both step1's and step2's outputs) — list every upstream step it depends on, not just one.
- Respond with only the JSON object — no extra commentary.
"""


def load_spec(use_case_id):
    spec_path = SPECS_DIR / f"{use_case_id.lower()}.json"
    with open(spec_path) as f:
        return json.load(f)
    
def term_obj(short_id, term_labels):
    return {"id": short_id, "label": term_labels.get(short_id)}

def format_slot(slot, term_labels):
    return {
        "data": [term_obj(i, term_labels) for i in slot["data_0006"]],
        "format": [term_obj(i, term_labels) for i in slot["format_1915"]],
    }

def format_requirement(spec, term_labels):
    return {
        "inputs": [format_slot(slot, term_labels) for slot in spec["inputs"]],
        "outputs": [format_slot(slot, term_labels) for slot in spec["outputs"]],
    }
    
def build_prompt(use_case_id):
    spec = load_spec(use_case_id)
    term_labels = load_term_labels()
    requirement = format_requirement(spec, term_labels)

    sections = [
        TASK_FRAMING,
        "## Scenario\n" + spec["nl_description"],
        "## Required Input/Output\n" + json.dumps(requirement, indent=2),
        "## Constraints\n" + json.dumps(spec["constraints"], indent=2),
        "## Available Tools\n" + CATALOG_READING_NOTES + "\n" + catalog_text(),
        "## Output Format\n" + OUTPUT_SCHEMA_INSTRUCTIONS,
    ]
    return "\n\n".join(sections)
