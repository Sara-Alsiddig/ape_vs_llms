import json
import re
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JAR = REPO_ROOT / "ape" / "APE-2.6.0-executable.jar"
CONFIGS_DIR = REPO_ROOT / "ape" / "configs"
OUT_PATH = REPO_ROOT / "results" / "ape_timing.json"

USE_CASES = ["no1", "no2", "no3", "no4"]
NUM_RERUNS = 5  # same as the LLM runs

def time_run(use_case, work_dir):
    # Runs APE once on a copy of the committed config whose output goes to
    # work_dir, so results/noX (the rated CWL set) is never overwritten.
    # /usr/bin/time -l (macOS) reports wall time and peak memory on stderr.
    config = json.loads((CONFIGS_DIR / f"{use_case}_config.json").read_text())
    config["solutions_dir_path"] = str(work_dir / use_case)
    config_path = work_dir / f"{use_case}_config.json"
    config_path.write_text(json.dumps(config))
    proc = subprocess.run(
        ["/usr/bin/time", "-l", "java", "-jar", str(JAR), str(config_path)],
        capture_output=True, text=True, cwd=work_dir, check=True,
    )
    seconds = float(re.search(r"([\d.]+) real", proc.stderr).group(1))
    max_rss = int(re.search(r"(\d+)\s+maximum resident set size", proc.stderr).group(1))
    return {"seconds": seconds, "max_rss_mb": round(max_rss / 1e6, 1)}

if __name__ == "__main__":
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for use_case in USE_CASES:
            for run in range(1, NUM_RERUNS + 1):
                row = {"use_case": use_case, "run": run, **time_run(use_case, Path(tmp))}
                rows.append(row)
                print(row)
    OUT_PATH.write_text(json.dumps(rows, indent=2))
    print(f"wrote {OUT_PATH}")
