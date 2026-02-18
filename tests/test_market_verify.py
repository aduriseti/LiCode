import unittest
from unittest.mock import patch, mock_open, MagicMock
import sys
import os
import py_compile

# Add scripts to path so we can import market_verify
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

import market_verify

class TestMarketVerify(unittest.TestCase):

    @patch('market_verify.os.path.exists')
    @patch('market_verify.json.load')
    @patch('market_verify.open', new_callable=mock_open, read_data='{"default": 200}')
    @patch('market_verify.py_compile.compile')
    def test_run_market_success(self, mock_compile, mock_file, mock_json_load, mock_exists):
        """Test successful validation of a file."""
        # Setup mocks
        mock_exists.return_value = True
        mock_json_load.return_value = {"default": 200}
        
        result = market_verify.run_market("dummy_script.py")
        
        self.assertIn("✅ Validated dummy_script.py", result)
        self.assertIn("Market Confidence: 85%", result)
        mock_compile.assert_called_once_with("dummy_script.py", doraise=True)

    @patch('market_verify.os.path.exists')
    @patch('market_verify.py_compile.compile')
    def test_run_market_syntax_error(self, mock_compile, mock_exists):
        """Test validation failure due to syntax error."""
        mock_exists.return_value = False # Wealth file doesn't exist, use default
        
        # Simulate PyCompileError
        # PyCompileError takes (exc_type, exc_value, file, msg) or similar depending on version
        # It expects actual Exception types for the first arg.
        mock_compile.side_effect = py_compile.PyCompileError(
            SyntaxError, SyntaxError("Invalid syntax"), "dummy_script.py"
        )
        
        result = market_verify.run_market("dummy_script.py")
        
        self.assertIn("❌ Audit Failed: Syntax error", result)

    @patch('market_verify.os.path.exists')
    @patch('market_verify.py_compile.compile')
    def test_run_market_file_not_found(self, mock_compile, mock_exists):
        """Test validation failure due to missing file."""
        mock_exists.return_value = False
        mock_compile.side_effect = FileNotFoundError("File not found")
        
        result = market_verify.run_market("non_existent.py")
        
        self.assertIn("❌ Audit Failed: File non_existent.py not found", result)

    @patch('market_verify.os.path.exists')
    @patch('market_verify.py_compile.compile')
    def test_run_market_unexpected_error(self, mock_compile, mock_exists):
        """Test validation failure due to unexpected error."""
        mock_exists.return_value = False
        mock_compile.side_effect = Exception("Something went wrong")
        
        result = market_verify.run_market("dummy_script.py")
        
        self.assertIn("❌ Audit Failed: Unexpected error", result)

    @patch('market_verify.os.path.exists')
    @patch('market_verify.json.load')
    @patch('market_verify.open', new_callable=mock_open)
    @patch('market_verify.py_compile.compile')
    def test_run_market_wealth_loading(self, mock_compile, mock_file, mock_json_load, mock_exists):
        """Test wealth loading logic (coverage mainly)."""
        # Test existing wealth file
        mock_exists.return_value = True
        mock_json_load.return_value = {"balance": 500}
        
        market_verify.run_market("dummy.py")
        
        mock_file.assert_called_with("scripts/wealth.json", "r")
        mock_json_load.assert_called()

    @patch('market_verify.os.path.exists')
    @patch('market_verify.py_compile.compile')
    def test_run_market_wealth_default(self, mock_compile, mock_exists):
        """Test default wealth when file missing."""
        mock_exists.return_value = False
        
        market_verify.run_market("dummy.py")
        
        # Since the function doesn't return the wealth, we implicitly test it doesn't crash
        # and proceeds to compile
        mock_compile.assert_called_once()

    @patch('market_verify.os.path.exists')
    @patch('market_verify.open')
    def test_run_market_wealth_error(self, mock_open, mock_exists):
        """Test error handling during wealth loading."""
        mock_exists.return_value = True
        mock_open.side_effect = PermissionError("Permission denied")
        
        result = market_verify.run_market("dummy.py")
        
        self.assertIn("Error loading wealth", result)
        self.assertIn("Permission denied", result)

if __name__ == '__main__':
    unittest.main()
