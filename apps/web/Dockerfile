# The platform web app (Next.js). Build from the repository root:
#   docker build -f apps/web/Dockerfile -t firstpr-web .
FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
RUN adduser -D -u 10001 firstpr
COPY --from=build --chown=firstpr /app/.next/standalone ./
COPY --from=build --chown=firstpr /app/.next/static ./.next/static
COPY --from=build --chown=firstpr /app/public ./public
USER firstpr
EXPOSE 3000
CMD ["node", "server.js"]
