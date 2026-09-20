# Vercel Deployment Guide

## 🎯 Recommended Approach: Hybrid Deployment

Since your app has heavy ML models and FastAPI backend, the best approach is:
- **Frontend → Vercel** (fast, free, global CDN)
- **Backend/API → Railway** (already configured, supports ML models)

---

## Option 1: Frontend Only on Vercel (Recommended)

### Step 1: Deploy Backend to Railway First
Follow the Railway deployment steps (already configured with `nixpacks.toml`)

### Step 2: Get Railway API URL
After Railway deployment, you'll get a URL like:
```
https://your-app.up.railway.app
```

### Step 3: Update vercel.json
Edit `vercel.json` and replace `your-railway-app.railway.app` with your actual Railway URL.

### Step 4: Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Login to Vercel
vercel login

# Deploy
cd /g/5g_sliced/5G-Marketplace
vercel

# Follow prompts:
# - Project name: 5g-marketplace
# - Deploy: Yes
```

### Step 5: Update Frontend API Calls
Update your frontend JavaScript to call the Railway backend:

```javascript
// In dashboard.js or similar files
const API_URL = 'https://your-railway-app.railway.app';

// Example API call
fetch(`${API_URL}/api/dashboard/system-health`)
  .then(res => res.json())
  .then(data => console.log(data));
```

---

## Option 2: Serverless API on Vercel (Limited)

⚠️ **Warning:** This won't work well with your ML models due to:
- 250MB size limit (PyTorch + TensorFlow = several GB)
- 10-second timeout (model loading takes longer)
- Cold starts (every request loads models from scratch)

### If you still want to try:

1. Create `api/index.py`:
```python
from fastapi import FastAPI
from mangum import Mangum

app = FastAPI()

@app.get("/api/health")
def health():
    return {"status": "ok"}

handler = Mangum(app)
```

2. Update `requirements.txt` (remove heavy ML libs):
```txt
fastapi==0.104.1
mangum==0.17.0
pydantic==2.4.2
```

3. Create `vercel.json`:
```json
{
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ]
}
```

---

## ✅ Best Practice: Use the Hybrid Approach

1. **Railway** handles:
   - FastAPI backend
   - ML model inference
   - Database connections
   - Heavy computations

2. **Vercel** handles:
   - Static frontend files
   - Fast global delivery
   - Auto SSL/CDN

---

## Quick Deploy Commands

```bash
# 1. Commit and push to GitHub
git add .
git commit -m "Add Vercel configuration"
git push origin main

# 2. Deploy to Vercel
vercel --prod

# 3. Your site will be live at:
# https://5g-marketplace.vercel.app
```

---

## Environment Variables (if needed)

In Vercel dashboard:
- Settings → Environment Variables
- Add `RAILWAY_API_URL` = your Railway backend URL

---

## Limitations on Vercel

❌ Can't run persistent FastAPI server  
❌ Can't load large ML models efficiently  
❌ 10-second function timeout  
❌ 250MB deployment limit  

✅ Great for static frontend  
✅ Global CDN  
✅ Free SSL  
✅ Automatic deployments  

---

**Recommended:** Keep Railway for backend, use Vercel only for frontend.
