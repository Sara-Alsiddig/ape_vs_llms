import hashlib
import json
from pathlib import Path
from collections import defaultdict

from rdflib import RDFS, Graph, URIRef

REPO_ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY_PATH = REPO_ROOT / "ape/APE_UseCases/MassSpectometry/edam.owl"
TOOL_ANNOTATIONS_PATH = REPO_ROOT / "ape/APE_UseCases/MassSpectometry/bio.tools_fragment.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "domain_ref.json"

with open(TOOL_ANNOTATIONS_PATH) as f:
    tool_annotations = json.load(f)
g = Graph()
g.parse(str(ONTOLOGY_PATH))

# Skip blank-node objects: rdfs:subClassOf can point at anonymous
# property restrictions, not just real parent classes.
edges = [
    (child, parent)
    for child, parent in g.subject_objects(RDFS.subClassOf)
    if isinstance(child, URIRef) and isinstance(parent, URIRef)
]

children_of = defaultdict(list)
for child, parent in edges:
    children_of[parent].append(child)

def closure(root):
    # BFS over subClassOf edges. Deprecated terms are excluded
    # automatically: EDAM reparents them under owl:DeprecatedClass,
    # so they're unreachable from a real taxonomy root.
    visited = {root}
    frontier = [root]
    while frontier:
        node = frontier.pop()
        for child in children_of[node]:
            if child not in visited:
                visited.add(child)
                frontier.append(child)
    return visited

data_terms = closure(URIRef("http://edamontology.org/data_0006"))

assert URIRef("http://edamontology.org/data_0943") in data_terms  # No1 input
assert URIRef("http://edamontology.org/data_2016") in data_terms  # No1 output
assert URIRef("http://edamontology.org/data_0835") not in data_terms  # deprecated, must be excluded

format_terms = closure(URIRef("http://edamontology.org/format_1915"))
operation_terms = closure(URIRef("http://edamontology.org/operation_0004"))

def short_id(uri):
    # EDAM term URIs are always "http://edamontology.org/<id>";
    # keep just the <id> part for readability.
    return str(uri).rsplit("/", 1)[-1]

tool_ids = sorted(t["id"] for t in tool_annotations["functions"])
data_ids = sorted(short_id(t) for t in data_terms)
format_ids = sorted(short_id(t) for t in format_terms)
operation_ids = sorted(short_id(t) for t in operation_terms)

# Human-readable labels for EDAM terms, needed for a readable tool catalog.
# Looked up over every term in the ontology, not just data_terms |
# format_terms | operation_terms: a term can be deprecated (correctly
# excluded from those domain-validity sets by closure()) while still
# needing a label -- e.g. a tool annotation can reference a now-deprecated
# term. IDs are unique across data/format/operation, so one merged dict is safe.
term_labels = {}
for term, label in g.subject_objects(RDFS.label):
    if isinstance(term, URIRef) and str(term).startswith("http://edamontology.org/"):
        term_labels[short_id(term)] = str(label)

def file_hash(path):
    # Content hash lets domain_ref.json record exactly which source
    # files it was built from, for reproducibility.
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

metadata = {
    "source_files": {
        "ontology_path": str(ONTOLOGY_PATH.relative_to(REPO_ROOT)),
        "tool_annotations_path": str(TOOL_ANNOTATIONS_PATH.relative_to(REPO_ROOT)),
    },
    "source_hashes": {
        "edam_owl_sha256": file_hash(ONTOLOGY_PATH),
        "bio_tools_fragment_sha256": file_hash(TOOL_ANNOTATIONS_PATH),
    },
    "taxonomy_roots": {
        "tools": "operation_0004",
        "data": "data_0006",
        "format": "format_1915",
    },
    "counts": {
        "tools": len(tool_ids),
        "data_terms": len(data_ids),
        "format_terms": len(format_ids),
        "operation_terms": len(operation_ids),
        "term_labels": len(term_labels),
    },
}

domain_ref = {
    "metadata": metadata,
    "tools": tool_ids,
    "data_terms": data_ids,
    "format_terms": format_ids,
    "operation_terms": operation_ids,
    "term_labels": term_labels, 
}

with open(OUTPUT_PATH, "w") as f:
    json.dump(domain_ref, f, indent=2)
