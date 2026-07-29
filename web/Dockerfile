# TickerTap web tier — builds the frontend SPA and serves it via nginx,
# proxying API/health calls to the `app` container. Replaces the previous
# host-level nginx + certbot setup; TLS is handled upstream by Cloudflare
# Tunnel, so this container only ever speaks plain HTTP.

FROM node:20-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY web/nginx.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -q -O /dev/null http://localhost/ || exit 1
