# Compile the Next.js application with the deployment-relative API path.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --force
COPY . .
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build
# The shared lockfile includes the native Windows Rolldown binding used by
# local development. Force lets npm discard that dev-only binding when this
# Linux image is reduced to production dependencies.
RUN npm prune --omit=dev --force && npm pkg set version=0.6.0

# Serve only production dependencies as an unprivileged user.
FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S paylens && adduser -S paylens -G paylens
COPY --from=build --chown=paylens:paylens /app /app
USER paylens
EXPOSE 3000
STOPSIGNAL SIGTERM
CMD ["npm", "run", "start", "--", "--host", "0.0.0.0", "--port", "3000"]
