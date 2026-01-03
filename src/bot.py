import os
import logging
import asyncio
import http.server
import socketserver
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, 
    MessageHandler, filters, ConversationHandler
)

# Import our custom modules
from .drive_manager import GoogleDriveManager
from .ai_agent import GeminiAgent

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# State Definitions for ConversationHandler
(
    DRIVE_SETUP,
    ONBOARDING_LANGUAGE,
    ONBOARDING_TRANSLATION,
    ONBOARDING_DENOMINATION,
    ONBOARDING_STYLE,
    ONBOARDING_PACING,
    ONBOARDING_ORDERING,
    IDLE,
    READING,
    DISCUSSION
) = range(10)

class BibleBot:
    def __init__(self, token, drive_manager, ai_agent):
        self.application = ApplicationBuilder().token(token).build()
        self.drive = drive_manager
        self.ai = ai_agent
        
        # Setup handlers
        self._setup_handlers()

    def _setup_handlers(self):
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                DRIVE_SETUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.drive_setup_handler)],
                ONBOARDING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.onboarding_language)],
                ONBOARDING_TRANSLATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.onboarding_translation)],
                ONBOARDING_DENOMINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.onboarding_denomination)],
                ONBOARDING_STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.onboarding_style)],
                ONBOARDING_PACING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.onboarding_pacing)],
                ONBOARDING_ORDERING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.onboarding_ordering)],
                IDLE: [CommandHandler('read', self.read_command)],
                READING: [CommandHandler('done', self.done_command)],
                DISCUSSION: [
                    CommandHandler('read', self.read_command),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.discussion_handler)
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)]
        )
        
        self.application.add_handler(conv_handler)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        email = self.drive.get_service_account_email()
        await update.message.reply_text(
            "Welcome to your Bible Reading Companion!\n\n"
            "To get started, I need access to a Google Drive folder to store your progress and preferences.\n"
            "1. Please share a folder with my service account:\n"
            f"`{email}`\n"
            "2. Paste the **Folder ID** here.",
            parse_mode='Markdown'
        )
        return DRIVE_SETUP

    async def drive_setup_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        folder_id = update.message.text.strip()
        
        # Verify access by trying to list files
        # We assume if it returns a list (even empty), we have access.
        # Real error handling would catch auth errors.
        try:
            # Offload blocking call
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, self.drive.list_files_in_folder, folder_id
            )
        except Exception as e:
            await update.message.reply_text(f"Could not access that folder. Error: {e}")
            return DRIVE_SETUP

        context.user_data['drive_folder_id'] = folder_id
        
        # Check for existing profile
        loop = asyncio.get_running_loop()
        profile_id = await loop.run_in_executor(
            None, self.drive.get_file_id_by_name, folder_id, 'profile.md'
        )
        
        if profile_id:
            await update.message.reply_text("I found an existing profile in this folder! Welcome back.\n\nType /read to continue your journey.")
            return IDLE
        else:
            await update.message.reply_text("Access confirmed! Let's set up your profile.\n\nFirst, what is your preferred language?")
            return ONBOARDING_LANGUAGE

    async def onboarding_language(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['language'] = update.message.text
        await update.message.reply_text("Great. What is your preferred Bible translation? (e.g., ESV, NIV, KJV)")
        return ONBOARDING_TRANSLATION

    async def onboarding_translation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['translation'] = update.message.text
        await update.message.reply_text("What is your denominational or theological background? (This helps me tailor our discussions)")
        return ONBOARDING_DENOMINATION

    async def onboarding_denomination(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['denomination'] = update.message.text
        await update.message.reply_text("How would you describe your preferred communication style? (e.g., Formal, Casual, Academic, Devotional)")
        return ONBOARDING_STYLE

    async def onboarding_style(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['style'] = update.message.text
        await update.message.reply_text("What is your preferred pacing? (e.g., 1 chapter/day, 15 mins/day)")
        return ONBOARDING_PACING

    async def onboarding_pacing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['pacing'] = update.message.text
        await update.message.reply_text("Finally, what is your preferred reading order? (e.g., Canonical, Chronological, Mix of OT/NT)")
        return ONBOARDING_ORDERING

    async def onboarding_ordering(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['ordering'] = update.message.text
        
        # Save Profile to Drive
        profile_data = {
            'language': context.user_data['language'],
            'translation': context.user_data['translation'],
            'denomination': context.user_data['denomination'],
            'style': context.user_data['style'],
            'pacing': context.user_data['pacing'],
            'ordering': context.user_data['ordering'],
            'current_day': 1
        }
        
        folder_id = context.user_data['drive_folder_id']
        loop = asyncio.get_running_loop()

        # Offload blocking calls
        await loop.run_in_executor(
            None, 
            lambda: self.drive.write_md_file(folder_id, 'profile.md', profile_data, "# User Profile\n\nManaged by BibleBot.")
        )
        
        # Generate initial plan using AI
        await update.message.reply_text("Thank you! I am generating your first reading plan...")
        
        # AI call might be slow too, good to offload
        plan_text = await loop.run_in_executor(
            None, self.ai.generate_reading_plan, str(profile_data)
        )
        
        await loop.run_in_executor(
            None, 
            lambda: self.drive.write_md_file(folder_id, 'reading_plan.md', {'generated_at': 'now'}, plan_text)
        )
        
        await update.message.reply_text(f"Setup Complete! Here is your plan:\n\n{plan_text}\n\nType /read to begin.")
        return IDLE

    async def read_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        folder_id = context.user_data.get('drive_folder_id')
        if not folder_id:
            await update.message.reply_text("Please run /start to set up your profile first.")
            return ConversationHandler.END

        loop = asyncio.get_running_loop()

        # Get Profile
        file_id = await loop.run_in_executor(None, self.drive.get_file_id_by_name, folder_id, 'profile.md')
        if not file_id:
            await update.message.reply_text("Profile not found. Please run /start.")
            return ConversationHandler.END
            
        read_result = await loop.run_in_executor(None, self.drive.read_md_file, file_id)
        if not read_result or read_result[0] is None:
            await update.message.reply_text("Error reading profile. Please try again.")
            return ConversationHandler.END
            
        profile, _ = read_result
        current_day = profile.get('current_day', 1)
        
        # Store profile in user_data for discussion context
        context.user_data['profile'] = profile
        
        # Get Reading Plan
        plan_id = await loop.run_in_executor(None, self.drive.get_file_id_by_name, folder_id, 'reading_plan.md')
        _, plan_body = await loop.run_in_executor(None, self.drive.read_md_file, plan_id)
        
        if not plan_body:
            await update.message.reply_text("Error: Reading plan is empty or missing. Please contact support or restart.")
            return ConversationHandler.END

        # Determine today's reading (naive parsing for now, assuming line by line or Day X format)
        # Check if the plan covers the current day
        if f"Day {current_day}:" not in plan_body and f"Day {current_day} " not in plan_body:
             await update.message.reply_text("Your current reading plan has ended. Generating the next part of your plan...")
             
             # Generate next 7 days
             extension_prompt = (
                 f"The user is on Day {current_day}. "
                 f"Generate a daily Bible reading plan for Day {current_day} to Day {current_day + 6}. "
                 f"Context/Preferences: {str(profile)}\n"
                 "Format the output as a Markdown list with 'Day X: Book Chapter:Verse'."
             )
             new_plan_part = await loop.run_in_executor(
                 None, self.ai.generate_response, extension_prompt
             )
             
             # Append to existing plan
             plan_body += f"\n\n{new_plan_part}"
             await loop.run_in_executor(
                 None, 
                 lambda: self.drive.write_md_file(folder_id, 'reading_plan.md', {'generated_at': 'now'}, plan_body, file_id=plan_id)
             )

        # In a real scenario, we'd parse 'plan_body' to find the specific verses.
        # Here we ask Gemini to extract/confirm the reading for Day X from the plan text.
        extraction_prompt = f"From this plan:\n{plan_body}\n\nWhat is the reading for Day {current_day}? Return ONLY the Bible reference."
        reading_ref = await loop.run_in_executor(None, self.ai.generate_response, extraction_prompt)
        reading_ref = reading_ref.strip()
        
        # Fetch Text
        scripture_text = await loop.run_in_executor(
            None, 
            lambda: self.ai.get_bible_text(reading_ref, translation=profile.get('translation', 'ESV'))
        )
        
        context.user_data['current_reading_ref'] = reading_ref
        context.user_data['current_scripture'] = scripture_text
        
        await update.message.reply_text(f"**Day {current_day}: {reading_ref}**\n\n{scripture_text}\n\nWhen you are finished reading, type /done.")
        return READING

    async def done_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        folder_id = context.user_data.get('drive_folder_id')
        loop = asyncio.get_running_loop()
        
        # Update Progress in Profile
        file_id = await loop.run_in_executor(None, self.drive.get_file_id_by_name, folder_id, 'profile.md')
        profile, body = await loop.run_in_executor(None, self.drive.read_md_file, file_id)
        
        profile['current_day'] = profile.get('current_day', 1) + 1
        await loop.run_in_executor(
            None, 
            lambda: self.drive.write_md_file(folder_id, 'profile.md', profile, body, file_id=file_id)
        )
        
        # Initialize Chat History for this session
        context.user_data['chat_history'] = []
        
        await update.message.reply_text("Great job! What stood out to you in today's reading? Let's talk about it.")
        return DISCUSSION

    async def discussion_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_input = update.message.text
        reading_context = context.user_data.get('current_scripture', 'The Bible')
        profile = context.user_data.get('profile', {})
        loop = asyncio.get_running_loop()
        folder_id = context.user_data.get('drive_folder_id')

        # Retrieve persistent chat history
        # 1. Try memory
        history = context.user_data.get('chat_history')
        
        # 2. If missing, try Drive
        chat_file_id = await loop.run_in_executor(None, self.drive.get_file_id_by_name, folder_id, 'chat_history.md')
        
        if history is None:
            if chat_file_id:
                meta, _ = await loop.run_in_executor(None, self.drive.read_md_file, chat_file_id)
                history = meta.get('history', [])
            else:
                history = []

        # Generate Response using existing history
        response = await loop.run_in_executor(
            None, 
            lambda: self.ai.discuss_reading(user_input, list(history), reading_context, profile=profile)
        )
        
        # Append User input and Model response to history
        history.append({'role': 'user', 'parts': [user_input]})
        history.append({'role': 'model', 'parts': [response]})
        
        # Keep window small (last 10 turns)
        if len(history) > 10:
            history = history[-10:]

        context.user_data['chat_history'] = history
        
        # Persist Chat Log to Drive
        # We save the structured history in Frontmatter for state recovery
        # And the readable text in the body for the user
        if chat_file_id:
            meta, content = await loop.run_in_executor(None, self.drive.read_md_file, chat_file_id)
            meta['history'] = history
            new_content = content + f"\n\n**User:** {user_input}\n**Bot:** {response}"
            await loop.run_in_executor(
                None, 
                lambda: self.drive.write_md_file(folder_id, 'chat_history.md', meta, new_content, file_id=chat_file_id)
            )
        else:
            meta = {'created': 'now', 'history': history}
            new_content = f"**User:** {user_input}\n**Bot:** {response}"
            await loop.run_in_executor(
                None, 
                lambda: self.drive.write_md_file(folder_id, 'chat_history.md', meta, new_content)
            )

        await update.message.reply_text(response)
        return DISCUSSION

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Operation cancelled.")
        return ConversationHandler.END

    def run(self):
        webhook_url = os.environ.get('WEBHOOK_URL')
        port = int(os.environ.get('PORT', '8080'))
        is_cloud_run = os.environ.get('K_SERVICE') is not None

        if webhook_url:
            logger.info(f"Starting in Webhook mode. Listening on port {port}...")
            self.application.run_webhook(
                listen="0.0.0.0",
                port=port,
                webhook_url=webhook_url,
                allowed_updates=Update.ALL_TYPES
            )
        elif is_cloud_run:
            logger.warning(f"WEBHOOK_URL not set. Detected Cloud Run environment. Starting dummy server on port {port} to pass health check.")

            class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"Service is running. Please set WEBHOOK_URL to enable the bot.")

            # Allow address reuse to avoid 'Address already in use' errors during restarts
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
                logger.info(f"Serving health check on port {port}")
                httpd.serve_forever()
        else:
            logger.info("Starting in Polling mode...")
            self.application.run_polling()

if __name__ == '__main__':
    # Initialize Dependencies
    token = os.environ.get('TELEGRAM_TOKEN')
    drive = GoogleDriveManager()
    ai = GeminiAgent()
    
    if not token:
        logger.error("No TELEGRAM_TOKEN found!")
        exit(1)

    bot = BibleBot(token, drive, ai)
    bot.run()
