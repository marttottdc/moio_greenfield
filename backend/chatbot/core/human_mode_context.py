def append_context_message(context, role, content):
    """
    Append a single human-mode message entry to context history.

    Human-mode submissions are single-message events, so this always returns a
    flat message list. Legacy dict contexts with `human_mode_messages` are
    normalized into the same list shape.
    """
    entry = {"role": role, "content": content}

    if isinstance(context, list):
        return context + [entry]

    if isinstance(context, dict):
        history = context.get("human_mode_messages")
        if isinstance(history, list):
            return history + [entry]

    return [entry]
