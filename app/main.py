from fastapi import FastAPI

app = FastAPI(
    title="MyImpact AI",
    description="AI intelligence and orchestration service for MyImpact",
    version="0.1.0",
)

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "myimpact-ai",
    }