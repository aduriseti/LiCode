import unittest
from unittest.mock import patch, MagicMock
import os
import subprocess
from licode.verifier import Verifier

class TestVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = Verifier("/path/to/test.py", timeout_sec=1)
        self.worktree = "/path/to/worktree"

    @patch("os.path.exists")
    @patch("os.path.abspath")
    @patch("subprocess.run")
    def test_execute_success(self, mock_run, mock_abspath, mock_exists):
        mock_exists.return_value = True
        mock_abspath.return_value = "/abs/path/to/test.py"
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        result = self.verifier.execute(self.worktree)
        self.assertTrue(result)
        
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(kwargs["cwd"], self.worktree)

    @patch("os.path.exists")
    @patch("os.path.abspath")
    @patch("subprocess.run")
    def test_execute_failure(self, mock_run, mock_abspath, mock_exists):
        mock_exists.return_value = True
        mock_abspath.return_value = "/abs/path/to/test.py"
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error"
        mock_run.return_value = mock_result
        
        result = self.verifier.execute(self.worktree)
        self.assertFalse(result)

    @patch("os.path.exists")
    @patch("os.path.abspath")
    @patch("subprocess.run")
    def test_execute_timeout(self, mock_run, mock_abspath, mock_exists):
        mock_exists.return_value = True
        mock_abspath.return_value = "/abs/path/to/test.py"
        
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="cmd", timeout=1)
        
        result = self.verifier.execute(self.worktree)
        self.assertIsNone(result)

    @patch("os.path.exists")
    def test_execute_missing_worktree(self, mock_exists):
        mock_exists.return_value = False
        result = self.verifier.execute(self.worktree)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
