# 🚀 Raj Web App — Deployment Guide (Non-Technical)

## What You Need to Do (5 Steps)

### Step 1: Upload These Files to GitHub
1. Go to https://github.com/robopirate/raj-web-app
2. Click **"Add file" → "Upload files"**
3. Upload these 5 files:
   - `app.py` (fixed backend)
   - `db.py` (PostgreSQL support)
   - `gmail_web.py` (web Gmail OAuth)
   - `seed_db.py` (CSV importer)
   - `requirements.txt` (dependencies)
4. Click **"Commit changes"**

### Step 2: Create PostgreSQL on Render
1. Go to https://dashboard.render.com
2. Click **"New" → "PostgreSQL"**
3. Name it: `raj-db`
4. Region: **Singapore** (closest to India)
5. Plan: **Free**
6. Click **"Create Database"**
7. Wait 2 minutes, then copy the **"Internal Database URL"** (looks like: `postgresql://raj_db_xxx:password@dpg-xxx.render.com/raj_db_xxx`)

### Step 3: Set Environment Variables on Render
1. Go to your web service: https://dashboard.render.com/web/srv-d8emvdurnols73afjbpg
2. Click **"Environment"** tab
3. Add these variables:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | *(paste the URL from Step 2)* |
| `GOOGLE_CLIENT_ID` | `912691451917-nh8it2i59v4ppmthqnajvc28sqj4c4i5.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | *(your secret from Google Cloud Console)* |
| `REDIRECT_URI` | `https://raj-web-app.onrender.com/oauth2callback` |
| `GMAIL_USER` | `info@robopirate.in` |
| `FLASK_SECRET_KEY` | `raj-web-secret-2026-robopirate` |

4. Click **"Save Changes"**

### Step 4: Redeploy
1. In Render dashboard, click **"Manual Deploy" → "Deploy latest commit"**
2. Wait 2-3 minutes for build to finish
3. Visit https://raj-web-app.onrender.com

### Step 5: Connect Gmail
1. In your web dashboard, click **Settings**
2. Click **"Connect Gmail"** button
3. Sign in with `info@robopirate.in` Google account
4. Authorize the app
5. You will be redirected back to the dashboard
6. ✅ Gmail is now connected!

---

## 📊 Import Your Desktop Data

Your desktop app has data in `campaign_data.db`. To sync it to the web:

### Option A: Export to CSV (Recommended)
1. Run `export_desktop_data.py` on your desktop (included in this repo)
2. It creates 3 CSV files: `batch_recipients.csv`, `batches.csv`, `blacklist.csv`
3. Upload these CSVs to your GitHub repo
4. The web app will auto-import them on startup

### Option B: Manual Import via Web
1. Go to web app → **Import** tab
2. Upload your Excel/CSV file
3. Select sequence (SCHOOL or CSR)
4. Click **Import to Pool**

---

## 🔧 Troubleshooting

| Problem | Fix |
|---------|-----|
| Dashboard shows 0s | Check `DATABASE_URL` is set. Click **Settings → Migrate CSV Data** |
| Gmail not sending | Go to **Settings → Connect Gmail** and authorize |
| App crashes on startup | Check Render logs. Usually missing `GOOGLE_CLIENT_SECRET` |
| CSV import fails | Make sure CSV has columns: `email`, `name`, `org`, `sequence_id` |

---

## 📞 Need Help?

If stuck, share:
1. Render logs (last 20 lines)
2. Screenshot of Environment variables page
3. What step you are on

**Locked by:** Kimi AI + RoboPirate Team
