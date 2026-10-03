# Hub image (also runs the simulator). Replaces the Raspberry Pi: any laptop with
# Docker can be the hub. Build it while online; the demo itself runs with no internet.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The hub serves web/, validates against shared/, and loads history made by sim/.
COPY pyproject.toml .
COPY shared/ shared/
COPY hub/ hub/
COPY sim/ sim/
COPY web/ web/

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Regenerate the fictional history on every start so it always ends today, then
# run the hub without --reload.
CMD ["sh", "-c", "python -m sim.generate_history && exec uvicorn hub.app.main:app --host 0.0.0.0 --port 8000"]
