from .session import Session


def desanitize_text(text: str, session: Session) -> str:
    if not session.fake_to_real:
        return text

    # Replace longest fake values first to avoid partial matches
    for fake_val, real_val in sorted(
        session.fake_to_real.items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        text = text.replace(fake_val, real_val)
    return text
