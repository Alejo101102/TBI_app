# Multi-stage: Vite build → Nginx static serve
# El frontend final solo expone puerto 80 (Nginx).
# /api/* se proxy-pasa al servicio "backend" via nginx.conf.

# ─── Stage 1: build con Vite ──────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# ─── Stage 2: serve con Nginx ─────────────────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
