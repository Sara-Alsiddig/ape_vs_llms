import anthropic
import openai
import time

CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_EFFORT = "medium"
CLAUDE_MAX_TOKENS = 20000  

OPENAI_MODEL = "gpt-6-astra" 
OPENAI_EFFORT = "medium"
OPENAI_MAX_TOKENS = 20000  

claude_client = anthropic.Anthropic()
openai_client = openai.OpenAI()

def call_claude(prompt):
    start = time.perf_counter()
    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        output_config={"effort": CLAUDE_EFFORT},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((block.text for block in response.content if block.type == "text"), "")
    meta = {
        "model": response.model,
        "stop_reason": response.stop_reason,
        "usage": response.usage.model_dump(),
        "seconds": round(time.perf_counter() - start, 2),
    }
    return text, meta

def call_chatgpt(prompt):
    start = time.perf_counter()
    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        max_output_tokens=OPENAI_MAX_TOKENS,
        input=[{"role": "user", "content": prompt}],
        reasoning={"effort": OPENAI_EFFORT, "mode": "standard", "summary": "auto"},
        text={"format": {"type": "text"}, "verbosity": "medium"},
    )
    meta = {
        "model": response.model,
        "status": response.status,
        "usage": response.usage.model_dump(),
        "seconds": round(time.perf_counter() - start, 2),
    }
    return response.output_text, meta

