import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MASS_SPEC_DIR = REPO_ROOT / "ape/APE_UseCases/MassSpectometry"
SPECS_DIR = REPO_ROOT / "specs"
CONFIGS_DIR = REPO_ROOT / "ape/configs"
RESULTS_DIR = REPO_ROOT / "results"

DOMAIN_FIXED = {
    "ontology_path": str(MASS_SPEC_DIR / "edam.owl"),
    "ontologyPrefixIRI": "http://edamontology.org/",
    "toolsTaxonomyRoot": "operation_0004",
    "dataDimensionsTaxonomyRoots": ["data_0006", "format_1915"],
    "tool_annotations_path": str(MASS_SPEC_DIR / "bio.tools_fragment.json"),
    "strict_tool_annotations": "true",
}

RUN_SETTINGS = {
    "timeout_sec": "120",
    "solutions": "1000",
    "number_of_execution_scripts": "0",
    "number_of_generated_graphs": "25",
    "number_of_cwl_files": "25",
    "debug_mode": "true",
    "use_workflow_input": "all",
    "use_all_generated_data": "all",
    "tool_seq_repeat": "false",
}

def build_config(use_case_id):
    spec_path = SPECS_DIR / f"{use_case_id.lower()}.json"
    with open(spec_path) as f:
        spec = json.load(f)

    config = {
        **DOMAIN_FIXED,
        **RUN_SETTINGS,
        "inputs": spec["inputs"],
        "outputs": spec["outputs"],
        "solution_length": spec["solution_length"],
        "constraints": spec["constraints"],
        "solutions_dir_path": str(RESULTS_DIR / use_case_id.lower()),
    }
    return config

CONFIGS_DIR.mkdir(exist_ok=True)

for i in range(1, 5):
    use_case_id = f"No{i}"
    config = build_config(use_case_id)
    output_path = CONFIGS_DIR / f"{use_case_id.lower()}_config.json"
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"wrote {output_path}")