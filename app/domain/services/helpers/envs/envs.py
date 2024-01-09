from os import getenv


def get_db_host() -> str:
    return getenv('DB_HOST', '')


def get_db_port() -> str:
    return getenv('DB_PORT', '')


def get_db_database() -> str:
    return getenv('DB_DATABASE', '')
