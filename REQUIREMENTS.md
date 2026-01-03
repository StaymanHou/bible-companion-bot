# Project Requirements & Specifications

## 1. Core Vision
Create an AI agent in the form of a **Telegram bot** that serves as a personalized **Bible reading companion**. The agent helps the user create a reading plan, keeps track of progress, and engages in deep-dive theological conversations based on the day's reading.

## 2. Functional Requirements

### Onboarding & Personalization
The bot must guide the user through an onboarding process to capture the following preferences:
- **Language:** Preferred language (supports bilingual interactions).
- **Bible Translation:** Primary preference (e.g., ESV, NIV) and optional secondary ones.
- **Theology:** Denominational, theological, or doctrinal affiliation to tailor discussions.
- **Communication Style:** Preferred tone (e.g., formal, casual, academic, devotional).
- **Pacing:** Reading frequency and duration.
- **Ordering:** Preference for reading order (e.g., Canonical, Chronological).

### Reading & Progress
- **Plan Generation:** The agent should generate customized reading plans based on user preferences using the AI model.
- **Daily Workflow:**
  - **Start Session:** User initiates reading (e.g., `/read`). The bot presents the text or reference.
  - **End Session:** User concludes reading (e.g., `/done`). The bot updates progress and initiates discussion.
- **Bible Text:** The bot relies on the LLM's internal knowledge base to quote and retrieve Bible verses (no external Bible text API required).

### Deep-Dive Discussion
- After reading, the bot engages the user in a conversation about the text.
- **Context Awareness:** The bot must utilize recent chat history (5-10 rounds) and user profile data to provide relevant and empathetic responses.
- **Learning:** The user profile should be updatable as the agent learns more about the user through conversation.

## 3. Data & Storage (Google Drive)

To ensure user ownership and transparency, all user data is stored in the **User's Google Drive**.

- **Integration Method:**
  - The bot uses a **Google Service Account**.
  - During setup, the bot provides its Service Account email.
  - The user creates a folder in their personal Drive and shares it with that email.
  - The user provides the **Folder ID** to the bot to link the account.
- **Data Format:** **Markdown (`.md`)** files with **YAML Frontmatter**.
  - *Reasoning:* Allows users to easily read and edit their own data files.
  - **Files:**
    - `profile.md`: Stores preferences and current progress (`current_day`).
    - `reading_plan.md`: Stores the generated reading schedule.
    - `chat_history.md`: Stores the log of interactions.

## 4. Technical Stack

- **Language:** Python
- **Framework:** `python-telegram-bot`
- **AI Model:** **Google Gemini** (via `google-generativeai`)
- **Storage API:** Google Drive API (via `google-api-python-client`)
- **Deployment:** Docker
  - Credentials (`service_account.json`) are mounted as a volume.
  - Configuration via Environment Variables (`TELEGRAM_TOKEN`, `GEMINI_API_KEY`).
