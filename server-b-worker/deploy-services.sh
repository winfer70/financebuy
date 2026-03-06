#!/usr/bin/env bash
# deploy-services.sh — Deploy TickerTap systemd services on Server B (Kali).
#
# This script:
#   1. Copies the service/timer files into /etc/systemd/system/
#   2. Fills in the <USERNAME>, <APP_SERVER_IP>, and <INTERNAL_KEY> placeholders
#   3. Reloads systemd, enables, and starts all services
#
# Usage:
#   sudo bash deploy-services.sh <APP_SERVER_IP> <INTERNAL_KEY>
#
# Prerequisites:
#   - Ollama must be installed (curl -fsSL https://ollama.com/install.sh | sh)
#   - The llama3:8b-instruct-q4_K_M model must be pulled (ollama pull llama3:8b-instruct-q4_K_M)
#   - Python venv must be set up at ~/tickertap-worker/venv with worker.py + learner.py

set -euo pipefail

# ── Validate arguments ─────────────────────────────────────────────────────
if [ $# -lt 2 ]; then
    echo "Usage: sudo bash deploy-services.sh <APP_SERVER_IP> <INTERNAL_KEY>"
    echo "  APP_SERVER_IP  — IP address of Server A (e.g. 192.168.1.100)"
    echo "  INTERNAL_KEY   — Must match INTERNAL_NEWS_KEY on Server A"
    exit 1
fi

APP_SERVER_IP="$1"
INTERNAL_KEY="$2"
USERNAME="$(logname 2>/dev/null || echo "${SUDO_USER:-$(whoami)}")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

echo "═══════════════════════════════════════════════════════════"
echo " TickerTap Service Deployment — Server B (Kali)"
echo "═══════════════════════════════════════════════════════════"
echo " User:           $USERNAME"
echo " App Server IP:  $APP_SERVER_IP"
echo " Internal Key:   ${INTERNAL_KEY:0:4}****"
echo " Source dir:     $SCRIPT_DIR"
echo ""

# ── Step 1: Verify Ollama is installed and model is available ──────────────
echo "[1/5] Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    echo "ERROR: Ollama is not installed. Run:"
    echo "  curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi
if ! ollama list 2>/dev/null | grep -q "llama3:8b-instruct"; then
    echo "WARNING: llama3:8b-instruct-q4_K_M model not found. Pull it with:"
    echo "  ollama pull llama3:8b-instruct-q4_K_M"
fi
echo "  Ollama OK"

# ── Step 2: Ensure Ollama service is enabled ───────────────────────────────
echo "[2/5] Enabling Ollama service..."
systemctl enable ollama 2>/dev/null || true
systemctl start ollama  2>/dev/null || true
echo "  ollama.service enabled and started"

# ── Step 3: Deploy worker service ──────────────────────────────────────────
echo "[3/5] Deploying tickertap-worker.service..."
sed -e "s|<USERNAME>|$USERNAME|g" \
    -e "s|<APP_SERVER_IP>|$APP_SERVER_IP|g" \
    -e "s|<INTERNAL_KEY>|$INTERNAL_KEY|g" \
    "$SCRIPT_DIR/tickertap-worker.service" > "$SYSTEMD_DIR/tickertap-worker.service"
echo "  Installed to $SYSTEMD_DIR/tickertap-worker.service"

# ── Step 4: Deploy learner service + timer ─────────────────────────────────
echo "[4/5] Deploying tickertap-learner.service + timer..."
sed -e "s|<USERNAME>|$USERNAME|g" \
    -e "s|<APP_SERVER_IP>|$APP_SERVER_IP|g" \
    -e "s|<INTERNAL_KEY>|$INTERNAL_KEY|g" \
    "$SCRIPT_DIR/tickertap-learner.service" > "$SYSTEMD_DIR/tickertap-learner.service"
cp "$SCRIPT_DIR/tickertap-learner.timer" "$SYSTEMD_DIR/tickertap-learner.timer"
echo "  Installed to $SYSTEMD_DIR/tickertap-learner.{service,timer}"

# ── Step 5: Reload, enable, and start ──────────────────────────────────────
echo "[5/5] Reloading systemd and enabling services..."
systemctl daemon-reload
systemctl enable tickertap-worker.service
systemctl enable tickertap-learner.timer
systemctl restart tickertap-worker.service
systemctl start tickertap-learner.timer

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo " Services status:"
systemctl is-active tickertap-worker.service  && echo "  tickertap-worker:  ACTIVE" || echo "  tickertap-worker:  INACTIVE"
systemctl is-active ollama.service            && echo "  ollama:            ACTIVE" || echo "  ollama:            INACTIVE"
echo ""
echo " Timer status:"
systemctl list-timers --all 2>/dev/null | grep -E "learner|NEXT" || true
echo ""
echo " Useful commands:"
echo "   journalctl -u tickertap-worker -f     # Watch worker logs"
echo "   journalctl -u tickertap-learner -e    # View learner output"
echo "   systemctl status tickertap-worker     # Worker status"
echo "   systemctl status ollama               # Ollama status"
