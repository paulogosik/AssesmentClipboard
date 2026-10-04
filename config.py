import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

CRM_API_TOKEN = os.environ["CRM_API_TOKEN"]
CRM_BASE_URL = os.environ.get("CRM_BASE_URL", "https://analyst-assessment-production.up.railway.app/api/v1")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://analyst-assessment-production.up.railway.app")

OPERATOR_NAME = os.environ.get("OPERATOR_NAME", "Bellhaven Senior Living")
OPERATOR_PARENT_NAME = os.environ.get("OPERATOR_PARENT_NAME", "Bellhaven Senior Living (Parent Account)")

DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "data" / "sync.db"))
LOCATIONS_PATH = ROOT / "data" / "locations.json"

NAME_MATCH_THRESHOLD = 0.80
