import unittest
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import asyncio
import os
import io
import json
from market.agents.shark import Shark, LLMResponseError, FatalAgentError
from opencode_ai.types import (
    TextPart,
    ToolPart,
    ToolStateRunning,
    ToolStateCompleted
)
from opencode_ai.types.event_list_response import EventMessagePartUpdated
from market.core.state import MarketState, MarketAsset, AgentPortfolio
from opencode_ai import APITimeoutError, APIConnectionError
from market.orchestrator import AgentAction

class SharkTest(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def setup_mock_stream(self, MockClient, content_text):
        # 1. Mock event.list() for tracing
        mock_event = MagicMock(spec=EventMessagePartUpdated)
        mock_event.properties = MagicMock()
        mock_part = MagicMock(spec=TextPart)
        mock_part.text = content_text
        mock_part.session_id = "ses_123"
        mock_part.id = "p1"
        mock_event.properties.part = mock_part
        
        async def mock_iter():
            yield mock_event
            
        mock_stream = AsyncMock()
        mock_stream.__aiter__.side_effect = lambda: mock_iter()
        mock_stream.close = AsyncMock()
        
        # AsyncOpencode() instance
        client_inst = MockClient.return_value
        client_inst.event.list = AsyncMock(return_value=mock_stream)
        client_inst.close = AsyncMock()
        
        # 2. Mock session.chat()
        client_inst.session.chat = AsyncMock()
        
        # 3. Mock session.messages() for content retrieval
        mock_msg_item = MagicMock()
        mock_msg_item.parts = [mock_part]
        client_inst.session.messages = AsyncMock(return_value=[mock_msg_item])

    @patch('market.agents.shark.subprocess.run')
    @patch('market.agents.shark.asyncio.create_subprocess_shell') # Mock shell for git add
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.isdir') # Changed from exists to isdir
    @patch('market.agents.shark.os.listdir')
    @patch('market.agents.shark.open', new_callable=mock_open)
    async def test_format_state_prompt_content(self, mock_file, mock_listdir, mock_isdir, mock_exec, mock_shell, mock_run):
        # Setup State
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Solve X")
        cand_path = "/tmp/cand_0"
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path=cand_path)
        
        ver_path = "/tmp/v_1"
        state.assets["v_1"] = MarketAsset("v_1", "VERIFIER", "Test V", test_path=ver_path)
        
        shark = Shark("agent_0")
        
        # Mocks
        mock_isdir.return_value = True
        
        # Mock Verifier Files
        def listdir_side_effect(path):
            if path == ver_path: return ["run.sh", "test.py"]
            return []
        mock_listdir.side_effect = listdir_side_effect

        # Mock File Content
        file_content_map = {
            f"{ver_path}/run.sh": "#!/bin/bash",
            f"{ver_path}/test.py": "import unittest"
        }
        def open_mock(file, *args, **kwargs):
            return mock_open(read_data=file_content_map.get(str(file), "")).return_value
        mock_file.side_effect = open_mock

        # Mock 'git add .'
        mock_shell_process = MagicMock()
        mock_shell_process.wait = AsyncMock()
        mock_shell.return_value = mock_shell_process

        # Mock 'git diff'
        mock_process = MagicMock()
        # communicate returns (stdout, stderr)
        mock_process.communicate = AsyncMock(return_value=(
            b"diff --git a/main.py b/main.py\n@@ -1 +1 @@\ndiff output line 1\n+ line 2\n",
            b""
        ))
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        # Call Method
        prompt = await shark._format_state_prompt(state)
        
        # Assertions
        self.assertIn("You are Agent: agent_0", prompt)
        self.assertIn("=== Candidate Code Changes (Diffs) ===", prompt)
        self.assertIn("diff output line 1", prompt)
        self.assertIn("=== Verifier Code ===", prompt)

    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.isdir')
    async def test_format_state_prompt_no_error_on_valid_diff(self, mock_isdir, mock_exec, mock_shell):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_isdir.return_value = True
        
        # Mock git add
        mock_shell.return_value.wait = AsyncMock()

        # Mock successful diff with changes
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(
            b"diff --git a/file.py b/file.py\n@@ -1 +1 @@\nsome diff content\n",
            b""
        ))
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        prompt = await shark._format_state_prompt(state)
        
        self.assertIn("some diff content", prompt)

    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.isdir')
    async def test_format_state_prompt_handles_timeout(self, mock_isdir, mock_exec, mock_shell):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_isdir.return_value = True
        
        mock_shell.return_value.wait = AsyncMock()

        mock_process = MagicMock()
        # Mock an exception during communicate (simulating timeout or crash)
        mock_process.communicate = AsyncMock(side_effect=Exception("Timeout or Crash"))
        mock_exec.return_value = mock_process
        
        prompt = await shark._format_state_prompt(state)
        
        self.assertIn("[Error: Timeout or Crash]", prompt)

    @patch('market.agents.shark.asyncio.create_subprocess_shell')
    @patch('market.agents.shark.asyncio.create_subprocess_exec')
    @patch('market.agents.shark.os.path.isdir')
    async def test_format_state_prompt_no_diff(self, mock_isdir, mock_exec, mock_shell):
        state = MarketState(round_num=1, liquidity_b=10.0, prompt="Fix Bug")
        state.assets["cand_0"] = MarketAsset("cand_0", "CANDIDATE", "Desc", code_path="/tmp/cand_0")
        
        shark = Shark("agent_0")
        mock_isdir.return_value = True
        
        mock_shell.return_value.wait = AsyncMock()

        # Mock empty diff
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        prompt = await shark._format_state_prompt(state)
        
        self.assertIn("--- cand_0 Diff ---", prompt)
        self.assertIn("(No changes from baseline)", prompt)

