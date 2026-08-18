import hashlib
import hmac
import time

import config

SESSION_COOKIE_NAME = "kutit_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 días


def _firma(payload: str) -> str:
    return hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def crear_token_sesion() -> str:
    payload = str(int(time.time()))
    return f"{payload}.{_firma(payload)}"


def token_valido(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    payload, firma = token.rsplit(".", 1)
    if not hmac.compare_digest(firma, _firma(payload)):
        return False
    try:
        emitido = int(payload)
    except ValueError:
        return False
    return (time.time() - emitido) < SESSION_MAX_AGE


def api_key_valida(intentada: str) -> bool:
    if not config.DASHBOARD_API_KEY:
        return False
    return hmac.compare_digest(intentada or "", config.DASHBOARD_API_KEY)


def es_honeypot(valor) -> bool:
    return bool(valor)
