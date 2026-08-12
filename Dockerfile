FROM python@sha256:23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements.docker.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements.lock \
    && python -m pip check \
    && rm /tmp/requirements.lock

COPY --chown=app:app forecast ./forecast
COPY --chown=app:app config ./config
COPY --chown=app:app scripts/phase_b_topology_probe.py ./scripts/phase_b_topology_probe.py
COPY deploy/python-entrypoint.sh /usr/local/bin/pnl-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/pnl-entrypoint \
    && chmod 0555 /usr/local/bin/pnl-entrypoint \
    && python -m compileall -q forecast

USER app
ENTRYPOINT ["/usr/local/bin/pnl-entrypoint"]
CMD ["python", "-m", "uvicorn", "forecast.bff.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
