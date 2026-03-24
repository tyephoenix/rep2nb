def validate(name):
    if not name or not isinstance(name, str):
        raise ValueError("Name must be a non-empty string")
    return name.strip()
