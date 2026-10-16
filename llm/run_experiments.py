import json
import sys
from pathlib import Path
from prompt_builder import build_prompt
from runners import call_claude, call_chatgpt

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"

USE_CASES = ["No1", "No2", "No3", "No4"]
VARIANTS = ["json", "nl"]
MODELS = {"claude": call_claude, "chatgpt": call_chatgpt}
NUM_RERUNS = 5

def run_all(use_cases=USE_CASES, variants=VARIANTS, results_dir=RESULTS_DIR):
    for use_case in use_cases:
        for variant in variants:
            prompt = build_prompt(use_case, variant=variant)
            for model_name, call_fn in MODELS.items():
                out_dir = results_dir / use_case.lower() / "llm" / variant / model_name
                out_dir.mkdir(parents=True, exist_ok=True)
                for run in range(1, NUM_RERUNS + 1):
                    out_path = out_dir / f"run{run}.txt"
                    if out_path.exists():
                        print(f"skipping {out_path} (already exists)")
                        continue
                    response = call_fn(prompt)
                    with open(out_path, "w") as f:
                        f.write(response)
                    print(f"wrote {out_path}")

if __name__ == "__main__":
    if sys.argv[1:] == ["sensitivity_prev_m"]:
        # Re-run only the NL variant of the specs that contain prev_m, with the
        # corrected wording, into a separate folder -- v2 results stay untouched.
        run_all(["No2", "No3", "No4"], ["nl"], RESULTS_DIR / "sensitivity_prev_m")
    else:
        run_all()