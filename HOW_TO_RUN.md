# How to run OpEx

This guide assumes no technical knowledge. Follow the steps for your computer. The first start takes about 5 minutes; after that it takes about 15 seconds.

You do **not** need any keys or accounts to try OpEx. Keys are optional extras, explained in [AUDIT.md](AUDIT.md).

---

## On a Mac

1. **Get the OpEx folder.** If you have a link to the GitHub page, click the green **Code** button → **Download ZIP**, then double-click the ZIP to unzip it.
2. Open the folder and **double-click `start.command`**.
   - If the Mac says *"cannot be opened because it is from an unidentified developer"*:
     1. **Right-click** (or Control-click) `start.command` and choose **Open**, then **Open** again.
     2. You only need to do this once.
3. A black Terminal window opens and shows progress. The first time, it:
   - installs a small tool called *uv*, which installs the right version of Python,
   - installs OpEx's packages,
   - creates your settings file.
4. After a short while, your web browser opens **http://localhost:8000** by itself.
5. **Keep the Terminal window open** while you use OpEx. To stop OpEx, click the Terminal window and press `Ctrl + C`, or just close it.

## On Windows

1. Download and unzip the OpEx folder as above.
2. **Double-click `start.bat`**.
   - If Windows shows *"Windows protected your PC"*, click **More info** → **Run anyway**.
3. A black window opens and installs everything the first time. Your browser then opens **http://localhost:8000**.
4. Keep the window open while you use OpEx. Close it to stop.

## On Linux

Open a terminal in the OpEx folder and run:

```bash
./start.sh
```

## With Docker Desktop (any computer)

1. Install Docker Desktop from https://www.docker.com/products/docker-desktop and open it.
2. In the OpEx folder, open a terminal and run:

```bash
docker compose up --build
```

3. When it is ready, open **http://localhost:8080**.

---

## Signing in

On the sign-in page you can:
- click **Explore as a guest (read-only)**, or
- click one of the demo accounts to fill in the form, then **Sign in**.

All demo accounts use the password **`OpEx-demo-2026`**.

| Account | Role | What you can do |
|---|---|---|
| `manager@opex.demo` | Plant manager | Everything, including Settings → Demo controls |
| `engineer@opex.demo` | Maintenance engineer | Approve or reject repairs and stops |
| `operator@opex.demo` | Machine operator | Acknowledge alerts, approve small actions |
| `viewer@opex.demo` | Viewer | Look around, ask questions, run simulations |

To make the screen easier to read, click the **T** button at the top. You can choose larger text, dark or high-contrast colours, a reading-friendly font, simpler words, less motion, and the language for AI answers and read-aloud.

A few things that help while you look around:
- The numbers update by themselves every few seconds. The dot at the top is **green** while data is live. Click **Pause** (⏸) to stop the updates while you read, and **Resume** when you're done.
- See a word you don't know, like *OEE*? Click the small **?** next to it for a plain explanation.
- Long lists show the 3 most important items first. Click **Show all** to see the rest.
- On a phone, **Sign out** is in the menu (☰).

---

## A 3-minute tour (also the demo-video script)

The plant runs 10× faster than real life, so things change while you watch.

| Time | Do this | What to point out |
|---|---|---|
| 0:00 | Sign in as **engineer@opex.demo**. You land on **Overview**. | A red banner: *M-17 spindle bearing, failure expected in 4–7 h*. The ranked list replaces 50 alarms with the few that matter. Health scores. The factory floor, where status shows as icon + word + colour. |
| 0:25 | Click **Review M-17**. | The numbered links at the top jump to each step. **1 What we detected:** "Vibration is 148% above its normal range…", with a bar showing the reading against its normal green band. **2 Why:** bearing degradation, chain of impact, *"similar to 7 previous incidents; in 7, bearing degradation was confirmed"*. **3 What happens next:** chance of failure, failure window, confidence, defects rising, ₹ per hour. |
| 1:00 | Click **4 What should we do?** | The best 3 options priced in ₹, with chance of failure and "worked here before" (**Show all options** for the rest). Switch priorities between **Balanced** and **Production first** and watch the recommendation change. Unsafe options are ruled out. |
| 1:20 | Click **Ask the AI incident room**. | Three Gemini agents: Diagnostician, Planner, Safety officer (with SOP references). |
| 1:35 | Close it, type a note, click **Approve: …**, then **Yes, approve**. | Before anything happens, OpEx says exactly what the action means (hours stopped, parts lost, cost). Then it confirms the decision and says when it will check whether it worked (2 plant hours, about 12 real minutes). The decision appears in the **Learning log**. |
| 1:40 | Optional: scroll to **Photo check of a part** and upload a photo of a machined part. | With a Gemini key, OpEx says *looks good*, *check it on the gauge* or *reject*, and why. |
| 1:45 | Open **M-21** from the Overview. | *"Vibration sensor drift (not a machine fault)"*. Confidence is cut because the data is bad. |
| 1:55 | **Ask OpEx** → press the mic and say *"What happens if I shut down Machine 17?"* (or click the chip). Click **Listen**. With a Gemini key, switch the language to हिन्दी and ask again. | Answers grounded on live plant tools, voice in and out, Indian languages. |
| 2:15 | **5-year simulation** → set the replay to **1 minute** → **Simulate 5 years**. | Two factories side by side: breakdowns, downtime, value created so far, machine floors, charts. |
| 2:40 | **Skip to results**. | A 3-line summary first, then **₹7.1 Cr net, 12.1× ROI, payback in month 3, 74.5% fewer breakdowns**, checked against US DOE benchmarks. Open **Rewind the factory** for one breakdown. Point out the downloads. |
| 2:55 | **Data & models**. | Models scored on unseen data: AUC 0.996, RMSE 13.0 cycles. Every assumption has a source. As the manager, **Send a snapshot now** copies the data to BigQuery (if it is set up). |

