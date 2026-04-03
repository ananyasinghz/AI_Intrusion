#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# AI Intrusion Monitor — one-shot startup
# Usage: ./run.sh
# ──────────────────────────────────────────────────────────────
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${GREEN}=== AI Intrusion Monitor ===${NC}"

# 1. .env check
if [ ! -f .env ]; then
  echo -e "${YELLOW}No .env found — copying from .env.example${NC}"
  cp .env.example .env
  echo -e "${YELLOW}Edit .env to add your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID${NC}"
fi

# 2. Python deps
echo -e "${GREEN}Installing Python dependencies...${NC}"
pip install -r requirements.txt -q

# 3. DB migrations
echo -e "${GREEN}Running database migrations...${NC}"
alembic upgrade head

# 4. Frontend deps + build (if node available)
if command -v node &> /dev/null; then
  echo -e "${GREEN}Installing frontend dependencies...${NC}"
  cd frontend && npm install -q && cd ..
fi

echo -e "${GREEN}Starting backend on http://localhost:8000${NC}"
echo -e "${GREEN}Starting frontend on http://localhost:5173${NC}"
echo -e "${YELLOW}Default login: admin / changeme${NC}"
echo ""

# 5. Start both in parallel
if command -v node &> /dev/null; then
  (cd frontend && npm run dev) &
  FRONTEND_PID=$!
fi

python -m uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# Cleanup on Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" SIGINT SIGTERM
wait $BACKEND_PID
