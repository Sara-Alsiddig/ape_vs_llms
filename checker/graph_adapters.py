"""Normalize APE's CWL output and the LLM's custom JSON output into the same
networkx DiGraph shape, so both can be compared with graph isomorphism.

Only two facts survive into the graph: which tool ID is at each step, and
which step's output feeds which step's input. Everything else (CWL's
cwlVersion/doc/run-path boilerplate, arbitrary step-id naming) is scaffolding
that isomorphism doesn't compare, so it's dropped during parsing.
"""

import networkx as nx
import yaml

CWL_RUN_PREFIX = "add-path-to-the-implementation/"
CWL_RUN_SUFFIX = ".cwl"


def _tool_id_from_cwl_run(run_value):
    run_value = run_value.strip()
    if run_value.startswith(CWL_RUN_PREFIX):
        run_value = run_value[len(CWL_RUN_PREFIX):]
    if run_value.endswith(CWL_RUN_SUFFIX):
        run_value = run_value[: -len(CWL_RUN_SUFFIX)]
    return run_value


def cwl_to_graph(cwl_path):
    with open(cwl_path) as f:
        doc = yaml.safe_load(f)

    graph = nx.DiGraph()
    steps = doc.get("steps", {})

    for step_id, step_def in steps.items():
        tool_id = _tool_id_from_cwl_run(step_def["run"])
        graph.add_node(step_id, tool=tool_id)

    for step_id, step_def in steps.items():
        for source in step_def.get("in", {}).values():
            if "/" in source:
                upstream_step = source.split("/")[0]
                graph.add_edge(upstream_step, step_id)

    return graph


def llm_json_to_graph(workflow):
    graph = nx.DiGraph()
    step_ids = {step["id"] for step in workflow["steps"]}

    for step in workflow["steps"]:
        graph.add_node(step["id"], tool=step["tool"])

    for step in workflow["steps"]:
        for source in step.get("in", []):
            if source in step_ids:
                graph.add_edge(source, step["id"])

    return graph


def graphs_match(graph_a, graph_b):
    return nx.is_isomorphic(
        graph_a, graph_b, node_match=lambda a, b: a["tool"] == b["tool"]
    )
