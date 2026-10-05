# The platform web app (Next.js). Build from the repository root:
#   docker build -f apps/web/Dockerfile -t firstpr-web .
FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
# Where /api goes when nothing sits in front (Render); baked into the build by Next.js.
# With Compose or the production Caddyfile the proxy sends /api to the API first.
ARG API_INTERNAL_URL=http://api:8000
ARG API_INTERNAL_HOSTPORT=
ENV NEXT_TELEMETRY_DISABLED=1 API_INTERNAL_URL=${API_INTERNAL_URL} API_INTERNAL_HOSTPORT=${API_INTERNAL_HOSTPORT}
RUN if [ -n "$API_INTERNAL_HOSTPORT" ]; then export API_INTERNAL_URL="http://$API_INTERNAL_HOSTPORT"; fi && npm run build

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
