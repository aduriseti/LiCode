import unittest
import logging
import io
import sys
from unittest.mock import MagicMock
from market.common.cli_utils import WrappingFormatter, UnbufferedStreamHandler

class TestLogging(unittest.TestCase):
    
    def test_wrapping_formatter_indentation(self):
        """Verifies that WrappingFormatter wraps long lines and indents subsequent lines."""
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        # Use a format with 2 separators: Time - Level - Message
        formatter = WrappingFormatter(fmt='%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S', width=30)
        handler.setFormatter(formatter)
        
        logger = logging.getLogger("test_wrapping")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        # This message is longer than 30 chars
        long_message = "This is a message that should wrap nicely."
        logger.info(long_message)
        
        output = buffer.getvalue()
        lines = output.strip().split('\n')
        
        self.assertGreater(len(lines), 1, "Message should be wrapped into multiple lines")
        
        # Check header logic
        # Header format: "HH:MM:SS - INFO - " (roughly 18 chars)
        # We find the length of the header from the first line
        parts = lines[0].split(" - INFO - ")
        self.assertTrue(len(parts) > 1, "Header not found in output")
        header_part = parts[0] + " - INFO - "
        expected_indent = " " * len(header_part)
        
        # Verify subsequent lines start with the indent
        for i in range(1, len(lines)):
            self.assertTrue(lines[i].startswith(expected_indent), f"Line {i} not indented correctly: '{lines[i]}'")

    def test_wrapping_formatter_fallback(self):
        """Verifies fallback wrapping when separators are missing."""
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        # Format with NO separators
        formatter = WrappingFormatter(fmt='%(message)s', width=10)
        handler.setFormatter(formatter)
        
        logger = logging.getLogger("test_fallback")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        logger.info("LongMessageHere")
        
        output = buffer.getvalue()
        lines = output.strip().split('\n')
        self.assertGreater(len(lines), 1, "Message should be wrapped")
        # No indentation expected since no header detected
        self.assertFalse(lines[1].startswith(" "), "Fallback wrapping should not indent")

    def test_unbuffered_handler_flushes(self):
        """Verifies that UnbufferedStreamHandler calls flush() on emit."""
        mock_stream = io.StringIO()
        # Monkeypatch flush to track calls
        mock_stream.flush = MagicMock()
        
        handler = UnbufferedStreamHandler(mock_stream)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        
        record = logging.LogRecord("name", logging.INFO, "path", 1, "Test Flush", (), None)
        handler.emit(record)
        
        self.assertTrue(mock_stream.flush.called, "flush() should be called at least once")
        # mock_stream.flush.assert_called_once() # StreamHandler base might also flush

if __name__ == '__main__':
    unittest.main()