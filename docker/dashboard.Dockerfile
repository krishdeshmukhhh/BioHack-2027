# Care dashboard image (Next.js). Build while online: npm ci downloads packages.
# At runtime it needs no internet; it talks only to the hub through HUB_URL.
FROM node:22-slim

WORKDIR /app/web/dashboard
ENV NEXT_TELEMETRY_DISABLED=1
COPY web/dashboard/package.json web/dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund

# The dashboard imports the shared data store and strings from web/shared.
COPY web/shared/ /app/web/shared/
COPY web/dashboard/ ./
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000
CMD ["npx", "next", "start", "--hostname", "0.0.0.0", "-p", "3000"]
