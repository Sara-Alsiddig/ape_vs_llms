import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
def extract_spec(use_case_id):
    use_case_dir = REPO_ROOT / f"ape/APE_UseCases/MassSpectometry/{use_case_id}"
    config_path = use_case_dir / "config_original.json"
    constraints_path = use_case_dir / f"constraints_{use_case_id.lower()}.json"

    with open(config_path) as f:
        config = json.load(f)
    with open(constraints_path) as f:
        constraints_file = json.load(f)
        
    return {
        "id": use_case_id,
        "inputs": config["inputs"],
        "outputs": config["outputs"],
        "solution_length": config["solution_length"],
        "constraints": constraints_file["constraints"],
    }
    
SPECS_DIR = Path(__file__).resolve().parent

for i in range(1, 5):
    use_case_id = f"No{i}"
    spec = extract_spec(use_case_id)
    output_path = SPECS_DIR / f"{use_case_id.lower()}.json"
    with open(output_path, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"wrote {output_path}")