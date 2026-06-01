# 🚀 QUICK DEPLOY — GitHub Desktop Method

## Step 1: Download the ZIP
You already have the files. Unzip them.

## Step 2: Copy to Your Repo Folder
1. Find your `raj-web-app` folder on your computer
   (Usually in Documents/GitHub/raj-web-app)
2. Copy ALL files from this ZIP into that folder
3. Overwrite existing files when asked

## Step 3: GitHub Desktop
1. Open GitHub Desktop
2. Select `raj-web-app` repository
3. You'll see all the changed files on the left
4. Type commit message: "Raj v3.0 — web OAuth + PostgreSQL + fixes"
5. Click "Commit to main"
6. Click "Push origin"

## Step 4: Set Environment Variables on Render
1. Go to https://dashboard.render.com/web/srv-d8emvdurnols73afjbpg
2. Click "Environment" tab
3. Add these EXACT values:

   DATABASE_URL = (create PostgreSQL first, then copy URL)
   GOOGLE_CLIENT_ID = 912691451917-nh8it2i59v4ppmthqnajvc28sqj4c4i5.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET = 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
   REDIRECT_URI = https://raj-web-app.onrender.com/oauth2callback
   GMAIL_USER = info@robopirate.in
   FLASK_SECRET_KEY = raj-web-secret-2026-robopirate

4. Click "Save Changes"

## Step 5: Create PostgreSQL (Free)
1. https://dashboard.render.com → "New" → "PostgreSQL"
2. Name: raj-db | Region: Singapore | Plan: Free
3. Click Create, wait 1 minute
4. Copy "Internal Database URL"
5. Paste it as DATABASE_URL in your Environment tab

## Step 6: Redeploy
1. In Render dashboard, click "Manual Deploy" → "Deploy latest commit"
2. Wait 2-3 minutes
3. Visit https://raj-web-app.onrender.com

## Step 7: Connect Gmail
1. On your web dashboard, click Settings
2. Click "Connect Gmail"
3. Sign in with info@robopirate.in
4. Authorize the app
5. Done! ✅

## 📊 Sync Desktop Data
Before Step 6, run `export_desktop_data.py` on your Windows PC:
1. Put it in your RP Gmail folder
2. Double-click to run
3. It creates 4 CSV files
4. Copy those CSVs to your raj-web-app folder
5. Commit + push again via GitHub Desktop

---
Questions? Just tell me which step you're on.
