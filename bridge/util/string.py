def add_quote(text: str, from_line: int = 0) -> str:
    lines = text.splitlines()
    for i in range(from_line, len(lines), 1):
        lines[i] = f'> {lines[i]}'
    return '\n'.join(lines)
