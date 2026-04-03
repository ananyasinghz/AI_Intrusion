# AI-Based Intrusion & Activity Monitoring System

A privacy-preserving hostel security system using computer vision and machine learning.
No facial recognition — persons are blurred before any snapshot is stored.

---

## Features

| Feature | Status |
|---|---|
| PIR sensor simulation (mock) | ✅ |
| OpenCV MOG2 motion detection | ✅ |
| YOLOv8 nano — animal / person classification | ✅ |
| Privacy blur on persons | ✅ |
| Telegram real-time alerts | ✅ |
| FastAPI REST + WebSocket + MJPEG stream | ✅ |
| JWT auth (access + refresh tokens) | ✅ |
| Admin / Viewer roles | ✅ |
| Loitering detection | ✅ |
| Zone crossing tripwire | ✅ |
| Optical flow anomaly detection | ✅ |
| 6-table database (users, zones, alert_rules, incidents, refresh_tokens, reports) | ✅ |
| Alembic migrations | ✅ |
| React 18 + TypeScript + Vite frontend | ✅ |
| PDF & CSV report generation | ✅ |
| APScheduler daily digest & weekly PDF | ✅ |
| Email notifications (optional) | ✅ |
| 52 automated tests | ✅ |
| Hardware layer (ESP32-CAM, HC-SR501, Raspberry Pi) | ⏳ Phase H |

---

## Quick Start

### 1. Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env — add your Telegram bot token and chat ID

# Apply database migrations (creates all tables)
alembic upgrade head

# Run the server
python -m uvicorn backend.main:app --reload --port 8000
```

Default admin credentials: `admin` / `changeme` (change via Settings page or `/auth/me/password`)

### 2. Frontend

```bash
cd frontend
npm install
npm run dev        # Development server on http://localhost:5173
npm run build      # Production build → frontend/dist/
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | From @BotFather |
| `TELEGRAM_CHAT_ID` | — | Your chat/group ID |
| `INPUT_SOURCE` | `webcam` | `webcam`, `video:/path/to.mp4`, `esp32cam:http://IP/stream` |
| `DATABASE_URL` | `sqlite:///data/incidents.db` | SQLite path or PostgreSQL URL |
| `JWT_SECRET` | (insecure default) | **Change in production** |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `SMTP_HOST` | — | Email host (e.g. `smtp.gmail.com`) |
| `SMTP_USER` | — | Email username |
| `SMTP_PASSWORD` | — | Email app password |
| `ADMIN_EMAIL` | — | Recipient for weekly PDF reports |
| `ZONES` | `["Main Entrance","Corridor","Backyard","Side Gate"]` | JSON list of zone names |
| `DATA_RETENTION_DAYS` | `30` | Auto-delete incidents older than N days (0 = keep forever) |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  React Frontend (Vite + TypeScript)                       │
│  Login · Dashboard · Incidents · Analytics                │
│  Zones · Reports · Settings · Users                       │
└─────────────────────┬────────────────────────────────────┘
                      │ HTTP / WebSocket
┌─────────────────────▼────────────────────────────────────┐
│  FastAPI Backend                                          │
│  /auth   /api/incidents  /api/zones  /api/users           │
│  /api/reports  /stream/video  /ws/live                    │
│  JWT + bcrypt auth · APScheduler · CORS                   │
└──────┬──────────────┬──────────────────────────────────── ┘
       │              │
┌──────▼──────┐  ┌────▼────────────────────────────────────┐
│  SQLite DB  │  │  Detection Pipeline                      │
│  (Alembic)  │  │  MotionDetector (MOG2)                   │
│  6 tables   │  │  YOLOv8 nano → Classifier                │
└─────────────┘  │  LoiteringDetector                       │
                 │  ZoneCrossingDetector (tripwire)          │
                 │  OpticalFlowAnomalyDetector               │
                 │  TelegramAlerter                          │
                 └─────────────────────────────────────────┘
```

---

## API Reference

### Auth
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | — | Login → access + refresh tokens |
| POST | `/auth/refresh` | — | Rotate refresh token |
| POST | `/auth/logout` | — | Revoke refresh token |
| GET | `/auth/me` | Any | Current user profile |
| PUT | `/auth/me/password` | Any | Change password |

### Incidents
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/incidents` | Any | Paginated list (filter by zone/type/date) |
| GET | `/api/incidents/{id}` | Any | Single incident |
| PATCH | `/api/incidents/{id}/resolve` | Admin | Mark resolved |
| GET | `/api/stats` | Any | Summary stats (by_type, by_zone, hourly) |
| GET | `/api/heatmap` | Any | Zone heatmap data |
| GET | `/api/analytics/hourly-heatmap` | Any | Hour-of-day × zone grid |

### Zones
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/zones` | Any | List all zones |
| POST | `/api/zones` | Admin | Create zone |
| PATCH | `/api/zones/{id}` | Admin | Update zone |
| DELETE | `/api/zones/{id}` | Admin | Delete zone |
| POST | `/api/zones/{id}/alert-rules` | Admin | Add alert rule |

### Users (Admin only)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/users` | List users |
| POST | `/api/users` | Create user |
| PATCH | `/api/users/{id}` | Update role / active status |
| DELETE | `/api/users/{id}` | Delete user |

### Reports
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/reports` | Any | Report history |
| POST | `/api/reports/generate` | Admin | Generate PDF or CSV |
| GET | `/api/reports/{id}/download` | Any | Download file |

---

## Running Tests

```bash
pytest tests/ -v
# Expected: 52 passed
```

Tests cover:
- API authentication and authorization (role enforcement)
- Incident CRUD + filtering
- Stats and heatmap endpoints
- Zone and user management
- JWT token creation / validation / rotation
- Detection modules: loitering, zone crossing, optical flow
- End-to-end pipeline with synthetic video frames

---

## Privacy Design

- **No facial recognition** — never trained, never called.
- **Gaussian blur** is applied to every detected `person` bounding box before the snapshot is saved to disk.
- Raw frames are never persisted; only the blurred snapshot JPEG is stored.
- Persons are identified only by bounding box + confidence — never by identity.

---

## Input Sources

Set `INPUT_SOURCE` in `.env`:

```
INPUT_SOURCE=webcam                        # Default webcam (index 0)
INPUT_SOURCE=webcam:1                      # Alternate camera index
INPUT_SOURCE=video:/path/to/sample.mp4    # Pre-recorded video file
INPUT_SOURCE=esp32cam:http://192.168.1.50/stream  # ESP32-CAM MJPEG stream
```

Sample test videos (no animals needed — motion detection works on any movement):
- [Pexels free walking footage](https://www.pexels.com/search/videos/walking/)

---

## Hardware Integration (Future — Phase H)

| Phase | Component | Status |
|---|---|---|
| H1 | HC-SR501 PIR sensor via GPIO/webhook | ⏳ |
| H2 | ESP32-CAM MJPEG stream | ⏳ |
| H3 | Raspberry Pi 4 deployment + multi-zone | ⏳ |

The software is fully hardware-agnostic. Swap `INPUT_SOURCE` for real cameras
and replace mock PIR with a real GPIO callback when hardware is available.
