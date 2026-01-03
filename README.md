# Bible Companion AI Agent

A Telegram bot that serves as a personalized Bible reading companion. It uses **Google Gemini** for intelligence and **Google Drive** for user-controlled data storage.

## Features
- **Personalized Onboarding:** Customizes experience based on language, translation, denomination, and pacing.
- **Reading Plans:** Generates custom reading plans (and extends them automatically) or follows standard ones.
- **Contextual Awareness:** Stores user context (profile, progress, chat history) in **Markdown** files in the user's Google Drive.
- **Deep-Dive Discussions:** Engages in theological conversations using Google Gemini.

---

## 1. Prerequisites

Before running the bot, you need the following:

1.  **Telegram Bot Token:**
    - Message [@BotFather](https://t.me/BotFather) on Telegram to create a new bot and get the token.
2.  **Google Gemini API Key:**
    - Get an API key from [Google AI Studio](https://aistudio.google.com/).
3.  **Google Cloud Service Account:**
    - Go to the [Google Cloud Console](https://console.cloud.google.com/).
    - Create a new Project.
    - Enable the **Google Drive API**.
    - Create a **Service Account** (IAM & Admin > Service Accounts).
    - Create a JSON Key for this account and download it. Rename it to `service_account.json`.
4.  **Google Drive Folder:**
    - Create a folder in your Google Drive.
    - **Share** this folder with the `client_email` found inside your `service_account.json` file.
    - Copy the **Folder ID** from the URL (e.g., `1s2r3...` in `drive.google.com/drive/u/0/folders/1s2r3...`).

---

## 2. Local Deployment (Docker)

The easiest way to run the bot is using Docker.

1.  **Prepare Directory:**
    ```bash
    mkdir -p credentials
    # Move your downloaded JSON key here
    cp /path/to/service_account.json credentials/service_account.json
    ```

2.  **Build the Image:**
    ```bash
    docker build -t bible-bot .
    ```

3.  **Run the Container:**
    Replace the placeholders with your actual keys.
    ```bash
    docker run -d \
      --name bible-bot \
      -v $(pwd)/credentials:/app/credentials \
      -e TELEGRAM_TOKEN="YOUR_TELEGRAM_TOKEN" \
      -e GEMINI_API_KEY="YOUR_GEMINI_API_KEY" \
      bible-bot
    ```

4.  **Start:**
    - Open your bot in Telegram.
    - Send `/start`.
    - Paste the **Google Drive Folder ID** when prompted.

---

## 3. Google Cloud Run Deployment (Serverless / Free Tier)

This bot is optimized for **Google Cloud Run** using Webhooks. This allows the bot to scale to zero when not in use, making it cost-effective (likely free for personal use).

### Step 1: Create Secrets & Grant Permissions
**Important:** Cloud Run requires explicit permission to access your secrets. Run these commands **before** deploying.

1.  **Create Secret:**
    ```bash
    gcloud secrets create bible-bot-creds --data-file=service_account.json
    ```

2.  **Grant Access:**
    Replace `PROJECT_NUMBER` with your actual project number.
    ```bash
    # 1. Get Project Number
    gcloud projects list --filter="$(gcloud config get-value project)" --format="value(projectNumber)"

    # 2. Grant Secret Accessor Role
    # Replace [PROJECT_NUMBER] below with the number from the command above
    gcloud secrets add-iam-policy-binding bible-bot-creds \
      --member="serviceAccount:[PROJECT_NUMBER]-compute@developer.gserviceaccount.com" \
      --role="roles/secretmanager.secretAccessor"
    ```

### Step 2: Deploy Initial Version
Now deploy the bot. Since Cloud Run generates the URL *after* deployment, we deploy once to get the URL.

1.  **Deploy:**
    ```bash
    gcloud run deploy bible-bot \
      --source . \
      --region us-central1 \
      --allow-unauthenticated \
      --set-env-vars TELEGRAM_TOKEN="your_token",GEMINI_API_KEY="your_key" \
      --set-secrets="/app/credentials/service_account.json=bible-bot-creds:latest"
    ```
    *Note: If using Option B (local file), remove `--set-secrets` and ensure the file is copied in Dockerfile.*

### Step 2: Configure Webhook
Once the deployment finishes, copy the **Service URL** (e.g., `https://bible-bot-xyz.a.run.app`).

1.  **Update Environment Variable:**
    ```bash
    gcloud run services update bible-bot \
      --region us-central1 \
      --set-env-vars WEBHOOK_URL="https://YOUR-SERVICE-URL.run.app"
    ```

2.  **Done!**
    The bot will now restart in Webhook mode. Cloud Run automatically manages the `PORT` variable.

    *Note: The bot automatically saves chat history to Google Drive, ensuring conversations persist even if the server sleeps.*

---

## Development

**Run locally without Docker:**
1.  Install dependencies: `pip install -r requirements.txt`
2.  Set environment variables:
    ```bash
    export TELEGRAM_TOKEN="x"
    export GEMINI_API_KEY="y"
    export GOOGLE_APPLICATION_CREDENTIALS="path/to/service_account.json"
    ```
3.  Run: `python -m src.bot`

**Run Tests:**
```bash
python -m unittest tests/test_bot_logic.py
```
