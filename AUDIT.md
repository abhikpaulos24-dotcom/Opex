# AUDIT: every key and setting OpEx needs, step by step

This guide is for anyone. You don't need to know how to code. You'll copy a value from a website and paste it into one file called **`.env`**.

**Do you need any of this to try OpEx?** No. With an empty `.env`, OpEx still runs fully on your computer:
- It uses a local database file instead of Supabase.
- The AI explanations are rule-based instead of written by Gemini.

Add keys only when you want:
- the real Gemini AI (step 3),
- a shared online database (step 2),
- or to put OpEx on the internet (step 4).

---

## What it costs: everything below can start free

OpEx was set up so a team can use every service on a free tier at demo scale. Free limits change, so check the links before relying on a number.

| Service | What OpEx uses it for | Free at demo scale? | Watch out for |
|---|---|---|---|
| **Gemini API key** (AI Studio, step 3A) | Copilot, incident room, investigations, shift briefing, photo check, search | Yes, no card needed. Default model `gemini-3.5-flash-lite` has the most generous free daily limit | Daily request limits per model ([current limits](https://ai.google.dev/gemini-api/docs/rate-limits)). On the free tier Google may use your prompts to improve its products, so don't send real customer or plant secrets |
| **Supabase** (step 2) | Shared online database | Yes, free plan | Free projects pause after about a week without use; open the dashboard to wake it |
| **Cloud Run** (step 4) | Hosting the whole app | Yes, monthly free allowance (2 million requests, 180,000 vCPU-seconds). OpEx scales to zero when nobody is using it | Needs a billing account linked, even when free. Building the app also uses Cloud Build and Artifact Registry, usually free or a few rupees a month |
| **BigQuery sandbox** (step 5.1) | Analysis of simulations and decisions | Yes, no billing needed (10 GB storage, 1 TB of queries a month) | Sandbox tables are deleted after 60 days; send a fresh snapshot any time |
| **Cloud Storage** (step 5.2) | Uploaded files and part photos | 5 GB free, but only in US regions (`us-central1`, `us-east1`, `us-west1`) | A Mumbai (`asia-south1`) bucket costs a few rupees a month at demo scale |
| **Pub/Sub** (step 5.3) | Sending critical alerts to other systems | Yes, 10 GiB of messages a month | — |
| **Vertex AI** (step 3B) | Gemini for production | **No free tier.** New Google Cloud accounts get trial credit | Use option A until you need Vertex |

Free-tier details: https://cloud.google.com/free

---

## Step 0: Open the `.env` file

1. Open the OpEx folder.
2. Find the file named **`.env`**.
   - Files starting with a dot are hidden.
     - **Mac:** press `Cmd + Shift + .` in Finder to show them.
     - **Windows:** in File Explorer, click View → Show → Hidden items.
   - Can't find `.env`? Copy **`.env.example`** and rename the copy to `.env`. (HOW_TO_RUN.md shows the copy command.)
3. Open `.env` with a plain text editor: **TextEdit** on Mac, **Notepad** on Windows.
   - On Mac, if TextEdit shows formatting, choose Format → Make Plain Text.
4. Each line looks like `NAME=value`. Paste your value right after the `=`. No spaces, no quote marks.
5. Save the file, close OpEx (`Ctrl + C` in its window), and start it again.

**Never share `.env` and never upload it to GitHub.** It is already listed in `.gitignore`, so git won't upload it.

---

## Step 1: `SECRET_KEY` (session security)

**What it is:** a long random password the server uses to sign logins.
**Do I need it?** Optional on your own computer (logins are then forgotten whenever you restart). **Required** before putting OpEx online.

1. To make a new one, open Terminal (Mac) or PowerShell (Windows) and paste:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   (No Python? Any random string of 40+ letters and numbers works.)
2. Copy the output and paste it after `SECRET_KEY=`.

Changing it logs everyone out once. Nothing else happens.

---

## Step 2: Supabase database (`DATABASE_URL`)

**What it is:** the online Postgres database that stores users, decisions, incidents and simulation runs.
**Do I need it?** Only for a shared or online version. Without it, OpEx uses a local file at `data/opex.db`.

1. Go to **https://supabase.com** → **Start your project** → sign in (GitHub or email).
2. Click **New project**.
   - Name: `opex`
   - Database password: click **Generate a password** and **copy it somewhere safe**. You need it in a moment.
   - Region: **South Asia (Mumbai)**, or the closest to you.
   - Click **Create new project** and wait about 2 minutes.
3. Create the tables:
   1. Left menu → **SQL Editor** → **New query**.
   2. On your computer, open `database/01_schema.sql` in a text editor. Select all, copy, paste into Supabase, and click **Run**. You should see "Success. No rows returned".
   3. Do the same with `database/02_security.sql`. This locks the tables so only OpEx can read them.
   4. Optional: do the same with `database/03_reporting_views.sql` to add ready-made reports.

   (If you skip this, OpEx creates the tables itself on first start, but running the scripts lets you see them.)
4. Get the connection string:
   1. Click **Connect** at the top of the project page.
   2. Choose the **Session pooler** tab (it works everywhere, including Cloud Run). Copy the URI. It looks like:
      `postgresql://postgres.abcdefghijk:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres`
   3. Replace `[YOUR-PASSWORD]` (including the brackets) with the database password from step 2.
      - If the password contains `@ # / ? %` or spaces, replace each one with its code: `@`→`%40`, `#`→`%23`, `/`→`%2F`, `?`→`%3F`, `%`→`%25`, space→`%20`.
5. Paste the whole line after `DATABASE_URL=`.
6. Restart OpEx. The start-up text should say `database: Supabase/Postgres connected`. In Supabase → **Table Editor** you will see `app_users` with 4 demo accounts.

---

## Step 2b: Google sign-in (`GOOGLE_OAUTH_CLIENT_ID`) and the first manager

**What it is:** how people sign in. They click "Sign in with Google", so there are no passwords to hand out. It is free.
**Do I need it?** To try OpEx, no: demo mode has demo accounts you pick from a list. For real people, yes.

1. Go to **https://console.cloud.google.com** → pick your project (or create one, as in step 4.1). No billing is needed for this.
2. Left menu → **APIs & Services → OAuth consent screen** (also called *Google Auth platform*).
   - User type **External**, app name `OpEx`, your email as support and developer contact. Save.
   - While the app is in **Testing**, add the Google emails of the people who will sign in under **Test users**. Click **Publish app** when you want anyone to be able to try (basic sign-in needs no Google review).
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → type **Web application**.
   - **Authorised JavaScript origins**: add `http://localhost:8000` (running on your computer) and, once online, your Cloud Run link (`https://opex-…run.app`). No redirect URI is needed.
   - Click **Create**, then copy the **Client ID** (it ends in `.apps.googleusercontent.com`). It is not a secret.
4. In `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=1234567890-abc….apps.googleusercontent.com
   MASTER_ADMIN_EMAIL=srihithapulapa1@gmail.com
   ```
5. Restart OpEx. The sign-in page now shows the Google button.

**Who can do what:**
- The **first plant manager** is the Google account in `MASTER_ADMIN_EMAIL`. Sign in with it, open **Settings → People and roles**, and add everyone else by their Google email, as a manager or an engineer. It can never be demoted or switched off from the app.
- A Google account nobody added is turned away. Managers add people one by one.

**If you use Supabase and created the tables earlier:** run `database/05_two_roles.sql` once in the SQL Editor (it moves everyone onto the two roles). New projects don't need it.

**For real use, set `DEMO_MODE=false`.** That removes the demo accounts and the password form, so Google is the only way in.

---

## Step 3: Gemini AI (pick **A** or **B**)

**What it is:** Google's Gemini model. It powers the copilot, the AI incident room, investigation write-ups, photo checks and semantic search.
**Do I need it?** Strongly recommended for the full experience. Without it, OpEx uses rule-based answers.

### Option A: Gemini API key (easiest, free, 2 minutes, good for local runs and demos)
1. Go to **https://aistudio.google.com** and sign in with a Google account.
2. Click **Get API key** (left menu) → **Create API key**. Choose or create a Google Cloud project when asked.
3. Copy the key (it starts with `AIza…`).
4. In `.env`:
   ```
   GEMINI_API_KEY=AIza...your key...
   GOOGLE_GENAI_USE_VERTEXAI=false
   ```
5. Restart OpEx. The start-up text says `Gemini: on`.
6. Check it: on **Data & models → Google Cloud services**, Gemini shows **on**. In **Ask OpEx**, answers now say "Gemini · grounded on plant tools". On a machine page, **Photo check of a part** now gives a verdict.

The free key has a daily limit. When it runs out (or Gemini is busy), OpEx answers that question with its rule-based version, labelled "Rule-based", and tries Gemini again on the next question. Nothing breaks.

### Option B: Gemini on Vertex AI (for production on Cloud Run; not free)
1. You need a Google Cloud project with billing on (step 4 below). Vertex AI has no free tier, but new accounts get trial credit. Note the **Project ID**, which looks like `opex-123456`, not the project name.
2. Open **https://console.cloud.google.com/vertex-ai** and select your project. If asked, click **Enable all recommended APIs**.
3. In `.env`:
   ```
   GOOGLE_GENAI_USE_VERTEXAI=true
   GOOGLE_CLOUD_PROJECT=opex-123456
   GOOGLE_CLOUD_LOCATION=global
   ```
   Leave `GEMINI_API_KEY` empty.
4. Let OpEx on your computer use your Google login. Pick one:
   - **With the gcloud tool** (step 4.3): run `gcloud auth application-default login` once and sign in. Done.
   - **With a key file:**
     1. In the Cloud Console go to **IAM & Admin → Service accounts → Create service account**. Name it `opex`, give it the role **Vertex AI User**, and click Done.
     2. Open the account → **Keys → Add key → Create new key → JSON**. A file downloads.
     3. Move the file into the OpEx folder and put its path after `GOOGLE_APPLICATION_CREDENTIALS=`, e.g. `GOOGLE_APPLICATION_CREDENTIALS=/Users/you/opex/opex-key.json`.
     4. Keep this file private, like a password.
   - **On Cloud Run** you need neither. Cloud Run uses its own service account (step 5.4).

**Model names** (already set):
- `GEMINI_MODEL=gemini-3.5-flash-lite`: used for everything by default, because its free tier allows the most requests per day.
- `GEMINI_FAST_MODEL=gemini-3.5-flash-lite`: used for quick jobs (shift briefing, photo check, safety officer).
- `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`: used for searching the factory memory.

Want sharper reasoning and have a paid key or Vertex AI? Set `GEMINI_MODEL=gemini-3.8-flash`. On the free tier it allows far fewer requests per day, so the demo may run out.

Note: the `gemini-2.5-*` models retire on Vertex AI on 20 Oct 2026, so don't use them.

---

## Step 4: Put OpEx online for free

OpEx is one Docker container, so any host that runs a Dockerfile can run it. Pick one.

### Option A: Render + Supabase (free, no Google Cloud project)

1. Put the OpEx folder on **GitHub** (a private repository is fine). `.env` is git-ignored, so your keys are **not** uploaded.
2. Set up the free **Supabase** database (step 2) and keep its `DATABASE_URL`. This matters: Render's free hosting erases local files whenever it goes to sleep, so without Supabase every person you added would be forgotten.
3. Go to **https://render.com** → sign in with GitHub → **New → Web Service** → choose your OpEx repository.
   - **Language / Runtime:** Docker (Render finds the `Dockerfile`).
   - **Instance type:** Free.
4. Under **Environment**, add these variables (the same names as in `.env`; paste each value yourself):

   | Name | Value |
   |---|---|
   | `ENV` | `production` |
   | `SECRET_KEY` | a long random text (step 1) |
   | `DATABASE_URL` | from Supabase (step 2) |
   | `GOOGLE_OAUTH_CLIENT_ID` | from step 2b |
   | `MASTER_ADMIN_EMAIL` | `srihithapulapa1@gmail.com` |
   | `GEMINI_API_KEY` | from step 3A (optional) |
   | `DEMO_MODE` | `false` for real use, `true` to keep the demo accounts |

5. Click **Create Web Service**. After a few minutes Render shows your link (`https://…onrender.com`).
6. Add that link to **Authorised JavaScript origins** in your Google client (step 2b), or the Google button will fail.

Good to know: the free service goes to sleep after 15 minutes without visitors and takes about a minute to wake. The live plant simulation starts over each time it wakes; your people, decisions and settings stay safe in Supabase.

### Option B: Google Cloud Run (needs a Google Cloud project with billing)

1. Create a project at **https://console.cloud.google.com** (name `opex`). Link a billing account (**Billing**); Cloud Run needs one even inside its free allowance. Set a budget alert (**Billing → Budgets & alerts**), e.g. ₹500.
2. Install the gcloud tool (https://cloud.google.com/sdk/docs/install), then in Terminal:
   ```bash
   gcloud auth login
   gcloud config set project opex-123456
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
   ```
3. From the OpEx folder, deploy (replace the values with your own, as in the table above):
   ```bash
   gcloud run deploy opex --source . --region asia-south1 --allow-unauthenticated \
     --memory 2Gi --cpu 2 --min-instances 0 --max-instances 1 \
     --set-env-vars "ENV=production,SECRET_KEY=...,DATABASE_URL=...,GOOGLE_OAUTH_CLIENT_ID=...,GEMINI_API_KEY=..."
   ```
   `--max-instances 1` keeps one shared live plant. It scales to zero when nobody is visiting. The command prints your public link (`https://opex-…run.app`).

---

## Step 5: Optional Google Cloud services

### 5.1 BigQuery (`BIGQUERY_DATASET`): simulation and decision data for analysis (free sandbox)
1. Open https://console.cloud.google.com/bigquery with your Google account and select (or create) a project. Without billing, BigQuery runs as a free **sandbox**; that is enough for OpEx.
2. In `.env`, set:
   ```
   GOOGLE_CLOUD_PROJECT=opex-123456
   BIGQUERY_DATASET=opex_analytics
   ```
   `BIGQUERY_LOCATION=asia-south1` is already set.
3. On your computer, let OpEx use your Google login: run `gcloud auth application-default login` once (or use a key file with the role **BigQuery Data Editor** + **BigQuery Job User**, as in step 3B). On Cloud Run, see 5.4.
4. Restart OpEx. **Data & models → Google Cloud services** shows BigQuery **on**.

What OpEx sends:
- After every simulation run, the daily results go into a `simulation_daily` table automatically.
- A plant manager can click **Data & models → Send a snapshot now**. It replaces the `decisions`, `incidents`, `alerts` and `latest_simulation` tables with a fresh copy and gives a link to open them.

Open the tables at https://console.cloud.google.com/bigquery, or connect Looker Studio to them. Sandbox tables are deleted after 60 days, so send a new snapshot when you need one.

### 5.2 Cloud Storage (`GCS_BUCKET`): uploaded files and part photos
1. Console → **Cloud Storage → Buckets → Create**.
   - Name: e.g. `opex-files-yourname` (must be unique worldwide).
   - Region: `us-central1` to stay inside the 5 GB free tier, or `asia-south1` (Mumbai) for data kept in India at a few rupees a month.
   - Leave public access **prevented**.
2. Set `GCS_BUCKET=opex-files-yourname`.
3. Sensor CSVs from the upload checker go to `uploads/`, and part photos from **Photo check** go to `photos/<machine>/`. Without a bucket, OpEx keeps them in the local `storage/` folder instead.

### 5.3 Pub/Sub (`PUBSUB_ALERTS_TOPIC`): send critical alerts to other systems
1. Console → **Pub/Sub → Topics → Create topic** → ID `opex-alerts` → Create.
2. Set `PUBSUB_ALERTS_TOPIC=opex-alerts`.
3. Any subscriber can now receive critical alerts as JSON: an SMS gateway, WhatsApp, your ticketing tool, or a Cloud Function.

### 5.4 Permissions for Cloud Run (needed for Vertex AI, BigQuery, Storage, Pub/Sub)
Cloud Run runs as the **Compute Engine default service account** (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`).
1. Console → **IAM & Admin → IAM** → find that account → **Edit** (pencil).
2. Add these roles:
   - **Vertex AI User**
   - **BigQuery Data Editor** + **BigQuery Job User**
   - **Storage Object Admin**
   - **Pub/Sub Publisher**
3. Save.

### 5.5 Sensor ingest key (`INGEST_API_KEY`): real machine data
- Make a random value (as in step 1) and set `INGEST_API_KEY=...`.
- Gateways or a Pub/Sub push subscription then send readings to `POST /api/ingest/readings` with the header `X-API-Key: <value>`. Example body:
  ```json
  {"machine_id": "M-17", "readings": {"vibration_mm_s": 3.4, "process_temp_c": 39.2, "rpm": 1810}}
  ```
- For a **Pub/Sub push subscription**, use the endpoint `https://YOUR-URL/api/ingest/readings` and the same JSON as the message data. Pass the key as a header via an API gateway, or keep the endpoint behind IAP.

---

## Step 6: Demo settings

| Setting | Meaning | Default |
|---|---|---|
| `DEMO_MODE` | Creates 2 demo accounts (pick one and log in) and the demo controls. Set `false` for real use | `true` (keep it on for judging) |
| `DEMO_PASSWORD` | Password of the demo accounts. Only used when they are first created | `OpEx-demo-2026` |
| `MASTER_ADMIN_EMAIL` | The Google account that becomes the first plant manager | `srihithapulapa1@gmail.com` |
| `LIVE_PLANT_SPEED` | Plant minutes per real minute. `10` makes demos lively; `1` is real time | `10` |
| `ENV` | `production` on Cloud Run (the deploy script sets it) | `development` |
| `LOG_LEVEL` | `INFO` normally, `DEBUG` when troubleshooting | `INFO` |
| `CORS_ORIGINS` | Only for developers using `npm run dev` | `http://localhost:5173` |

---

## Checklist: what each value is and where it comes from

| Variable | Needed? | Where you get it | Example |
|---|---|---|---|
| `SECRET_KEY` | Yes, online | Step 1 (random) | `Xy7…48 chars` |
| `DATABASE_URL` | Optional | Supabase → Connect → Session pooler | `postgresql://postgres.abc:pass@aws-0-ap-south-1.pooler.supabase.com:5432/postgres` |
| `GOOGLE_OAUTH_CLIENT_ID` | For real sign-in | Google Cloud → APIs & Services → Credentials (step 2b) | `1234…apps.googleusercontent.com` |
| `GEMINI_API_KEY` | Option A | aistudio.google.com → Get API key | `AIza…` |
| `GOOGLE_GENAI_USE_VERTEXAI` | Option B | `true` to use Vertex AI | `true` |
| `GOOGLE_CLOUD_PROJECT` | Option B / deploy | Cloud Console project ID | `opex-123456` |
| `GOOGLE_CLOUD_LOCATION` | Option B | Keep `global` | `global` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Local Vertex only | Service-account JSON path | `/Users/you/opex/key.json` |
| `BIGQUERY_DATASET` | Optional (needs `GOOGLE_CLOUD_PROJECT` too) | Any name | `opex_analytics` |
| `GCS_BUCKET` | Optional | Cloud Storage bucket name | `opex-files-yourname` |
| `PUBSUB_ALERTS_TOPIC` | Optional | Pub/Sub topic ID | `opex-alerts` |
| `INGEST_API_KEY` | Optional | Random | `k3y…` |

**How to check everything is connected:** sign in → **Data & models** → card **Google Cloud services**. Each service shows **on** or **off**. The `/api/config` page shows the same in raw form.
