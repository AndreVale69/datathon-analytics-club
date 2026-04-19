FROM node:22-alpine AS build

WORKDIR /app

COPY apps_sdk/web/package.json apps_sdk/web/package-lock.json* ./
RUN npm install

COPY apps_sdk/web/ ./
RUN npm run build

FROM caddy:2-alpine

COPY apps_sdk/web/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
