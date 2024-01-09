
from hashlib import sha256
from os import urandom


def encrypt(text: str) -> str:
    hash_object = sha256()
    hash_object.update(urandom(32) + text.encode())
    return hash_object.hexdigest()


def compare(plain_text: str, encrypted_text: str) -> bool:
    return encrypt(plain_text) == encrypted_text
