import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET") or DASHBOARD_API_KEY or "kutit-dev-secret"

HONEYPOT_FIELD_NAME = os.environ.get("HONEYPOT_FIELD_NAME", "_hp")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "5493794099636")
CLEVER_SITE_URL = os.environ.get("CLEVER_SITE_URL", "https://clevercnc.com.ar/")

MEDIDA_LARGO_DEFAULT = 2750
MEDIDA_ANCHO_DEFAULT = 1830

ODOO_URL = (os.environ.get("ODOO_URL") or "").rstrip("/") or None
ODOO_DB = os.environ.get("ODOO_DB") or None
ODOO_USERNAME = os.environ.get("ODOO_USERNAME") or None
ODOO_API_KEY = os.environ.get("ODOO_API_KEY") or None
ODOO_PRODUCT_CORTE_ID = int(os.environ.get("ODOO_PRODUCT_CORTE_ID", "4488"))
ODOO_PRODUCT_CANTO_ID = int(os.environ.get("ODOO_PRODUCT_CANTO_ID", "3364"))
ODOO_CATEGORIA_MATERIALES_ID = int(os.environ.get("ODOO_CATEGORIA_MATERIALES_ID", "3"))
ODOO_PARTNER_CONSUMIDOR_FINAL_ID = int(os.environ.get("ODOO_PARTNER_CONSUMIDOR_FINAL_ID", "7"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or None
