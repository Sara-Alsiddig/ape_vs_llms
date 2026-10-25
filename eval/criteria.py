import json
from collections import Counter

from build_rating_sheet import RESULTS_DIR, USE_CASES, parse_llm_response, graph_to_sequence
from tool_catalog import load_tools
from isomorphism_checker import check_llm_against_ape
from graph_adapters import llm_json_to_graph
from prompt_builder import load_spec

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
                "meta": json.loads(p.with_name(f"{p.stem}.meta.json").read_text()),
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
    # None for UNSAT or unparsed answers - (whether an UNSAT verdict agrees
    # with APE's is a separate column step 6)).
    if response is None or response["unsatisfiable"]:
        return None
    return check_llm_against_ape(response, RESULTS_DIR / use_case / "CWL")["matched"]

def n_steps(response):
    # Number of tools in the workflow; None when there is no workflow.
    if response is None or response["unsatisfiable"]:
        return None
    return len(response["steps"])

def type_ancestors(tools):
    # Every data/format term in the tool catalog mapped to its EDAM
    # ancestors (domain_ref stores them per term inside the tool slots).
    ancestors = {}
    for tool in tools:
        for slot in tool["inputs"] + tool["outputs"]:
            for term in slot["data"] + slot["format"]:
                ancestors[term["id"]] = {a["id"] for a in term["ancestors"]}
    return ancestors

def slot_ids(slot):
    # A catalog slot as (data ids, format ids) the same shape as a spec slot.
    return [t["id"] for t in slot["data"]], [t["id"] for t in slot["format"]]

def fits(source, target, ancestors):
    # The rule the LLMs were given, and how APE connects types: for data and
    # for format, some pair of terms is equal or one is an ancestor of the other.
    def related(a, b):
        return a == b or a in ancestors.get(b, ()) or b in ancestors.get(a, ())
    return all(any(related(a, b) for a in s for b in t) for s, t in zip(source, target))

def type_chain(response, use_case, tools_by_id, ancestors):
    # True if every input slot of every step can be fed by the workflow input
    # or by an output of a step in its "in", and the last step(s) can produce
    # the required output. None when there is no workflow.
    if response is None or response["unsatisfiable"]:
        return None
    spec = load_spec(use_case)
    workflow_inputs = [(s["data_0006"], s["format_1915"]) for s in spec["inputs"]]
    graph = llm_json_to_graph(response)
    for node in graph.nodes:
        offered = workflow_inputs + [
            slot_ids(out) for pred in graph.predecessors(node)
            for out in tools_by_id[graph.nodes[pred]["tool"]]["outputs"]]
        for slot in tools_by_id[graph.nodes[node]["tool"]]["inputs"]:
            if not any(fits(o, slot_ids(slot), ancestors) for o in offered):
                return False
    last_steps = [n for n in graph.nodes if graph.out_degree(n) == 0]
    for required in spec["outputs"]:
        target = (required["data_0006"], required["format_1915"])
        if not any(fits(slot_ids(out), target, ancestors) for n in last_steps
                   for out in tools_by_id[graph.nodes[n]["tool"]]["outputs"]):
            return False
    return True

def claims_unsat(response):
    # The LLM's own verdict; None when the answer didn't parse.
    if response is None:
        return None
    return response["unsatisfiable"]

def ape_unsat(use_case):
    # APE writes CWL candidates only when it finds solutions, so no CWL
    # folder means APE certified the spec UNSAT (No2 in our use cases).
    return not (RESULTS_DIR / use_case / "CWL").exists()

def workflow_key(response):
    # The tool sequence, so identical workflows from different runs compare
    # equal (same notion of "same workflow" as the rating sheet). None when
    # there is no workflow.
    if response is None or response["unsatisfiable"]:
        return None
    return graph_to_sequence(llm_json_to_graph(response))

def usage(meta):
    # Provider-neutral token counts. Anthropic reports cache reads apart from
    # input_tokens; OpenAI's input_tokens already includes the cached ones.
    u = meta["usage"]
    if "cache_read_input_tokens" in u:  # Anthropic
        cached = u["cache_read_input_tokens"]
        total_input = u["input_tokens"] + cached + u["cache_creation_input_tokens"]
        reasoning = u["output_tokens_details"]["thinking_tokens"]
    else:  # OpenAI
        cached = u["input_tokens_details"]["cached_tokens"]
        total_input = u["input_tokens"]
        reasoning = u["output_tokens_details"]["reasoning_tokens"]
    return {"input": total_input, "cached_input": cached, "output": u["output_tokens"],
            "reasoning": reasoning, "seconds": meta["seconds"]}



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
    for r in runs:
        r["n_steps"] = n_steps(r["response"])
    for use_case in USE_CASES:
        counts = Counter((r["system"], r["n_steps"]) for r in runs if r["use_case"] == use_case)
        print(f"n_steps {use_case}: {dict(counts)}")
    tools = load_tools()
    tools_by_id = {t["id"]: t for t in tools}
    ancestors = type_ancestors(tools)
    for r in runs:
        r["type_chain"] = type_chain(r["response"], r["use_case"], tools_by_id, ancestors)
    for use_case in USE_CASES:
        counts = Counter(r["type_chain"] for r in runs if r["use_case"] == use_case)
        print(f"type_chain {use_case}: {dict(counts)}")
    for r in runs:
        r["claims_unsat"] = claims_unsat(r["response"])
    verdicts = Counter(
        (r["system"], r["variant"],
        "APE UNSAT" if ape_unsat(r["use_case"]) else "APE SAT",
        {True: "LLM UNSAT", False: "LLM workflow", None: "invalid"}[r["claims_unsat"]])
        for r in runs)
    print("UNSAT behaviour:")
    for key in sorted(verdicts):
        print(f"  {key}: {verdicts[key]}")

    for r in runs:
        r["workflow"] = workflow_key(r["response"])
    print("Variance (5 runs per cell):")
    for use_case in USE_CASES:
        for variant in ("json", "nl"):
            for system in ("claude", "chatgpt"):
                cell = [r for r in runs if (r["use_case"], r["variant"], r["system"]) == (use_case, variant, system)]
                distinct = {r["workflow"] for r in cell if r["workflow"] is not None}
                in_ape = {r["workflow"] for r in cell if r["ape_match"]}
                print(f"  {use_case} {variant:4} {system:7}: {len(distinct)} distinct, {len(in_ape)} in APE's 25")
        for r in runs:
            r["usage"] = usage(r["meta"])
    print("LLM usage, mean per run (tokens are not comparable across providers):")
    for system in ("claude", "chatgpt"):
        for variant in ("json", "nl"):
            cell = [r["usage"] for r in runs if (r["system"], r["variant"]) == (system, variant)]
            mean = {k: round(sum(u[k] for u in cell) / len(cell), 1) for k in cell[0]}
            print(f"  {system:7} {variant:4} ({len(cell)} runs): {mean}")
