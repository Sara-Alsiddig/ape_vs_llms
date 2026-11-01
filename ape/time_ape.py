import json
import re
import subprocess
import tempfile
import time
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
    start = time.perf_counter()
    proc = subprocess.Popen(
        ["/usr/bin/time", "-l", "java", "-jar", str(JAR), str(config_path)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=work_dir,
    )
    first, first_25, log = None, None, []
    for line in proc.stdout:
        log.append(line)
        found = re.search(r"Found (\d+) solutions", line)
        if found:
            n = int(found.group(1))
            elapsed = round(time.perf_counter() - start, 1)
            if first is None and n >= 1:
                first = elapsed
            if first_25 is None and n >= 25:
                first_25 = elapsed
    if proc.wait() != 0:
        raise subprocess.CalledProcessError(proc.returncode, proc.args)
    output = "".join(log)

    
    seconds = float(re.search(r"([\d.]+) real", output).group(1))
    max_rss = int(re.search(r"(\d+)\s+maximum resident set size", output).group(1))
    return {"seconds": seconds, "max_rss_mb": round(max_rss / 1e6, 1), "first_solution_s": first, "first_25_s": first_25}

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
