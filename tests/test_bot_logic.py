import unittest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
import sys
import os
import asyncio

# Ensure src can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

# We need to mock the imports in bot.py before importing it
# because they are now relative imports, but here we run as a script
# Alternatively, we can patch sys.modules or just fix the path.
# Since we fixed imports to be relative, running `from src.bot` works if we are at root.
# But inside tests/, we need to be careful.
# Let's adjust the python path so `src` is a package.

from src.bot import BibleBot, DRIVE_SETUP, ONBOARDING_LANGUAGE, IDLE, READING, DISCUSSION

class TestBibleBotLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_drive = MagicMock()
        self.mock_ai = MagicMock()
        self.bot = BibleBot("dummy_token", self.mock_drive, self.mock_ai)
        
        # Mock Context and Update
        self.mock_update = AsyncMock()
        self.mock_context = MagicMock()
        self.mock_context.user_data = {}
        
        # Mock the event loop executor
        # Since we use loop.run_in_executor(None, func, args...), we can mock run_in_executor
        # to just call the function immediately or return a value.
        self.mock_loop = MagicMock()
        # We removed usage of context.application.loop, so we don't mock it there.
        # Instead, we need to ensure asyncio.get_running_loop() returns our mock loop,
        # OR we rely on IsolatedAsyncioTestCase's loop but we mock the run_in_executor method 
        # of the *current* loop.
        
        # However, IsolatedAsyncioTestCase manages its own loop.
        # To make things simple, we can patch asyncio.get_running_loop to return our mock.
        self.loop_patcher = patch('asyncio.get_running_loop', return_value=self.mock_loop)
        self.loop_patcher.start()
        
        async def async_executor(executor, func, *args):
            if callable(func):
                return func(*args)
            return func
            
        self.mock_loop.run_in_executor.side_effect = async_executor

    def tearDown(self):
        self.loop_patcher.stop()

    async def test_start_command(self):
        """Test the /start command triggers DRIVE_SETUP state."""
        state = await self.bot.start(self.mock_update, self.mock_context)
        self.assertEqual(state, DRIVE_SETUP)
        self.mock_update.message.reply_text.assert_called_once()

    async def test_drive_setup_success(self):
        """Test valid drive folder ID transitions to ONBOARDING when no profile exists."""
        self.mock_update.message.text = "valid_folder_id"
        self.mock_drive.list_files_in_folder.return_value = [{'id': '1', 'name': 'test'}]
        # Mock no existing profile
        self.mock_drive.get_file_id_by_name.return_value = None
        
        state = await self.bot.drive_setup_handler(self.mock_update, self.mock_context)
        
        self.assertEqual(state, ONBOARDING_LANGUAGE)
        self.assertEqual(self.mock_context.user_data['drive_folder_id'], "valid_folder_id")

    async def test_drive_setup_existing_profile(self):
        """Test valid drive folder ID transitions to IDLE when profile exists."""
        self.mock_update.message.text = "valid_folder_id"
        self.mock_drive.list_files_in_folder.return_value = [{'id': '1', 'name': 'test'}]
        # Mock existing profile
        self.mock_drive.get_file_id_by_name.return_value = "existing_profile_id"
        
        state = await self.bot.drive_setup_handler(self.mock_update, self.mock_context)
        
        self.assertEqual(state, IDLE)
        self.assertEqual(self.mock_context.user_data['drive_folder_id'], "valid_folder_id")
        # Ensure we didn't ask onboarding questions
        self.assertIn("Welcome back", self.mock_update.message.reply_text.call_args[0][0])

    async def test_onboarding_flow(self):
        """Test the sequence of onboarding questions."""
        # Setup context
        self.mock_context.user_data['drive_folder_id'] = "fid"
        
        # Language -> Translation
        self.mock_update.message.text = "English"
        state = await self.bot.onboarding_language(self.mock_update, self.mock_context)
        self.assertEqual(state, 2) # ONBOARDING_TRANSLATION
        
        # Translation -> Denomination
        self.mock_update.message.text = "ESV"
        state = await self.bot.onboarding_translation(self.mock_update, self.mock_context)
        self.assertEqual(state, 3) # ONBOARDING_DENOMINATION
        
        # ... skip to saving profile
        self.mock_context.user_data.update({
            'language': 'En', 'translation': 'ESV', 'denomination': 'None',
            'style': 'Casual', 'pacing': 'Fast'
        })
        self.mock_update.message.text = "Canonical" # Ordering
        
        # Mock AI generation for plan
        self.mock_ai.generate_reading_plan.return_value = "Day 1: Genesis 1"
        
        state = await self.bot.onboarding_ordering(self.mock_update, self.mock_context)
        
        self.assertEqual(state, IDLE)
        # Check if profile was saved
        # Note: Since we used a lambda in run_in_executor, verifying arguments of write_md_file
        # directly on mock_drive might fail if the lambda hasn't executed or if checking logic is strict.
        # But our side_effect executes it.
        self.mock_drive.write_md_file.assert_any_call("fid", 'profile.md', ANY, "# User Profile\n\nManaged by BibleBot.")
        # Check if plan was saved
        self.mock_drive.write_md_file.assert_any_call("fid", 'reading_plan.md', ANY, "Day 1: Genesis 1")

    async def test_read_command_success(self):
        """Test /read command fetches text and transitions to READING."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        
        # Mock Profile and Plan exists
        self.mock_drive.get_file_id_by_name.side_effect = ["p_id", "plan_id"]
        self.mock_drive.read_md_file.side_effect = [
            ({'current_day': 1, 'translation': 'ESV'}, "body"), # Profile
            ({}, "Day 1: Gen 1") # Plan
        ]
        
        self.mock_ai.generate_response.return_value = "Genesis 1" # Extracted Ref
        self.mock_ai.get_bible_text.return_value = "In the beginning..."
        
        state = await self.bot.read_command(self.mock_update, self.mock_context)
        
        self.assertEqual(state, READING)
        self.assertIn("In the beginning...", self.mock_context.user_data['current_scripture'])

    async def test_read_command_extends_plan(self):
        """Test /read command extends plan if day not found."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        
        # Mock Profile and Plan exists but Day 8 requested
        self.mock_drive.get_file_id_by_name.side_effect = ["p_id", "plan_id"]
        self.mock_drive.read_md_file.side_effect = [
            ({'current_day': 8, 'translation': 'ESV'}, "body"), # Profile (Day 8)
            ({}, "Day 1... Day 7...") # Plan (Only 7 days)
        ]
        
        self.mock_ai.generate_response.side_effect = [
            "Day 8: Gen 20", # Extension
            "Gen 20" # Extraction
        ]
        self.mock_ai.get_bible_text.return_value = "Text"
        
        state = await self.bot.read_command(self.mock_update, self.mock_context)
        
        # Check that extension prompt was called
        # The first call to generate_response should be the extension
        args, _ = self.mock_ai.generate_response.call_args_list[0]
        self.assertIn("Day 8 to Day 14", args[0])
        
        # Check plan updated
        self.mock_drive.write_md_file.assert_called()

    async def test_done_command(self):
        """Test /done updates progress and transitions to DISCUSSION."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        self.mock_drive.get_file_id_by_name.return_value = "p_id"
        self.mock_drive.read_md_file.return_value = ({'current_day': 1}, "body")
        
        state = await self.bot.done_command(self.mock_update, self.mock_context)
        
        self.assertEqual(state, DISCUSSION)
        # Verify day incremented
        self.mock_drive.write_md_file.assert_called()
        # Verify the call arguments specifically for the profile update
        # We need to find the call that matches profile.md
        calls = self.mock_drive.write_md_file.call_args_list
        found = False
        for call in calls:
            if call[0][1] == 'profile.md':
                self.assertEqual(call[0][2]['current_day'], 2)
                found = True
        self.assertTrue(found)

    async def test_discussion_flow(self):
        """Test discussion handler uses AI and saves history."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        self.mock_context.user_data['profile'] = {'denomination': 'Baptist'}
        # Initialize empty history
        self.mock_context.user_data['chat_history'] = []
        
        self.mock_update.message.text = "What does this mean?"
        self.mock_ai.discuss_reading.return_value = "It means..."
        
        # Mock finding chat history file
        self.mock_drive.get_file_id_by_name.return_value = None # New file
        
        state = await self.bot.discussion_handler(self.mock_update, self.mock_context)
        
        self.assertEqual(state, DISCUSSION)
        self.mock_drive.write_md_file.assert_called_with(
            "fid", 'chat_history.md', ANY, ANY
        )
        
        # Verify that profile was passed to discuss_reading
        # Also verify that history passed to AI does NOT contain the new message yet
        # (It should be empty list in this case)
        self.mock_ai.discuss_reading.assert_called_with(
            "What does this mean?", [], ANY, profile={'denomination': 'Baptist'}
        )
        
        # Verify history is updated afterwards
        history = self.mock_context.user_data['chat_history']
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['role'], 'user')
        self.assertEqual(history[1]['role'], 'model')

    async def test_read_command_empty_plan(self):
        """Test /read command handles empty plan gracefully."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        
        self.mock_drive.get_file_id_by_name.side_effect = ["p_id", "plan_id"]
        self.mock_drive.read_md_file.side_effect = [
            ({'current_day': 1}, "body"), 
            ({}, "") # Empty plan
        ]
        
        # ConversationHandler.END is -1 usually, but here we check what it returns
        # The code returns ConversationHandler.END
        from telegram.ext import ConversationHandler
        state = await self.bot.read_command(self.mock_update, self.mock_context)
        
        self.assertEqual(state, ConversationHandler.END)
        self.mock_update.message.reply_text.assert_called_with(
            "Error: Reading plan is empty or missing. Please contact support or restart."
        )

    async def test_discussion_to_read_transition(self):
        """Test transitioning from DISCUSSION to READING via /read command."""
        # This test verifies that the /read command handler is accessible from DISCUSSION state.
        # Ideally, we'd test the ConversationHandler routing, but that's complex to mock.
        # Instead, we verify that read_command logic still works if called (logic is stateless regarding origin state).
        # And we rely on the ConversationHandler setup verification in code review.
        # But we can simulate the flow by setting up context as if we were in discussion.
        
        self.mock_context.user_data['drive_folder_id'] = "fid"
        
        # Mock Profile and Plan
        self.mock_drive.get_file_id_by_name.side_effect = ["p_id", "plan_id"]
        self.mock_drive.read_md_file.side_effect = [
            ({'current_day': 2, 'translation': 'ESV'}, "body"), 
            ({}, "Day 2: Gen 2")
        ]
        
        self.mock_ai.generate_response.return_value = "Genesis 2"
        self.mock_ai.get_bible_text.return_value = "Creation..."
        
        state = await self.bot.read_command(self.mock_update, self.mock_context)
        
        self.assertEqual(state, READING)
        self.assertEqual(self.mock_context.user_data['current_reading_ref'], "Genesis 2")

if __name__ == '__main__':
    unittest.main()