class TestSharkActionParsing(unittest.IsolatedAsyncioTestCase):

    def setup_mock_stream(self, MockClient, content_text):
        # 1. Mock event.list() for tracing
        mock_event = MagicMock(spec=EventMessagePartUpdated)
        mock_event.properties = MagicMock()
        mock_part = MagicMock(spec=TextPart)
        mock_part.text = content_text
        mock_part.session_id = "ses_123"
        mock_part.id = "p1"
        mock_event.properties.part = mock_part
        
        async def mock_iter():
            yield mock_event
            
        mock_stream = AsyncMock()
        mock_stream.__aiter__.side_effect = lambda: mock_iter()
        mock_stream.close = AsyncMock()
        
        # AsyncOpencode() instance
        client_inst = MockClient.return_value
        client_inst.event.list = AsyncMock(return_value=mock_stream)
        client_inst.close = AsyncMock()
        
        # 2. Mock session.chat()
        client_inst.session.chat = AsyncMock()
        
        # 3. Mock session.messages() for content retrieval
        mock_msg_item = MagicMock()
        mock_msg_item.parts = [mock_part]
        client_inst.session.messages = AsyncMock(return_value=[mock_msg_item])

    @patch('market.agents.shark.AsyncOpencode')
    async def test_parsing_success_markdown(self, MockClient):
        # Mock successful JSON in markdown
        self.setup_mock_stream(MockClient, 'Some reasoning... ```json\n{"beliefs": {"cand_0": 0.9}, "proposals": []}\n```')
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        MockClient.return_value.session.create = AsyncMock(return_value=mock_session)

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")
        
        action = await shark.get_action(state)
        self.assertEqual(action.beliefs["cand_0"], 0.9)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_parsing_success_raw(self, MockClient):
        # Mock successful raw JSON
        self.setup_mock_stream(MockClient, '{"beliefs": {"cand_0": 0.8}, "proposals": []}')
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        MockClient.return_value.session.create = AsyncMock(return_value=mock_session)

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")
        
        action = await shark.get_action(state)
        self.assertEqual(action.beliefs["cand_0"], 0.8)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_parsing_failure_no_json(self, MockClient):
        # Mock blabber with no JSON
        self.setup_mock_stream(MockClient, 'I am thinking about Fibonacci but I will not give you JSON today.')
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        MockClient.return_value.session.create = AsyncMock(return_value=mock_session)

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")
        
        # We expect FatalAgentError after all self-correction attempts fail
        with self.assertRaises(FatalAgentError):
            await shark.get_action(state)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_parsing_malformed_json_recovery(self, MockClient):
        # Mock malformed JSON that has a valid block inside
        self.setup_mock_stream(MockClient, 'Here is a list: { "item": 1 } and here is the real answer: {"beliefs": {"cand_0": 0.5}}')
        
        mock_session = MagicMock()
        mock_session.id = "ses_123"
        MockClient.return_value.session.create = AsyncMock(return_value=mock_session)

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")
        
        action = await shark.get_action(state)
        self.assertEqual(action.beliefs["cand_0"], 0.5)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_get_action_fallback_on_exception(self, MockClient):
        # Mock successful session creation but chat raises an Exception
        mock_session = MagicMock()
        mock_session.id = "ses_123"

        mock_client_instance = MockClient.return_value
        mock_client_instance.session.create = AsyncMock(return_value=mock_session)

        # Mock context manager to raise exception
        mock_cm = AsyncMock()
        mock_cm.__aenter__.side_effect = Exception("API error")
        mock_client_instance.session.with_streaming_response.chat.return_value = mock_cm

        state = MarketState(round_num=1, liquidity_b=100.0)
        shark = Shark("agent_0")

        # Verify it raises FatalAgentError
        with self.assertRaises(FatalAgentError):
            await shark.get_action(state)

