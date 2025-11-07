# 🌐 Ngrok Setup Guide

Ngrok creates a public URL that tunnels to your Flask web server, allowing external services (like YeuMoney) to redirect users to your code pages.

## ✅ What's Already Done

- ✅ Ngrok library (`pyngrok`) is installed
- ✅ Web server is configured to use ngrok
- ✅ Code will automatically create a tunnel when you add your auth token

## 📋 Setup Steps

### 1. Create Ngrok Account (Free)

Go to: **https://ngrok.com/signup**

- Sign up with Google, GitHub, or email
- It's completely free for basic use

### 2. Get Your Auth Token

1. After signing up, go to: **https://dashboard.ngrok.com/get-started/your-authtoken**
2. Copy your auth token (it looks like: `2abc...xyz`)

### 3. Add Token to Replit Secrets

1. In Replit, click the **🔒 Secrets** icon in the left sidebar (or Tools > Secrets)
2. Click **+ New Secret**
3. Set:
   - **Key**: `NGROK_AUTH_TOKEN`
   - **Value**: `paste your token here`
4. Click **Add new secret**

### 4. Restart Web Server

The web-server workflow will automatically restart and you'll see:

```
======================================================================
🌐 NGROK TUNNEL ACTIVE
======================================================================
📡 Public URL: https://abc123.ngrok-free.app
📡 Local:      http://localhost:5000
======================================================================

⚠️  IMPORTANT: Update WEB_BASE in .env with the ngrok URL above!
    WEB_BASE=https://abc123.ngrok-free.app
```

### 5. Update Your Configuration

1. Copy the ngrok URL from the logs
2. Open `.env` file
3. Update the `WEB_BASE` line:
   ```env
   WEB_BASE=https://your-ngrok-url.ngrok-free.app
   ```
4. Save the file
5. Restart the discord-bot workflow

## 🎯 How It Works

```
User → YeuMoney Link → Ngrok URL → Your Flask App → Display Code → Notify Bot
```

1. User gets YeuMoney shortened link from `/nhanxu` command
2. User completes YeuMoney redirect
3. YeuMoney redirects to: `https://your-ngrok-url.ngrok-free.app/ABC123`
4. Your Flask app displays the code
5. Flask notifies the Discord bot via webhook
6. Bot automatically adds xu to user's account

## ⚠️ Important Notes

### Free Plan Limitations

- **Ngrok URL changes** each time you restart the web server
- You'll need to update `WEB_BASE` in `.env` after each restart
- **Solution**: Use ngrok's paid plan for a permanent URL ($8/month)

### Keep Server Running

- The ngrok tunnel stays active as long as the web-server workflow is running
- If the server stops, the tunnel closes
- Replit keeps workflows running automatically

### Security

- Ngrok URLs are public but hard to guess
- Your Discord token and secrets are protected
- Never share your NGROK_AUTH_TOKEN

## 🔧 Troubleshooting

### "NGROK_AUTH_TOKEN not found!"

- Double-check you added the secret correctly
- Make sure the key is exactly: `NGROK_AUTH_TOKEN` (all caps)
- Restart the web-server workflow after adding

### Ngrok tunnel fails to start

- Check your auth token is valid at: https://dashboard.ngrok.com/get-started/your-authtoken
- Try restarting the web-server workflow
- Check the web-server logs for error messages

### Users not getting xu after visiting link

1. Make sure you updated `WEB_BASE` in `.env` with the ngrok URL
2. Restart the discord-bot workflow after updating `.env`
3. Check that both workflows (discord-bot and web-server) are running
4. Look at the web-server logs to see if the code page was accessed

## 💡 Alternative: Replit Domain (No Ngrok Needed)

If you don't want to use ngrok, you can use your Replit domain directly:

In `.env`, set:
```env
WEB_BASE=https://8c843fba-bb82-4209-a713-510e15dac172-00-3rchho2qamz9k.pike.replit.dev
```

**Pros**: 
- Free
- URL doesn't change
- No setup needed

**Cons**:
- Your Replit domain is visible to users
- Less professional looking

## 🎉 That's It!

Once ngrok is set up, your bot will work perfectly with YeuMoney links!

Need help? Check the web-server logs to see the ngrok URL and status.
