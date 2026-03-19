from fastapi import FastAPI

from config.logging import setup_logging

setup_logging()

app = FastAPI(
    title="AlgoBridge API",
    description="Transforms coding problems into real-world engineering insights",
    version="1.0.0",
)


@app.get("/health")
async def health():
    return {"status": "OK"}