class TestSharkTraceLogging(unittest.IsolatedAsyncioTestCase):

    @patch('market.agents.shark.AsyncOpencode')
    @patch('market.agents.shark.open', new_callable=mock_open)
    async def test_chat_logs_prompt(self, mock_file, MockClient):
        shark = Shark("agent_0", trace_path="/tmp/trace.txt")
        shark.session = MagicMock()
        shark.session.id = "ses_123"

        # 1. Mock event.list()
        mock_event = MagicMock(spec=EventMessagePartUpdated)
        mock_event.properties = MagicMock()
        mock_part = MagicMock(spec=TextPart)
        mock_part.text = '{"beliefs": {}}'
        mock_part.session_id = "ses_123"
        mock_part.id = "p1"
        mock_event.properties.part = mock_part

        async def mock_iter():
            yield mock_event
            
        mock_stream = AsyncMock()
        mock_stream.__aiter__.side_effect = lambda: mock_iter()
        mock_stream.close = AsyncMock()
        
        client_inst = MockClient.return_value
        client_inst.event.list = AsyncMock(return_value=mock_stream)
        client_inst.close = AsyncMock()
        
        # 2. Mock session.chat()
        client_inst.session.chat = AsyncMock()
        
        # 3. Mock session.messages()
        mock_msg_item = MagicMock()
        mock_msg_item.parts = [mock_part]
        client_inst.session.messages = AsyncMock(return_value=[mock_msg_item])

        await shark._chat_with_network_retry("Hello")

        # Verify prompt was written to trace
        found_prompt = False
        # mock_file.call_args_list contains calls to open()
        handle = mock_file()
        for write_call in handle.write.call_args_list:
            if "[PROMPT]\nHello" in write_call[0][0]:
                found_prompt = True

        self.assertTrue(found_prompt)

    @patch('market.agents.shark.AsyncOpencode')
    @patch('market.agents.shark.open', new_callable=mock_open)
    async def test_capture_sse_events_tool_calls(self, mock_file, MockClient):
        shark = Shark("agent_0", trace_path="/tmp/trace.txt")
        shark.session = MagicMock()
        shark.session.id = "ses_123"

        # 1. Mock SSE stream events
        mock_event_before = MagicMock(spec=EventMessagePartUpdated)
        mock_event_before.type = 'message.part.updated'
        mock_event_before.properties = MagicMock()
        mock_part_before = MagicMock(spec=ToolPart)
        mock_part_before.type = "tool"
        mock_part_before.tool = "run_bash"
        mock_part_before.session_id = "ses_123"
        mock_part_before.id = "p_tool"
        mock_part_before.state = MagicMock(spec=ToolStateRunning)
        mock_part_before.state.status = "running"
        mock_part_before.state.input = "ls"
        mock_event_before.properties.part = mock_part_before

        mock_event_after = MagicMock(spec=EventMessagePartUpdated)
        mock_event_after.type = 'message.part.updated'
        mock_event_after.properties = MagicMock()
        mock_part_after = MagicMock(spec=ToolPart)
        mock_part_after.type = "tool"
        mock_part_after.tool = "run_bash"
        mock_part_after.session_id = "ses_123"
        mock_part_after.id = "p_tool"
        mock_part_after.state = MagicMock(spec=ToolStateCompleted)
        mock_part_after.state.status = "completed"
        mock_part_after.state.output = "file.txt"
        mock_event_after.properties.part = mock_part_after

        # For the final retrieval, we need a text part
        mock_part_text = MagicMock(spec=TextPart)
        mock_part_text.text = '{"beliefs": {}}'

        async def mock_iter():
            yield mock_event_before
            yield mock_event_after
            
        mock_stream = AsyncMock()
        mock_stream.__aiter__.side_effect = lambda: mock_iter()
        mock_stream.close = AsyncMock()
        
        client_inst = MockClient.return_value
        client_inst.event.list = AsyncMock(return_value=mock_stream)
        client_inst.close = AsyncMock()
        
        # 2. Mock session.chat()
        client_inst.session.chat = AsyncMock()
        
        # 3. Mock session.messages()
        mock_msg_item = MagicMock()
        mock_msg_item.parts = [mock_part_before, mock_part_after, mock_part_text]
        client_inst.session.messages = AsyncMock(return_value=[mock_msg_item])

        # Run the chat logic (which now captures events in-line)
        await shark._chat_with_network_retry("test prompt")

        # Verify all events were written
        written_content = ""
        handle = mock_file()
        for call in handle.write.call_args_list:
            written_content += call[0][0]

        self.assertIn("[TOOL CALL: run_bash(ls)]", written_content)
        self.assertIn("[TOOL RESULT: file.txt]", written_content)

