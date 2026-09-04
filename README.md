# 🦅 Elite-Bot — Autonomous AI Trading Platform
ONLY FOR THE JUDGES TO TEST THE ACCOUNT PORTFOLIO

ALPACA_API_KEY=PKHTCUNVHOM723G3HDLJZLPMA3
ALPACA_SECRET_KEY=3UQCrgVcs8wSR3Nfuk9nYsx9UbzMdCfSVRLLoATzbBCX
ALPACA_PAPER=true


A multi-asset, time-aware algorithmic trading platform combining:
- **Statistical Arbitrage** (Pairs Trading / Z-Score)
- **Multi-Agent AI Validation** (CrewAI + Groq Llama 3.3 70B)
- **Reinforcement Learning** (Q-Learning Brain)
- **Dual-Market Support** (US Stocks, Indian NSE, Forex)
- **Full-Stack Dashboard** (React + FastAPI)

---

## 🚀 Deploy Your Own Private Instance (Free)

> **Each user deploys their own private copy** — your API keys never touch anyone else's server.

### Option 1: Deploy to Render (Recommended — Fully Free)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. **Fork this repository** to your own GitHub account.
2. Go to [render.com](https://render.com) and sign up for a free account.
3. Click **"New +"** → **"Blueprint"** and connect your forked GitHub repo.
4. Render will detect `render.yaml` automatically and configure the service.
5. In the **Environment Variables** section (optional — you can also set these from the UI later):
   - `ALPACA_API_KEY` — your Alpaca API Key ID
   - `ALPACA_SECRET_KEY` — your Alpaca Secret Key
   - `ALPACA_PAPER` — `true` for paper trading, `false` for live
   - `GROQ_API_KEY` — your Groq API key (for AI agent validation)
6. Click **"Apply"** and wait ~5 minutes for the build to finish.
7. Open your Render URL and set your keys from the **Settings** page in the UI.

---

### Option 2: Run with Docker Locally

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/elite-bot.git
cd elite-bot

# 2. Build the container
docker build -t elite-bot .

# 3. Run with your keys
docker run -p 8080:8080 \
  -e ALPACA_API_KEY=your_key_here \
  -e ALPACA_SECRET_KEY=your_secret_here \
  -e ALPACA_PAPER=true \
  -e GROQ_API_KEY=your_groq_key_here \
  elite-bot

# 4. Open http://localhost:8080
```

---

### Option 3: Run Locally (Development)

```bash
# 1. Clone & install backend deps
git clone https://github.com/YOUR_USERNAME/elite-bot.git
cd elite-bot
pip install -r requirements.txt

# 2. Install & build frontend
cd frontend
npm install
npm run build
cd ..

# 3. Start the server
uvicorn app:app --host 0.0.0.0 --port 8080

# 4. Open http://localhost:8080 and enter your keys in Settings
```

---

## 🔑 Getting Your API Keys

### Alpaca (Trading — Free Paper Account)
1. Sign up at [alpaca.markets](https://alpaca.markets)
2. Go to **Paper Trading** → **API Keys** → Generate keys
3. Paste them in the Elite-Bot Settings page

### Groq (AI Agent Validation — Free Tier)
1. Sign up at [console.groq.com](https://console.groq.com)
2. Go to **API Keys** → Create a key
3. Paste it in the Elite-Bot Settings page

### Upstox (Indian Market — Optional)
1. Sign up at [developer.upstox.com](https://developer.upstox.com)
2. Create a **Sandbox App** and generate an access token
3. Set `UPSTOX_ACCESS_TOKEN` in your environment or Render dashboard

---

## 🛡️ Security Architecture

| Feature | Details |
|---|---|
| **Key Isolation** | Each deployed instance only has one user's keys — no sharing |
| **No Keys on Disk** | Keys live in browser `localStorage` + runtime env vars only |
| **No Global State** | Bot threads read from `os.environ` dynamically, not cached globals |
| **Module Hot-Reload** | `importlib.reload()` ensures new keys bind before each bot session |
| **Masked in UI** | API keys always shown as `PK12****ABCD` in the dashboard |
| **Groq Key Optional** | Leave blank to use server-level env key; or supply your own per-session |

---

## 🤖 Bot Modes

| Mode | Strategy | Market |
|---|---|---|
| **Elite** | Pairs Trading + CrewAI Validation | US Stocks |
| **Crypto** | Pairs Trading + RL Brain | Crypto |
| **Smart** | Momentum + RSI + CrewAI | US Stocks |
| **Sniper** | High-confidence Z-Score hits | US Stocks |
| **Autopilot** | Rule-based pairs with SL/TP | US Stocks |
| **RL** | Q-Learning + Sentiment | US Stocks |
| **Indian** | Pairs Trading | NSE (India) |
| **Forex** | Pairs Trading | Major FX Pairs |

---

## ⚠️ Risk Disclaimer

This is a **paper trading** research tool. Past performance does not guarantee future results. The authors are not responsible for any financial losses. Use live trading at your own risk.

---

## 📦 Tech Stack

- **Backend:** Python, FastAPI, Uvicorn
- **AI:** CrewAI, Groq (Llama 3.3 70B), Q-Learning
- **Data:** Alpaca Markets API, yfinance
- **Frontend:** React 19, Vite, Lightweight Charts
- **Deploy:** Docker, Render
