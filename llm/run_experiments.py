import json
from pathlib import Path
from prompt_builder import build_prompt
from runners import call_claude, call_chatgpt

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"

USE_CASES = ["No1", "No2", "No3", "No4"]
VARIANTS = ["json", "nl"]
MODELS = {"claude": call_claude, "chatgpt": call_chatgpt}
NUM_RERUNS = 5

def run_all():
    for use_case in USE_CASES:
        for variant in VARIANTS:
            prompt = build_prompt(use_case, variant=variant)
            for model_name, call_fn in MODELS.items():
                out_dir = RESULTS_DIR / use_case.lower() / "llm" / variant / model_name
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
    run_all()
