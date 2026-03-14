"""
Summarization via Claude, and converting summary text to HTML.
"""

from pathlib import Path
import anthropic

PROMPT_TEMPLATE = (Path(__file__).parent / "prompt.txt").read_text()


def format_summary_html(text: str) -> str:
    """Convert 'lead sentence\n- bullet\n- bullet' text into HTML."""
    lead = ""
    bullets = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(("-", "•", "*")):
            bullets.append(line.lstrip("-•* ").strip())
        elif not lead:
            lead = line
    html = f'<p class="summary-lead">{lead}</p>' if lead else ""
    if bullets:
        items_html = "".join(f"<li>{b}</li>" for b in bullets)
        html += f'<ul class="summary-bullets">{items_html}</ul>'
    return html or f'<p class="summary-lead">{text}</p>'


def summarize(client: anthropic.Anthropic, title: str, content: str, sentences: int, source_type: str, stack: str = "", interests: str = "") -> str:
    """Call Claude to produce a short summary."""
    if not content or len(content.strip()) < 50:
        return "No content available to summarize."

    prompt = PROMPT_TEMPLATE.format(source_type=source_type, title=title, content=content, sentences=sentences, stack=stack, interests=interests)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
