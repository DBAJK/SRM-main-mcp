from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from mangum import Mangum
import json
import os

app = FastAPI(title="5G Marketplace API - Vercel")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load static data
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

@app.get("/")
def read_root():
    return {"message": "5G Marketplace API", "status": "running"}

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "platform": "vercel"}

@app.get("/api/dashboard/system-health")
def system_health():
    return {
        "status": "healthy",
        "services": {
            "api": "operational",
            "database": "operational",
            "ai_agent": "disabled_on_vercel"
        },
        "metrics": {
            "total_slices": 0,
            "active_slices": 0,
            "total_vendors": 5
        }
    }

@app.get("/api/vendors")
def get_vendors():
    try:
        vendors_file = os.path.join(DATA_DIR, "vendors.json")
        with open(vendors_file, 'r') as f:
            vendors = json.load(f)
        return {"vendors": vendors}
    except:
        return {"vendors": []}

@app.get("/api/slices")
def get_slices():
    try:
        slices_file = os.path.join(DATA_DIR, "slices.json")
        with open(slices_file, 'r') as f:
            slices = json.load(f)
        return {"slices": slices}
    except:
        return {"slices": []}

@app.get("/api/env.js")
def env_js():
    key = os.getenv("GEMINI_API_KEY", "")
    serialized = json.dumps(key)
    script = (
        "window.ENV=window.ENV||{};"
        f"window.ENV.GEMINI_API_KEY={serialized};"
        f"try{{localStorage.setItem('geminiApiKey',{serialized});}}catch(e){{}}"
    )
    return Response(
        content=script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
    )

# Vercel serverless handler
handler = Mangum(app)
