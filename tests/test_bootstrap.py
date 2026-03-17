import os
import unittest
import shutil
from pathlib import Path

class TestProjectBootstrap(unittest.TestCase):
    def test_path_population(self):
        """Verifies that importing market prepends the local bin directory to PATH."""
        # Note: market is already imported by the test runner if running via pytest
        # but we can verify the results.
        import market
        
        project_root = Path(__file__).parent.parent.resolve()
        expected_bin = str(project_root / ".opencode" / "node_modules" / ".bin")
        
        current_path = os.environ.get("PATH", "")
        self.assertTrue(current_path.startswith(expected_bin), 
                        f"Expected PATH to start with {expected_bin}, but got: {current_path}")
        
        # Verify bun is actually findable now
        bun_path = shutil.which("bun")
        self.assertIsNotNone(bun_path, "bun should be found in PATH after bootstrap")
        self.assertIn(expected_bin, bun_path, f"Expected to find project-local bun, but found: {bun_path}")

if __name__ == '__main__':
    unittest.main()
