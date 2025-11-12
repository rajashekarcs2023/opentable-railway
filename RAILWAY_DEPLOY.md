# 🚂 Railway Deployment Guide

Deploy your OpenTable uAgent to Railway in 5 minutes!

## 📋 Prerequisites

- GitHub account
- Railway account (sign up at [railway.app](https://railway.app))
- OpenAI API key
- Google Gemini API key

## 🚀 Quick Deploy (5 Steps)

### Step 1: Push to GitHub

```bash
# Navigate to your repo
cd /path/to/agents-agentverse

# Add and commit the Railway folder
git add browser-use-agent/opentable-railway/
git commit -m "Add OpenTable Railway deployment"
git push origin main
```

### Step 2: Create Railway Project

1. Go to **https://railway.app**
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Authorize Railway to access your GitHub
5. Select your repository: `agents-agentverse`

### Step 3: Configure Service

In Railway dashboard:

**Root Directory:**
```
browser-use-agent/opentable-railway
```

**Start Command:**
```
python agent.py
```

### Step 4: Add Environment Variables

Click **"Variables"** tab and add:

```bash
OPENAI_API_KEY=sk-proj-your-key-here
GEMINI_API_KEY=AIza-your-key-here
```

### Step 5: Deploy!

Click **"Deploy"** button. Railway will:
- ✅ Install Python 3.11
- ✅ Install dependencies
- ✅ Install Chromium browser
- ✅ Start your agent
- ✅ Keep it running 24/7

## 📊 Monitor Deployment

### View Build Logs

In Railway:
1. Click on your service
2. Go to **"Deployments"** tab
3. Click on latest deployment
4. View real-time logs

**Look for:**
```
🍽️  Starting OpenTable Reservation Agent...
📍 Agent address: agent1q...
✅ OpenAI API configured
✅ Gemini API configured
✅ Agent is running!
```

### Get Agent Address

Copy the agent address from logs:
```
Agent address: agent1q2w3e4r5t6y7u8i9o0p...
```

You'll need this for ASI:One!

## 🔗 Connect to ASI:One

### Step 1: Go to ASI:One Dashboard

Visit your ASI:One admin panel.

### Step 2: Add Agent Service

```
Service Type: Agent
Agent Address: agent1q... (from Railway logs)
Protocol: Chat
Mailbox: Enabled
```

### Step 3: Test It!

Send a message:
```
"Book Che Fico in SF for tomorrow at 8pm for 2 people, 
John Doe (john@email.com, 415-555-1234)"
```

## 🎯 What Railway Provides

✅ **Automatic deployments** - Push to GitHub = auto deploy  
✅ **Always running** - 24/7 uptime  
✅ **Auto-scaling** - Scales with usage  
✅ **Logs & monitoring** - Real-time logs  
✅ **SSL/TLS** - Secure connections  
✅ **Environment variables** - Secure config  
✅ **Rollbacks** - Easy to revert  

## 💰 Railway Pricing

**Hobby Plan (Free):**
- $5 credits/month
- Good for testing
- Limited resources

**Pro Plan ($20/month):**
- More resources
- Better for production
- Priority support

**Expected Usage:**
- ~$5-10/month for demo
- ~$15-20/month for production

## 🔄 Update Your Agent

### Method 1: Git Push (Automatic)

```bash
# Make changes to agent.py
nano opentable-railway/agent.py

# Commit and push
git add opentable-railway/
git commit -m "Update booking flow"
git push

# Railway auto-deploys!
```

### Method 2: Railway CLI

```bash
# Install CLI
npm install -g @railway/cli

# Login
railway login

# Link project
cd opentable-railway
railway link

# Deploy
railway up
```

## 🐛 Common Issues

### Issue: "Build Failed"

**Check:** `railway.json` has correct build command

**Fix:**
```json
{
  "build": {
    "buildCommand": "pip install -r requirements.txt && playwright install chromium && playwright install-deps"
  }
}
```

### Issue: "Agent not responding"

**Check:** Environment variables are set

**Fix:** Go to Railway → Variables → Add keys

### Issue: "Module not found"

**Check:** `requirements.txt` is complete

**Fix:** Add missing dependencies to `requirements.txt`

### Issue: "Browser automation failed"

**Check:** Playwright is installed

**Fix:** Add to `railway.json`:
```json
"buildCommand": "... && playwright install chromium && playwright install-deps"
```

## 📱 Railway Features to Use

### 1. Metrics

Monitor:
- CPU usage
- Memory usage
- Network traffic
- Request count

### 2. Logs

Real-time logs with:
- Filter by level
- Search functionality
- Download logs

### 3. Webhooks

Set up notifications:
- Deploy success/failure
- High resource usage
- Error alerts

### 4. Domains

Add custom domain:
```
Settings → Domains → Add Domain
```

## 🔐 Security Best Practices

### ✅ DO:
- Use environment variables for API keys
- Keep dependencies updated
- Monitor logs regularly
- Use test cards for demos

### ❌ DON'T:
- Hardcode API keys
- Commit `.env` files
- Use real cards without encryption
- Ignore security alerts

## 🎉 Success Checklist

- [ ] Railway project created
- [ ] Root directory set to `opentable-railway`
- [ ] Environment variables configured
- [ ] Build successful
- [ ] Agent running (check logs)
- [ ] Agent address copied
- [ ] Registered in ASI:One
- [ ] Test booking successful

## 📚 Next Steps

1. **Test thoroughly** - Try different restaurants
2. **Monitor usage** - Check Railway metrics
3. **Scale if needed** - Upgrade plan as usage grows
4. **Set up alerts** - Get notified of issues
5. **Document** - Keep track of agent address

## 🆘 Getting Help

**Railway Support:**
- Docs: https://docs.railway.app
- Discord: https://discord.gg/railway
- Status: https://status.railway.app

**Agent Issues:**
- Check logs first
- Verify API keys
- Test locally before deploying
- Review error messages

---

**You're now live on Railway! 🎉**

Your OpenTable agent is running 24/7 and ready to make reservations via ASI:One chat.

**Agent Address:** (from Railway logs)  
**Status:** ✅ Deployed and running  
**Cost:** ~$5-10/month
