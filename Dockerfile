FROM node:22-bookworm-slim AS frontend
WORKDIR /app/website-designs
ENV NEXT_TELEMETRY_DISABLED=1
COPY website-designs/package.json website-designs/package-lock.json ./
RUN npm ci --ignore-scripts
COPY website-designs/app ./app
COPY website-designs/public ./public
COPY website-designs/next.config.mjs ./
RUN npm run build

FROM node:22-bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
COPY src/web/requirements.lock.txt /tmp/requirements.lock.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.lock.txt \
    && rm /tmp/requirements.lock.txt
WORKDIR /app
COPY --chown=node:node --from=frontend /app/website-designs ./website-designs
COPY --chown=node:node website-designs/scripts/pilot.mjs ./website-designs/scripts/pilot.mjs
COPY --chown=node:node src/web ./src/web
COPY --chown=node:node src/utils/__init__.py src/utils/mchat_scorer.py ./src/utils/
COPY --chown=node:node src/data/mchat_questions.json ./src/data/mchat_questions.json
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 ASDWISE_PRODUCTION=1 \
    ASDWISE_BIND_HOST=0.0.0.0 ASDWISE_PYTHON=/opt/venv/bin/python \
    PYTHONDONTWRITEBYTECODE=1 PORT=3000
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT+'/healthz',{signal:AbortSignal.timeout(4000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "website-designs/scripts/pilot.mjs"]
