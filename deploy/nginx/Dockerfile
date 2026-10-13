# Образ фронтенда: сборка SPA + nginx (статика, обратный прокси на api, TLS).
# Контекст сборки — корень репозитория:
#   docker build -f deploy/nginx/Dockerfile .
FROM node:24-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.29-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/conf/ /etc/nginx/app/
COPY deploy/nginx/40-select-config.sh /docker-entrypoint.d/40-select-config.sh
RUN chmod +x /docker-entrypoint.d/40-select-config.sh \
    && rm -f /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
