import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAIN_REF_PATH = REPO_ROOT / "domain_ref" / "domain_ref.json"

def load_tools():
    with open(DOMAIN_REF_PATH) as f:
        domain_ref = json.load(f)
    return domain_ref["tools"]

def load_term_labels():
    with open(DOMAIN_REF_PATH) as f:
        domain_ref = json.load(f)
    return domain_ref["term_labels"]

def catalog_text():
    tools = load_tools()
    return json.dumps(tools, indent=2)