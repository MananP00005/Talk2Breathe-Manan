# 🚀 Talk2Breath — Phase 2: Deploy to Google Cloud (Cloud Run)

This guide takes the app from your computer to a **public HTTPS website** using
**Google Cloud Run** (serverless Docker). It's beginner-friendly — follow it top to
bottom. Everything is done in a terminal with the `gcloud` command.

> Why Cloud Run? It runs your Docker container, gives you a public URL with HTTPS,
> and **scales to zero** when nobody is using it — so a student test costs very little
> (often within Google's free tier).

---

## 0. What you need before starting
- A **Google account** (Gmail).
- A **credit/debit card** for Google Cloud (required to enable billing — but there's a
  free tier + free trial credits, and this app is very cheap).
- The **project code** on the laptop (the whole `Talk2Breath-Manan` folder).
- Your **Groq API key(s)** ready to paste.

---

## 1. Get the code onto the laptop
If it's on GitHub already:
```bash
git clone git@github.com:YOUR_USERNAME/Talk2Breath.git
cd Talk2Breath
```
Or just copy the whole `Talk2Breath-Manan` folder onto the laptop and `cd` into it.

> ⚠️ Do NOT copy your `.env` file to a public place. Keys will be added securely in Step 6.

---

## 2. Install the Google Cloud CLI (`gcloud`)
This is the tool that talks to Google Cloud.

**macOS** (easiest with Homebrew):
```bash
brew install --cask google-cloud-sdk
```
**Windows / Linux / manual:** download from
https://cloud.google.com/sdk/docs/install and follow the installer.

Check it worked:
```bash
gcloud --version
```

---

## 3. Log in to Google Cloud
```bash
gcloud auth login
```
A browser window opens — pick your Google account and allow access.

---

## 4. Create (or pick) a project
A "project" is a container for your app on Google Cloud.

```bash
# Make a new project (the ID must be globally unique, lowercase, no spaces)
gcloud projects create talk2breath-app-123 --name="Talk2Breath"

# Tell gcloud to use it from now on
gcloud config set project talk2breath-app-123
```
> Replace `talk2breath-app-123` with your own unique ID. If it says the ID is taken,
> add more numbers.

**Enable billing:** open https://console.cloud.google.com/billing , then link your
project to a billing account (this is where you add the card). Cloud Run won't deploy
without billing enabled, even though usage is likely free.

---

## 5. Turn on the services we use
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com
```
This takes about a minute the first time.

---

## 6. Store your Groq key(s) securely (Secret Manager)
Never bake keys into the image. We put them in Google's **Secret Manager**, then let
Cloud Run read them.

Create the secret and add your key(s). For **multiple keys**, separate with commas
(no spaces) — exactly like your `.env`:
```bash
printf "gsk_yourkey,gsk_friendskey" | gcloud secrets create groq-keys --data-file=-
```
> To update the keys later (add/remove a friend's key):
> ```bash
> printf "gsk_new,gsk_list" | gcloud secrets versions add groq-keys --data-file=-
> ```

Give Cloud Run permission to read it:
```bash
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding groq-keys \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 7. Deploy! 🎉
From inside the project folder (where the `Dockerfile` is), run one command. Cloud Run
builds your Docker image and deploys it:

```bash
gcloud run deploy talk2breath \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets "GROQ_API_KEYS=groq-keys:latest" \
  --memory 512Mi
```

What the flags mean:
- `--source .` — build from the current folder (uses your `Dockerfile`).
- `--region us-central1` — where it runs (pick one near your students; e.g.
  `asia-south1` for India).
- `--allow-unauthenticated` — makes it a public website anyone with the link can open.
- `--set-secrets` — injects your Groq keys from Secret Manager as the `GROQ_API_KEYS`
  environment variable (the app already reads this).
- `--memory 512Mi` — plenty for this app.

The first deploy takes a few minutes. If asked to enable extra APIs or pick a build
option, say **yes**.

When it finishes, it prints a **Service URL** like:
```
https://talk2breath-xxxxxxxxxx-uc.a.run.app
```
Open that in a browser — Breezy is live on the internet! 🌍

---

## 8. Test it
- Open the URL in **Chrome** (best for voice).
- Send a message → Breezy replies.
- Try the mic, a photo, and "draw me a picture."
- Visit `https://YOUR-URL/api/health` — it should show `{"status":"ok","keys_loaded":N}`.

> 🔊 Voice + 🎤 mic note: browsers only allow microphone on **HTTPS** sites. Cloud Run
> gives you HTTPS automatically, so the mic actually works better here than on localhost.

---

## 9. Updating the app later
Made changes? Just deploy again from the folder:
```bash
gcloud run deploy talk2breath --source . --region us-central1
```
It reuses your earlier settings (secrets, public access) and rolls out a new version.

---

## 10. Cost & safety notes
- **Cost:** Cloud Run bills only while handling requests and scales to zero when idle.
  A student test typically stays within the **free tier**. Set a budget alert at
  https://console.cloud.google.com/billing/budgets to be safe.
- **Groq limits still apply** — the per-account 30 requests/minute cap is on Groq's side,
  not GCP. Your multi-key rotation is what helps a full classroom (see README).
- **Turn it off / clean up** when the test is done to guarantee zero cost:
  ```bash
  gcloud run services delete talk2breath --region us-central1
  ```
- **Keys stay private** — they live in Secret Manager, never in the image or GitHub.

---

## Troubleshooting
| Problem | Fix |
|---|---|
| `billing account ... required` | Link billing in the Cloud Console (Step 4). |
| Build fails on push | Re-run the deploy; ensure `Dockerfile` is in the folder you're in. |
| Site loads but chat errors | Check the secret is set: `gcloud run services describe talk2breath --region us-central1`. Look for `GROQ_API_KEYS`. |
| "Breezy needs a rest" | All Groq keys hit their daily limit — add another key (Step 6) and redeploy. |
| Mic doesn't work | Must be the HTTPS Cloud Run URL, in Chrome, with mic permission allowed. |

---

Made with 💙 — once this is live, share the Cloud Run link with your students and watch
Breezy teach them about healthy lungs.
