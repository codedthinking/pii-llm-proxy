import re

from .session import Session


def desanitize_text(text: str, session: Session) -> str:
    if not session.hash_to_pii:
        return text

    escaped_hashes = [re.escape(h) for h in session.hash_to_pii]
    hash_alt = "|".join(escaped_hashes)

    # Match full redacted tags first, then bare hashes
    pattern = re.compile(
        r'<redacted\s+hash="(' + hash_alt + r')"\s+type="[^"]*"\s*/>'
        r"|\b(" + hash_alt + r")\b"
    )

    def _replace(m: re.Match) -> str:
        hash_val = m.group(1) or m.group(2)
        return session.hash_to_pii.get(hash_val, m.group(0))

    return pattern.sub(_replace, text)
