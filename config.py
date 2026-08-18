import os

from dotenv import load_dotenv

load_dotenv()

TURSO_URL = os.environ.get("TURSO_URL") or None
TURSO_TOKEN = os.environ.get("TURSO_TOKEN") or None
LOCAL_DB_PATH = os.environ.get("LOCAL_DB_PATH", "data/kutit.db")

DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET") or DASHBOARD_API_KEY or "kutit-dev-secret"

HONEYPOT_FIELD_NAME = os.environ.get("HONEYPOT_FIELD_NAME", "_hp")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "5493794099636")

MEDIDA_LARGO_DEFAULT = 2750
MEDIDA_ANCHO_DEFAULT = 1830
