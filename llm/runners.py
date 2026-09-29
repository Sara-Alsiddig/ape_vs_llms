import anthropic
import openai

CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_EFFORT = "medium"
CLAUDE_MAX_TOKENS = 10000  

OPENAI_MODEL = "gpt-6-astra" 
OPENAI_EFFORT = "medium"
OPENAI_MAX_TOKENS = 10000  

claude_client = anthropic.Anthropic()
openai_client = openai.OpenAI()

def call_claude(prompt):
    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        output_config={"effort": CLAUDE_EFFORT},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""

def call_chatgpt(prompt):
    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=[{"role": "user", "content": prompt}],
        reasoning={"effort": OPENAI_EFFORT, "mode": "standard", "summary": "auto"},
        text={"format": {"type": "text"}, "verbosity": "medium"},
    )
    return response.output_text

