# TickerTap web tier — builds the frontend SPA and serves it via nginx,
# proxying API/health calls to the `app` container. Replaces the previous
# host-level nginx + certbot setup; TLS is handled upstream by Cloudflare
# Tunnel, so this container only ever speaks plain HTTP.

FROM node:20-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
# --legacy-peer-deps: the repo's devDependencies (eslint 9.x + eslint-plugin-*)
# have an unresolved peer-dep conflict unrelated to the production build
# (eslint is dev-only tooling, not used by `vite build`). Scoped to this
# build stage only; does not modify the app's package.json/lock.
RUN npm ci --legacy-peer-deps
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/security-headers.conf /etc/nginx/security-headers.conf

# Use 127.0.0.1 explicitly, not "localhost" — Alpine's /etc/hosts resolves
# localhost to ::1 first, and nginx only listens on 0.0.0.0 (IPv4).
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
