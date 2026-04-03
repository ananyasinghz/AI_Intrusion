import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# Detection
CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.45"))
# Higher bar for animal class — false animal positives are worse than missing one
ANIMAL_CONFIDENCE_THRESHOLD: float = float(os.getenv("ANIMAL_CONFIDENCE_THRESHOLD", "0.65"))
ALERT_COOLDOWN_SECONDS: int = int(os.getenv("ALERT_COOLDOWN_SECONDS", "30"))
MOTION_MIN_AREA: int = int(os.getenv("MOTION_MIN_AREA", "1500"))
# How many of the last N frames must agree before a detection is accepted
VOTE_WINDOW: int = int(os.getenv("VOTE_WINDOW", "5"))
VOTE_THRESHOLD: int = int(os.getenv("VOTE_THRESHOLD", "3"))

# Input source
INPUT_SOURCE: str = os.getenv("INPUT_SOURCE", "webcam")
VIDEO_FILE_PATH: str = os.getenv("VIDEO_FILE_PATH", "data/test_video.mp4")
ESP32CAM_URL: str = os.getenv("ESP32CAM_URL", "http://192.168.1.100/stream")
WEBCAM_INDEX: int = int(os.getenv("WEBCAM_INDEX", "0"))

# Zones
_zones_raw = os.getenv("ZONES", '["Main Entrance", "Corridor", "Backyard", "Side Gate"]')
ZONES: list[str] = json.loads(_zones_raw)

# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/incidents.db")

# Snapshots
SNAPSHOT_DIR: Path = BASE_DIR / os.getenv("SNAPSHOT_DIR", "snapshots")
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Mock PIR
MOCK_PIR_INTERVAL: int = int(os.getenv("MOCK_PIR_INTERVAL", "0"))

# Models
MODELS_DIR: Path = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
# yolov8s (small) — significantly better accuracy than nano with acceptable CPU speed
YOLO_MODEL_PATH: str = os.getenv("YOLO_MODEL_PATH", str(MODELS_DIR / "yolov8s.pt"))

# Server
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# JWT
JWT_SECRET: str = os.getenv("JWT_SECRET", "CHANGE_THIS_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING")
JWT_ALGORITHM: str = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Email (optional — alerts/digests)
SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM: str = os.getenv("SMTP_FROM", "intrusion@example.com")
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")

# Reports output directory
REPORTS_DIR: Path = BASE_DIR / os.getenv("REPORTS_DIR", "reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Snapshot/incident data retention days (0 = keep forever)
DATA_RETENTION_DAYS: int = int(os.getenv("DATA_RETENTION_DAYS", "30"))

# COCO class indices for animals (from COCO 80-class list)
ANIMAL_CLASS_IDS: set[int] = {
    14,  # bird
    15,  # cat
    16,  # dog
    17,  # horse
    18,  # sheep
    19,  # cow
    20,  # elephant
    21,  # bear
    22,  # zebra
    23,  # giraffe
}
PERSON_CLASS_ID: int = 0
