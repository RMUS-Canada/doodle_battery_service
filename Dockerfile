FROM arm64v8/python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends

RUN python -m pip install --upgrade pip

COPY docker-requirements.txt .
RUN python -m pip install --no-cache-dir -r docker-requirements.txt

COPY build_signal.py doodle_battery_service.py doodle_helper.py /app/
WORKDIR /app

ENTRYPOINT ["python", "/app/doodle_battery_service.py"]