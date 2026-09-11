FROM node:22-alpine AS build
WORKDIR /app

ARG PUBLIC_API_BASE=/api
ARG PUBLIC_SELF_HOSTED=true
ENV PUBLIC_API_BASE=$PUBLIC_API_BASE
ENV PUBLIC_SELF_HOSTED=$PUBLIC_SELF_HOSTED

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
