# using ubuntu LTS version
FROM ubuntu:20.04 AS builder-image

# avoid stuck build due to user prompt
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install --no-install-recommends -y python3.9 python3.9-dev python3.9-venv python3-pip python3-wheel build-essential && \
	apt-get clean && rm -rf /var/lib/apt/lists/*

# create and activate virtual environment
# using final folder name to avoid path issues with packages
RUN python3.9 -m venv /home/predicta/venv
ENV PATH="/home/predicta/venv/bin:$PATH"

# install requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir wheel
RUN pip3 install --no-cache-dir -r requirements.txt

FROM ubuntu:20.04 AS runner-image
RUN apt-get update && apt-get install --no-install-recommends -y python3.9 python3-venv && \
	apt-get clean && rm -rf /var/lib/apt/lists/*

 FROM python:3.13-slim AS builder

 ENV PYTHONDONTWRITEBYTECODE=1 \
	 PYTHONUNBUFFERED=1 \
	 PIP_NO_CACHE_DIR=1 \
	 VIRTUAL_ENV=/opt/venv \
	 PATH="/opt/venv/bin:$PATH"

 RUN apt-get update \
	 && apt-get install --no-install-recommends -y build-essential \
	 && python -m venv "$VIRTUAL_ENV" \
	 && rm -rf /var/lib/apt/lists/*

USER predicta
RUN mkdir /home/predicta/code
 WORKDIR /build
 COPY requirements.txt pyproject.toml ./
 RUN sed '/^-e file:/d' requirements.txt > requirements-docker.txt \
	 && pip install --upgrade pip \
	 && pip install -r requirements-docker.txt \
	 && pip install gunicorn

 COPY . .
 RUN pip install --no-deps .
COPY . .

 FROM python:3.13-slim AS runtime

 ENV PYTHONDONTWRITEBYTECODE=1 \
	 PYTHONUNBUFFERED=1 \
	 DJANGO_DEBUG=0 \
	 DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost \
	 VIRTUAL_ENV=/opt/venv \
	 PATH="/opt/venv/bin:$PATH"

 RUN useradd --create-home --shell /usr/sbin/nologin predicta

 COPY --from=builder /opt/venv /opt/venv
 WORKDIR /app
 COPY --chown=predicta:predicta . .

 RUN mkdir -p /app/data/web /app/outputs/web/runs \
	 && chown -R predicta:predicta /app

 USER predicta
 EXPOSE 5000

RUN python manage.py collectstatic --noinput
 RUN python manage.py check

 CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 web.predicta_web.wsgi:application"]
# make sure all messages always reach console
ENV PYTHONUNBUFFERED=1

# activate virtual environment
ENV VIRTUAL_ENV=/home/predicta/venv
ENV PATH="/home/predicta/venv/bin:$PATH"

# /dev/shm is mapped to shared memory and should be used for gunicorn heartbeat
# this will improve performance and avoid random freezes
CMD ["gunicorn","-b", "0.0.0.0:5000", "-w", "4", "-k", "gevent", "--worker-tmp-dir", "/dev/shm", "api:api"]