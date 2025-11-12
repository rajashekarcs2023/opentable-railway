# 🚂 OpenTable Agent - Railway Deployment

Deploy the OpenTable Reservation uAgent to Railway for production use with Fetch.ai's ASI1 protocol.

## 🎯 What This Is

This is a **uAgent** (Fetch.ai agent) that:
- ✅ Uses ASI1 chat protocol
- ✅ Connects via mailbox for chat
- ✅ Automates OpenTable reservations
- ✅ Handles OTP verification
- ✅ Fills credit card forms (CDP)
- ✅ Works with ASI:One UI

## 🚀 Deploy to Railway

### Option 1: Deploy from GitHub (Recommended)

#### 1. Push to GitHub

```bash
# In your repo root
git add opentable-railway/
git commit -m "Add Railway deployment"
git push origin main
```

#### 2. Create Railway Project

1. Go to [Railway.app](https://railway.app)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. Railway will auto-detect Python and deploy!

#### 3. Configure Environment Variables

In Railway dashboard, add these variables:

```bash
OPENAI_API_KEY=sk-your-key-here
GEMINI_API_KEY=your-gemini-key-here
```

#### 4. Set Root Directory (Important!)

In Railway settings:
- **Root Directory**: `opentable-railway`
- **Start Command**: `python agent.py`

#### 5. Deploy!

Railway will automatically:
- Install Python dependencies
- Install Chromium browser
- Start your agent
- Provide logs

### Option 2: Deploy with Railway CLI

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
cd opentable-railway
railway init

# Set environment variables
railway variables set OPENAI_API_KEY=sk-your-key
railway variables set GEMINI_API_KEY=your-key

# Deploy
railway up
```

## 📋 Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-...` |
| `GEMINI_API_KEY` | Google Gemini API key | `AIza...` |

### Optional Configuration

In `agent.py`, you can customize:

```python
# Agent configuration
agent = Agent(
    name="opentable_reservation_agent",
    seed="opentable_seed_phrase_123",
    port=8001,  # Change port if needed
    mailbox=True  # Required for ASI1
)
```

### Card Data

Edit in `agent.py` around line 43:

```python
CARD_DATA = {
    'name on the card': 'Your Name',
    'number': '4111111111111111',  # Test card
    'expiry_month': '03',
    'expiry_year': '27',
    'cvv': '317',
    'zip': '94704'
}
```

⚠️ **For production with real cards, see security notes below.**

## 🔧 Railway Configuration

### railway.json

```json
{
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "pip install -r requirements.txt && playwright install chromium"
  },
  "deploy": {
    "startCommand": "python agent.py",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

### Procfile

```
web: python agent.py
```

## 🎯 After Deployment

### 1. Get Agent Address

Check Railway logs for:
```
Agent address: agent1q...
```

### 2. Register with ASI:One

1. Go to ASI:One dashboard
2. Add agent service
3. Use your agent address
4. Enable chat protocol

### 3. Test It!

Send a message via ASI:One:
```
"Book Che Fico in SF for tomorrow at 8pm for 2 people,
John Doe (john@email.com, 415-555-1234)"
```

## 📊 Monitoring

### View Logs

In Railway dashboard:
- Click on your service
- Go to **"Deployments"** tab
- Click **"View Logs"**

### Check Agent Status

Look for these in logs:
```
✅ OpenAI API configured
✅ Gemini API configured
✅ Agent is running! Connect via ASI:One.
```

### Health Check

The agent runs continuously and logs:
- Registration status
- Incoming messages
- Booking progress
- Errors

## 🐛 Troubleshooting

### "ModuleNotFoundError"

**Fix**: Check `requirements.txt` is complete
```bash
railway logs
```

### "API key not configured"

**Fix**: Set environment variables in Railway dashboard

### "Browser automation disabled"

**Fix**: Verify Gemini API key is valid

### "Agent not responding"

**Fix**: 
1. Check mailbox is enabled
2. Verify agent address is correct
3. Check Railway logs for errors

### Build Fails

**Fix**: Make sure `railway.json` includes Playwright install:
```json
"buildCommand": "pip install -r requirements.txt && playwright install chromium && playwright install-deps"
```

## 💰 Railway Costs

Railway offers:
- **$5 free credits/month** (Hobby plan)
- **$20/month** for Pro plan (recommended for production)

**Resource Usage:**
- Memory: ~500MB-1GB
- CPU: Light (during booking only)
- Build time: ~3-5 minutes
- Deploy time: ~30 seconds

**Estimated cost**: $5-10/month for demo use

## 🔒 Security Notes

### For Demo (Current Setup)

✅ Uses test credit card (safe)  
✅ Public agent address (fine for demos)  
✅ No sensitive data stored

### For Production (Real Cards)

⚠️ **DO NOT hardcode real credit cards!**

**Options:**
1. **Use AWS Secrets Manager** (see `opentable-api` folder)
2. **Use Railway environment variables** (basic encryption)
3. **User-provided cards only** (recommended)

**If using Railway env vars:**
```bash
railway variables set CARD_NUMBER=4111111111111111
railway variables set CARD_CVV=123
# etc.
```

Then in code:
```python
CARD_DATA = {
    'number': os.getenv('CARD_NUMBER'),
    'cvv': os.getenv('CARD_CVV'),
    # ...
}
```

## 📁 Project Structure

```
opentable-railway/
├── agent.py              # Main uAgent code (from opentable_asi1_with_card_tool.py)
├── requirements.txt      # Python dependencies
├── railway.json          # Railway configuration
├── Procfile             # Process file
├── env.example          # Environment template
└── README.md            # This file
```

## 🔄 Updating Your Agent

### Option 1: Git Push

```bash
# Make changes to agent.py
git add opentable-railway/
git commit -m "Update agent"
git push

# Railway auto-deploys on push
```

### Option 2: Railway CLI

```bash
cd opentable-railway
# Make changes
railway up
```

## 🌐 Connecting to ASI:One

### 1. Deployment Complete

After Railway deployment, note your **agent address** from logs.

### 2. Register in ASI:One

```
Service Type: Agent
Agent Address: agent1q... (from logs)
Protocol: Chat
Mailbox: Enabled
```

### 3. Test Connection

Send a test message:
```
"Hi! Can you help me make a reservation?"
```

The agent should respond with booking instructions.

## 📚 Related Documentation

- **Original Agent**: `../opentable_asi1_with_card_tool.py`
- **API Version**: `../opentable-api/` (for REST API deployment)
- **Railway Docs**: https://docs.railway.app
- **uAgents Docs**: https://fetch.ai/docs

## 🎉 You're Live!

Your OpenTable agent is now:
- ✅ Running on Railway
- ✅ Connected to Fetch.ai network
- ✅ Ready for ASI:One chat
- ✅ Making reservations automatically

**Next Steps:**
1. Test with sample reservations
2. Monitor Railway logs
3. Share agent address with users
4. Scale as needed

## 💡 Tips

- **Keep logs open** during first few bookings
- **Test with non-peak times** initially
- **Monitor Railway metrics** for performance
- **Set up alerts** in Railway dashboard
- **Use test cards** until confident

## 🆘 Support

**Railway Issues:**
- Railway Discord: https://discord.gg/railway
- Railway Docs: https://docs.railway.app

**Agent Issues:**
- Check Railway logs first
- Verify environment variables
- Test API keys separately
- Review error messages

---

**Deployed with:** Railway + uAgents + ASI1  
**Status:** Production-ready for demos  
**Cost:** ~$5-10/month
