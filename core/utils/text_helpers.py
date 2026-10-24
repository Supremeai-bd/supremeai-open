def strip_markdown_code_block(text: str) -> str:
    """
    AI response থেকে ```python ... ``` markdown wrapper সরায়।
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) > 1:
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines).strip()
