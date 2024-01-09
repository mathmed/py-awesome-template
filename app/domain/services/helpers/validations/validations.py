from re import search


def is_valid_email(email: str) -> bool:
    return bool(search(r"^[\w\.\+\-]+\@[\w]+\.[a-z]{2,3}$", email))


def is_valid_password(password: str) -> bool:
    return len(password) >= 6


def is_valid_name(name: str) -> bool:
    return len(name) >= 3
