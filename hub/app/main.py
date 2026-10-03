"""Smart pump hub. Scaffold only: see docs/PLAN.md phases 1 and 2."""

from fastapi import FastAPI

app = FastAPI(title="Smart Pump Hub (prototype)")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