class TestSharkRetryLogic(unittest.IsolatedAsyncioTestCase):
    @patch('market.agents.shark.AsyncOpencode')
    @patch('market.agents.shark.asyncio.sleep')
    async def test_get_action_retry_on_timeout(self, mock_sleep, MockClient):
        # 1. Setup Shark with short base timeout for testing
        shark = Shark("agent_0", max_retries=2, timeout=1.0, max_backoff=10.0)
        shark.initialize_session = AsyncMock()
        shark.session = MagicMock()
        shark.session.id = "ses_123"
        shark.interrupt = AsyncMock()
        
        # 2. Mock _chat_with_network_retry to fail twice with timeout, then succeed
        with patch.object(Shark, '_chat_with_network_retry') as mock_chat:
            mock_chat.side_effect = [
                APITimeoutError("Timeout!"),
                APITimeoutError("Timeout again!"),
                '{"beliefs": {"cand_0": 0.5}}'
            ]
            
            state = MarketState(round_num=1, liquidity_b=100.0)
            action = await shark.get_action(state)
            
            # 3. Assertions
            self.assertEqual(action.beliefs["cand_0"], 0.5)
            self.assertEqual(mock_chat.call_count, 3)
            self.assertEqual(shark.interrupt.call_count, 2)
            
            # Verify NO sleep occurs (immediate retry)
            self.assertEqual(mock_sleep.call_count, 0)
            
            # Verify timeout scaling: 1.0, then 2.0, then 4.0
            calls = mock_chat.call_args_list
            self.assertEqual(calls[0].kwargs.get("timeout"), 1.0)
            self.assertEqual(calls[1].kwargs.get("timeout"), 2.0)
            self.assertEqual(calls[2].kwargs.get("timeout"), 4.0)
            
            # Verify prompt updates
            self.assertIn("You are Agent: agent_0", calls[0][0][0]) # First call has full state
            self.assertIn("TIMEOUT: Your previous response took more than 1.0s", calls[1][0][0])
            self.assertIn("You have 2.0s for this attempt", calls[1][0][0])
            self.assertIn("TIMEOUT: Your previous response took more than 2.0s", calls[2][0][0])
            self.assertIn("You have 4.0s for this attempt", calls[2][0][0])

    @patch('market.agents.shark.AsyncOpencode')
    @patch('market.agents.shark.asyncio.sleep')
    async def test_get_action_retry_on_parsing_error(self, mock_sleep, MockClient):
        shark = Shark("agent_0", max_retries=2)
        shark.initialize_session = AsyncMock()
        shark.session = MagicMock()
        shark.session.id = "ses_123"
        
        with patch.object(Shark, '_chat_with_network_retry') as mock_chat:
            mock_chat.side_effect = [
                "Not JSON",
                '{"beliefs": {"cand_0": 0.7}}'
            ]
            
            state = MarketState(round_num=1, liquidity_b=100.0)
            action = await shark.get_action(state)
            
            self.assertEqual(action.beliefs["cand_0"], 0.7)
            self.assertEqual(mock_chat.call_count, 2)
            # Parsing error doesn't cause sleep or interrupt
            self.assertEqual(mock_sleep.call_count, 0)
            
            calls = mock_chat.call_args_list
            self.assertIn("ERROR: Your previous response was invalid", calls[1][0][0])

    @patch('market.agents.shark.AsyncOpencode')
    @patch('market.agents.shark.asyncio.sleep')
    async def test_get_action_max_retries_exceeded(self, mock_sleep, MockClient):
        shark = Shark("agent_0", max_retries=1)
        shark.initialize_session = AsyncMock()
        shark.session = MagicMock()
        shark.session.id = "ses_123"
        shark.interrupt = AsyncMock()
        
        with patch.object(Shark, '_chat_with_network_retry') as mock_chat:
            mock_chat.side_effect = [
                APITimeoutError("Timeout 1"),
                APITimeoutError("Timeout 2")
            ]
            
            state = MarketState(round_num=1, liquidity_b=100.0)
            from market.agents.shark import FatalAgentError
            with self.assertRaises(FatalAgentError):
                await shark.get_action(state)
            
            self.assertEqual(mock_chat.call_count, 2)
            self.assertEqual(shark.interrupt.call_count, 2)

    @patch('market.agents.shark.AsyncOpencode')
    async def test_chat_with_network_retry_propagates_timeout(self, MockClient):
        # Verify APITimeoutError is not swallowed by _chat_with_network_retry
        client_inst = AsyncMock() 
        MockClient.return_value = client_inst
        client_inst.session = AsyncMock()
        client_inst.session.chat = AsyncMock(side_effect=APITimeoutError("Request timed out"))
        
        shark = Shark("agent_0")
        shark.session = MagicMock()
        shark.session.id = "ses_123"
        
        # event.list() mock for stream
        mock_stream = AsyncMock()
        mock_stream.__aiter__.side_effect = lambda: (i for i in []) # empty stream
        client_inst.event.list = AsyncMock(return_value=mock_stream)
        
        with self.assertRaises(APITimeoutError):
            await shark._chat_with_network_retry("test prompt")

    @patch('market.agents.shark.AsyncOpencode')
    async def test_chat_with_network_retry_respects_timeout_config(self, MockClient):
        # Verify both capture_client and main_client use call-specific timeout
        base_timeout = 300.0
        call_timeout = 120.0
        client_inst = AsyncMock()
        MockClient.return_value = client_inst
        client_inst.session = AsyncMock()
        client_inst.session.chat = AsyncMock()

        shark = Shark("agent_0", timeout=base_timeout)
        shark.session = MagicMock()
        shark.session.id = "ses_123"

        from opencode_ai.types import TextPart
        dummy_part = TextPart(id="p1", messageID="m1", sessionID="s1", type="text", text='{"beliefs": {}}')
        client_inst.session.messages = AsyncMock(return_value=[MagicMock(parts=[dummy_part])])

        mock_stream = AsyncMock()
        mock_stream.__aiter__.side_effect = lambda: (i for i in [])
        client_inst.event.list = AsyncMock(return_value=mock_stream)

        await shark._chat_with_network_retry("test prompt", timeout=call_timeout)

        # Verify that session.chat was called with the overridden timeout
        # rather than the base timeout from Shark constructor
        client_inst.session.chat.assert_called()
        self.assertEqual(client_inst.session.chat.call_args.kwargs.get("timeout"), call_timeout)
    @patch('market.agents.shark.AsyncOpencode')
    @patch('market.agents.shark.asyncio.sleep')
    async def test_get_action_fatal_failure_on_short_timeout(self, mock_sleep, MockClient):
        # Verify that repeated timeouts lead to FatalAgentError
        shark = Shark("agent_0", max_retries=1, timeout=0.1)
        shark.initialize_session = AsyncMock()
        shark.session = MagicMock()
        shark.session.id = "ses_123"
        shark.interrupt = AsyncMock()
        
        # Mock _chat_with_network_retry to always timeout
        with patch.object(Shark, '_chat_with_network_retry', side_effect=APITimeoutError("Timeout")):
            state = MarketState(round_num=1, liquidity_b=100.0)
            from market.agents.shark import FatalAgentError
            with self.assertRaises(FatalAgentError):
                await shark.get_action(state)
            
            self.assertEqual(shark.interrupt.call_count, 2) # initial + 1 retry

if __name__ == "__main__":
    unittest.main()
