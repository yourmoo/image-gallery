# The fake picsum.dev used by the e2e suite. Test infrastructure only -- it is
# never part of the application image.
#
# Standard library only, so there is nothing to install and no package index
# needed at build time.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10002 fakeuser
USER fakeuser
WORKDIR /home/fakeuser

COPY app.py ./

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=2s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/_control/health', timeout=2).status == 200 else 1)"

CMD ["python", "app.py"]
