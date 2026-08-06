FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY index.html app.js styles.css vite.config.js ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
