# syntax=docker/dockerfile:1

FROM node:22-alpine AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine

USER root

COPY --from=builder --chown=101:101 /app/dist /usr/share/nginx/html

# Serve Vite assets directly and return index.html for client-side routes.
RUN printf '%s\n' \
    'server {' \
    '    listen 8080 default_server;' \
    '    listen [::]:8080 default_server;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '' \
    '    location /assets/ {' \
    '        try_files $uri =404;' \
    '        expires 1y;' \
    '        add_header Cache-Control "public, immutable";' \
    '    }' \
    '' \
    '    location = /index.html {' \
    '        add_header Cache-Control "no-store";' \
    '    }' \
    '' \
    '    location / {' \
    '        try_files $uri $uri/ /index.html;' \
    '    }' \
    '}' \
    > /etc/nginx/conf.d/default.conf

USER 101

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q -O /dev/null http://localhost:8080/

ENTRYPOINT ["nginx", "-g", "daemon off;"]
