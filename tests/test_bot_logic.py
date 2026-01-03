import unittest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
import sys
import os
import asyncio

# Ensure src can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

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
        self.mock_loop = MagicMock()
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
        # Verify message mentions manual file creation
        args = self.mock_update.message.reply_text.call_args[0][0]
        self.assertIn("create 3 empty files", args)

    async def test_drive_setup_success_new_user_write_ok(self):
        """Test valid folder, no profile, write access OK -> ONBOARDING."""
        self.mock_update.message.text = "valid_folder_id"
        self.mock_drive.list_files_in_folder.return_value = [{'id': '1', 'name': 'test'}]
        # Mock no existing profile
        self.mock_drive.get_file_id_by_name.return_value = None
        # Mock successful write test
        self.mock_drive.write_md_file.return_value = "test_file_id"
        
        state = await self.bot.drive_setup_handler(self.mock_update, self.mock_context)
        
        self.assertEqual(state, ONBOARDING_LANGUAGE)
        self.assertEqual(self.mock_context.user_data['drive_folder_id'], "valid_folder_id")
        self.mock_drive.delete_file.assert_called_with("test_file_id")

    async def test_drive_setup_quota_error(self):
        """Test valid folder, no profile, write access fails (Quota) -> Ask User."""
        self.mock_update.message.text = "valid_folder_id"
        self.mock_drive.list_files_in_folder.return_value = [{'id': '1', 'name': 'test'}]
        self.mock_drive.get_file_id_by_name.return_value = None

        # Mock write failure with Quota message
        self.mock_drive.write_md_file.side_effect = Exception("Service Accounts do not have storage quota")

        state = await self.bot.drive_setup_handler(self.mock_update, self.mock_context)

        self.assertEqual(state, DRIVE_SETUP)
        # Verify instructions
        args = self.mock_update.message.reply_text.call_args[0][0]
        self.assertIn("manually create these **empty files**", args)

    async def test_drive_setup_existing_profile_full(self):
        """Test valid folder, profile exists and has data -> IDLE (Welcome Back)."""
        self.mock_update.message.text = "valid_folder_id"
        self.mock_drive.list_files_in_folder.return_value = [{'id': '1', 'name': 'test'}]
        # Mock existing profile
        self.mock_drive.get_file_id_by_name.return_value = "existing_profile_id"
        # Mock reading profile with data
        self.mock_drive.read_md_file.return_value = ({'language': 'en'}, "body")
        
        state = await self.bot.drive_setup_handler(self.mock_update, self.mock_context)
        
        self.assertEqual(state, IDLE)
        self.assertIn("Welcome back", self.mock_update.message.reply_text.call_args[0][0])

    async def test_drive_setup_existing_profile_empty(self):
        """Test valid folder, profile exists but empty -> ONBOARDING."""
        self.mock_update.message.text = "valid_folder_id"
        self.mock_drive.list_files_in_folder.return_value = [{'id': '1', 'name': 'test'}]
        self.mock_drive.get_file_id_by_name.return_value = "existing_profile_id"
        # Mock reading empty profile
        self.mock_drive.read_md_file.return_value = ({}, "")

        state = await self.bot.drive_setup_handler(self.mock_update, self.mock_context)

        self.assertEqual(state, ONBOARDING_LANGUAGE)
        self.assertIn("empty profile.md", self.mock_update.message.reply_text.call_args[0][0])

    async def test_onboarding_flow(self):
        """Test the sequence of onboarding questions."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        
        # Skip to saving
        self.mock_context.user_data.update({
            'language': 'En', 'translation': 'ESV', 'denomination': 'None',
            'style': 'Casual', 'pacing': 'Fast'
        })
        self.mock_update.message.text = "Canonical" # Ordering
        
        self.mock_ai.generate_reading_plan.return_value = "Day 1: Genesis 1"
        
        state = await self.bot.onboarding_ordering(self.mock_update, self.mock_context)
        
        self.assertEqual(state, IDLE)
        # Check if profile was saved
        self.mock_drive.write_md_file.assert_any_call("fid", 'profile.md', ANY, "# User Profile\n\nManaged by BibleBot.")
        # Check if plan was saved
        self.mock_drive.write_md_file.assert_any_call("fid", 'reading_plan.md', ANY, "Day 1: Genesis 1")

    async def test_read_command_success(self):
        """Test /read command fetches text and transitions to READING."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        
        self.mock_drive.get_file_id_by_name.side_effect = ["p_id", "plan_id"]
        self.mock_drive.read_md_file.side_effect = [
            ({'current_day': 1, 'translation': 'ESV'}, "body"), # Profile
            ({}, "Day 1: Gen 1") # Plan
        ]
        
        self.mock_ai.generate_response.return_value = "Genesis 1"
        self.mock_ai.get_bible_text.return_value = "In the beginning..."
        
        state = await self.bot.read_command(self.mock_update, self.mock_context)
        
        self.assertEqual(state, READING)

    async def test_done_command(self):
        """Test /done updates progress and transitions to DISCUSSION."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        self.mock_drive.get_file_id_by_name.return_value = "p_id"
        self.mock_drive.read_md_file.return_value = ({'current_day': 1}, "body")
        
        state = await self.bot.done_command(self.mock_update, self.mock_context)
        
        self.assertEqual(state, DISCUSSION)
        self.mock_drive.write_md_file.assert_called()

    async def test_discussion_flow(self):
        """Test discussion handler uses AI and saves history."""
        self.mock_context.user_data['drive_folder_id'] = "fid"
        self.mock_context.user_data['profile'] = {'denomination': 'Baptist'}
        self.mock_context.user_data['chat_history'] = []
        
        self.mock_update.message.text = "What does this mean?"
        self.mock_ai.discuss_reading.return_value = "It means..."
        
        self.mock_drive.get_file_id_by_name.return_value = None
        
        state = await self.bot.discussion_handler(self.mock_update, self.mock_context)
        
        self.assertEqual(state, DISCUSSION)
        self.mock_drive.write_md_file.assert_called_with(
            "fid", 'chat_history.md', ANY, ANY
        )

if __name__ == '__main__':
    unittest.main()
