# ---- build stage: produce a wheel ----
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir build

COPY pyproject.toml ./
COPY image_gallery ./image_gallery

RUN python -m build --wheel --outdir /dist

# ---- runtime stage: install the wheel only, no source tree ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=image_gallery.settings \
    DJANGO_STATIC_ROOT=/var/www/static \
    DJANGO_STATIC_MANIFEST=true

RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /dist/*.whl /tmp/

RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -f /tmp/*.whl \
    && mkdir -p /var/www/static \
    && chown -R appuser:appuser /var/www/static

USER appuser
WORKDIR /home/appuser

RUN image-gallery-admin collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

# A page is N concurrent /images/<id> requests, not one request that fans out
# internally (docs/adr/0017-image-fetch-timing.md), so request slots ARE the
# fetch concurrency. Sync workers would serve 2 at a time and re-serialise the
# page: 5 waves x ~450 ms for a 10-image page. gthread with 8 threads gives 16
# slots, above the browser's 6-per-origin cap, so the browser stays the binding
# constraint as that ADR assumes. The work is blocking I/O, so the GIL is idle.
CMD ["gunicorn", "image_gallery.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--worker-class", "gthread", \
     "--workers", "2", \
     "--threads", "8", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
