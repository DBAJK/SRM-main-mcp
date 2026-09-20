# Deployment Guide - 5G Marketplace

## ✅ Recommended: Deploy to Railway

### Step-by-Step Instructions:

#### 1. **Prepare Your GitHub Repository**

```bash
# Make sure you're in the 5G-Marketplace directory
cd /g/5g_sliced

# Add all files to git
git add .

# Commit the changes
git commit -m "Add deployment configuration files"

# Push to GitHub
git push origin main
```

#### 2. **Deploy to Railway**

1. **Go to Railway**: https://railway.app/
2. **Sign up/Login** with your GitHub account
3. **Click "New Project"**
4. **Select "Deploy from GitHub repo"**
5. **Choose your repository**: `Harsh067899/Build-A-Thon-SRM`
6. **Select root directory** or specify `5G-Marketplace` as the root path
7. **Railway will automatically detect** your Python app
8. **Add Environment Variables** (if needed):
   - Click on your service
   - Go to "Variables" tab
   - Add any required environment variables

9. **Deploy!** - Railway will:
   - Install dependencies from `requirements.txt`
   - Run your app using the `Procfile`
   - Provide you with a public URL

#### 3. **Configure Port** (Railway does this automatically)

Railway sets the `$PORT` environment variable. Your `run.py` will use it.

---

## Alternative 1: Deploy to Render

### Steps:

1. **Go to Render**: https://render.com/
2. **Sign up/Login** with GitHub
3. **New Web Service**
4. **Connect your repository**
5. **Configure**:
   - **Name**: `5g-marketplace`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python run.py --api-port $PORT`
6. **Create Web Service**

---

## Alternative 2: Deploy to Heroku

### Steps:

```bash
# Install Heroku CLI first: https://devcenter.heroku.com/articles/heroku-cli

# Login to Heroku
heroku login

# Create a new Heroku app
cd /g/5g_sliced/5G-Marketplace
heroku create 5g-marketplace-app

# Push to Heroku
git push heroku main

# Open your app
heroku open
```

---

## ❌ Why Not Vercel?

Vercel has limitations for your project:
- **Serverless only**: No persistent processes (your FastAPI needs to run continuously)
- **10-second timeout**: Your ML models might take longer to load
- **Limited Python support**: Better suited for Node.js/Next.js
- **No WebSockets**: If you need real-time features

---

## For Vercel (Frontend Only)

If you want to deploy **only the frontend** to Vercel:

### Steps:

1. **Create `vercel.json`** in your project root:

```json
{
  "builds": [
    {
      "src": "frontend/**",
      "use": "@vercel/static"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "/frontend/$1"
    }
  ]
}
```

2. **Deploy**:

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd /g/5g_sliced/5G-Marketplace
vercel
```

3. **Update API endpoints** in your frontend to point to your backend (deployed on Railway/Render)

---

## 🎯 My Recommendation

**Use Railway** - It's:
- ✅ Free tier available
- ✅ Easy GitHub integration
- ✅ Supports Python + ML models
- ✅ Automatic deployments on push
- ✅ Built-in database support
- ✅ No cold starts (unlike serverless)

---

## Quick Start Command

```bash
# 1. Commit and push to GitHub
git add .
git commit -m "Ready for deployment"
git push origin main

# 2. Go to railway.app and connect your GitHub repo
# 3. Deploy with one click!
```

---

## Need Help?

- Railway Docs: https://docs.railway.app/
- Render Docs: https://render.com/docs
- Heroku Docs: https://devcenter.heroku.com/
