#!/bin/bash
# deploy.sh — Server setup script for tickerTap on a fresh Ubuntu 22.04/24.04 server.
# Run this script as a non-root user with sudo access.
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "\n${YELLOW}[STEP] $1${NC}"; }
ok()   { echo -e "${GREEN}[OK]   $1${NC}"; }
err()  { echo -e "${RED}[ERR]  $1${NC}"; exit 1; }

# ── 1. System packages ────────────────────────────────────────────────────────
step "Updating system packages"
sudo apt-get update -y
sudo apt-get upgrade -y
ok "System packages up to date"

# ── 2. Docker ─────────────────────────────────────────────────────────────────
step "Installing Docker"
if command -v docker &>/dev/null; then
    ok "Docker already installed: $(docker --version)"
else
    # Remove conflicting packages
    for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
        sudo apt-get remove -y "$pkg" 2>/dev/null || true
    done

    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin

    # Allow running docker without sudo (takes effect after re-login)
    sudo usermod -aG docker "$USER"
    ok "Docker installed: $(docker --version)"
    echo "  NOTE: Log out and back in (or run 'newgrp docker') for group change to take effect."
fi

# ── 3. nginx ──────────────────────────────────────────────────────────────────
step "Installing nginx"
if command -v nginx &>/dev/null; then
    ok "nginx already installed: $(nginx -v 2>&1)"
else
    sudo apt-get install -y nginx
    sudo systemctl enable nginx
    sudo systemctl start nginx
    ok "nginx installed and started"
fi

# ── 4. Certbot ────────────────────────────────────────────────────────────────
step "Installing certbot (Let's Encrypt)"
if command -v certbot &>/dev/null; then
    ok "certbot already installed: $(certbot --version)"
else
    sudo apt-get install -y certbot python3-certbot-nginx
    ok "certbot installed"
fi

# ── 5. Summary & next steps ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Installation complete. Follow these steps to deploy:${NC}"
echo -e "${GREEN}============================================================${NC}"
cat <<'EOF'

1. SET UP ENVIRONMENT VARIABLES
   cp .env.prod.example .env.prod
   # Edit .env.prod and fill in POSTGRES_PASSWORD, JWT_SECRET, ALLOWED_ORIGINS
   # Generate a strong JWT secret:
   #   openssl rand -hex 64

2. CONFIGURE NGINX
   # Replace api.yourdomain.com with your actual domain in nginx/tickerTap.conf
   sudo cp nginx/tickerTap.conf /etc/nginx/sites-available/tickerTap
   sudo ln -sf /etc/nginx/sites-available/tickerTap /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t && sudo systemctl reload nginx

3. OBTAIN SSL CERTIFICATE (Let's Encrypt)
   sudo certbot --nginx -d api.yourdomain.com
   # certbot will automatically update nginx config with SSL settings
   # Agree to the prompts and let certbot modify the nginx config

4. BUILD AND START THE APP
   # If docker group change hasn't taken effect yet, prefix commands with sudo
   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

5. VERIFY
   docker compose -f docker-compose.prod.yml ps
   curl -s https://api.yourdomain.com/health

6. AUTO-RENEW SSL (already set up by certbot, verify with):
   sudo systemctl status certbot.timer

EOF
