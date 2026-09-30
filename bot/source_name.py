"""Validate public Telegram username before constructing any crawl URL."""
import re
_USERNAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{4,31}')

def public_source_name(value):
    if not isinstance(value,str) or not _USERNAME.fullmatch(value):
        raise ValueError('Nombre de canal público inválido.')
    return value