**Tip for a smooth demo:** sign in as the manager → **Settings → Demo controls**. You can reset to the scripted morning (OpEx asks you to confirm first), jump the plant clock forward, or start a problem on purpose (for example *"Coolant pump failing"* on M-09) and watch OpEx catch it within a few minutes.

---

## Turning on the real Gemini AI

Without a key, the AI answers are rule-based and labelled *"Rule-based"*, and the photo check is switched off. To get full Gemini:
1. Get a free key at **https://aistudio.google.com** → *Get API key*. No card is needed.
2. Open the `.env` file in the OpEx folder and paste it after `GEMINI_API_KEY=`.
3. Stop OpEx and start it again.

The free key allows a limited number of AI answers per day. If you use them up, OpEx simply switches back to rule-based answers until the next day. Google may use what you send on the free tier to improve its products, so don't paste confidential plant data. [AUDIT.md](AUDIT.md) lists what every Google service costs (most are free at demo size).

Full details (Vertex AI, Supabase and Google Cloud) are in [AUDIT.md](AUDIT.md).

## Putting OpEx online

Follow [AUDIT.md, step 4](AUDIT.md#step-4-google-cloud-project-to-put-opex-online-on-cloud-run). It comes down to installing `gcloud`, signing in, and running `./deploy/deploy_cloud_run.sh`, which gives you a public link.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| The browser didn't open | Open **http://localhost:8000** yourself. |
| *"Address already in use"* / port 8000 busy | Another OpEx window is already running. Close it, or restart the computer. |
| *"command not found: curl"* or the uv install fails | Install uv by hand from https://docs.astral.sh/uv/getting-started/installation/, then start again. |
| The first start is slow | Normal. It downloads Python and packages (about 400 MB). Later starts are fast. |
| *"Please sign in"* after a restart | Your `.env` has no `SECRET_KEY`. The start script adds one; see AUDIT.md step 1. |
| Supabase error on start | Check `DATABASE_URL` (AUDIT.md step 2), especially the password and special characters. Remove the line to fall back to the local database. |
| Gemini answers still say "Rule-based" | Check the key, save `.env`, restart. **Data & models → Google Cloud services** shows whether Gemini is on. If it worked earlier today, the free daily limit may be used up; it resets the next day. |
| The numbers stopped changing | Look at the top bar. If it says **Paused**, click Resume (▶). If it says **Connection lost**, the OpEx window was closed or the computer slept; start OpEx again. |
| A machine says "stopped for a short routine job" | Normal: it's changing a tool. Its forecast still shows, based on its last minutes of cutting. |
| I want a clean start | Stop OpEx, delete `data/opex.db`, start again. This only resets the local database. |
| Windows: `start.bat` closes immediately | Open *Command Prompt*, go to the folder (`cd path\to\opex`) and run `start.bat` to read the message. |

## For developers

```bash
# backend with auto-reload (uses .venv created by the start script)
cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
# frontend with hot reload on http://localhost:5173 (needs Node.js 20+)
cd frontend && npm install && npm run dev
```

```bash
# tests: 32 tests, every API route for every role (about 15 s)
cd backend && ../.venv/bin/python -m pytest -q
```

```bash
# code checks
cd backend && ../.venv/bin/ruff check app tests pipeline
```

```bash
# type-check and rebuild the web app after changing frontend/src
cd frontend && npx tsc --noEmit && npm run build
```

```bash
# rebuild data + models from the raw datasets (about 30 s)
cd backend && ../.venv/bin/python -m pipeline.run_all
```
