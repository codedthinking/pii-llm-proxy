import re

from .session import Session


def desanitize_text(text: str, session: Session) -> str:
    if not session.hash_to_pii:
        return text

    escaped_hashes = [re.escape(h) for h in session.hash_to_pii]
    hash_alt = "|".join(escaped_hashes)

    # First pass: replace full <redacted .../> tags (match any hash= value)
    tag_pattern = re.compile(r'<redacted\s+hash="([^"]*)"\s+type="[^"]*"\s*/>')

    def _replace_tag(m: re.Match) -> str:
        hash_val = m.group(1)
        return session.hash_to_pii.get(hash_val, m.group(0))

    text = tag_pattern.sub(_replace_tag, text)

    # Second pass: replace bare hashes that appear outside tags
    bare_pattern = re.compile(r"\b(" + hash_alt + r")\b")

    def _replace_bare(m: re.Match) -> str:
        return session.hash_to_pii.get(m.group(1), m.group(0))

    return bare_pattern.sub(_replace_bare, text)
