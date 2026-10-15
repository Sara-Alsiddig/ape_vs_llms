import json
from collections import Counter

from build_rating_sheet import RESULTS_DIR, USE_CASES, parse_llm_response
from tool_catalog import load_tools
from isomorphism_checker import check_llm_against_ape

def is_fenced(text):
    # Same fence rule parse_llm_response strips: first line ```json or ```,
    # last line ```. Recorded separately so we can decide later whether a
    # fenced answer counts as "valid JSON output".
    lines = text.strip().splitlines()
    return lines[0] in ("```json", "```") and lines[-1] == "```"

def load_runs():
    # One dict per LLM run file. A response that doesn't parse is kept
    # (response=None, parse_error=message) rather than crashing the script.
    rows = []
    for use_case in USE_CASES:
        for p in sorted((RESULTS_DIR / use_case / "llm").glob("*/*/run*.txt")):
            text = p.read_text()
            row = {
                "use_case": use_case,
                "variant": p.parent.parent.name,
                "system": p.parent.name,
                "run": int(p.stem.removeprefix("run")),
                "fenced": is_fenced(text),
                "response": None,
                "parse_error": None,
            }
            try:
                row["response"] = parse_llm_response(text)
            except json.JSONDecodeError as e:
                row["parse_error"] = str(e)
            rows.append(row)
    return rows

def grounded(response, tool_ids):
    # True if every step uses a tool from the domain. None when there is
    # nothing to check: an UNSAT answer, or a response that didn't parse.
    if response is None or response["unsatisfiable"]:
        return None
    return all(step["tool"] in tool_ids for step in response["steps"])

def ape_match(response, use_case):
    # True if the workflow is isomorphic to one of APE's 25 candidates.
    # None for UNSAT or unparsed answers -- whether an UNSAT verdict agrees
    # with APE's is a separate column (step 6).
    if response is None or response["unsatisfiable"]:
        return None
    return check_llm_against_ape(response, RESULTS_DIR / use_case / "CWL")["matched"]


if __name__ == "__main__":
    runs = load_runs()
    print(f"{len(runs)} runs")
    fenced = Counter(r["system"] for r in runs if r["fenced"])
    print(f"{sum(fenced.values())} fenced: {dict(fenced)}")
    print(f"{sum(r['parse_error'] is not None for r in runs)} parse errors")
    tool_ids = {tool["id"] for tool in load_tools()}
    for r in runs:
        r["grounded"] = grounded(r["response"], tool_ids)
    print(f"grounded: {Counter(r['grounded'] for r in runs)}")
    for r in runs:
        r["ape_match"] = ape_match(r["response"], r["use_case"])
    for use_case in USE_CASES:
        counts = Counter(r["ape_match"] for r in runs if r["use_case"] == use_case)
        print(f"ape_match {use_case}: {dict(counts)}")