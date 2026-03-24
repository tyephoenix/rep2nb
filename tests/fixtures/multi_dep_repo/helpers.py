from config import DEBUG


def log(message):
    if DEBUG:
        print(f"[LOG] {message}")


def format_url(base, endpoint):
    return f"{base}/{endpoint.lstrip('/')}"
