# Expert Map — Deployment Guide

## Quick Setup (Railway)

### Step 1: Get an Anthropic API Key
1. Go to https://console.anthropic.com
2. Sign up and add a payment method
3. Go to **API Keys** → **Create Key**
4. Copy the key (starts with `sk-ant-...`)

### Step 2: Deploy to Railway
1. Go to https://railway.app and sign up
2. Click **New Project** → **Deploy from GitHub repo**
3. Connect your GitHub account and select this repo
4. Go to **Settings** → **Environment Variables**
5. Add: `ANTHROPIC_API_KEY` = your key from Step 1
6. Railway will auto-deploy. Your app URL appears under **Settings** → **Domains**

### Step 3: Use the App
- Open your Railway URL in any browser
- Share the link with colleagues — it works 24/7

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `PORT` | No | Set automatically by Railway |

## Estimated Costs
- **Railway**: ~$5/month (Hobby plan)
- **Anthropic API**: ~$0.05–0.15 per company search (depends on usage)

## Files
- `api_server.py` — FastAPI backend (LLM orchestration, caching, verification)
- `app.js` — React frontend
- `index.html` — Entry point
- `requirements.txt` — Python dependencies
- `Procfile` — Railway start command
- `railway.json` — Railway config
