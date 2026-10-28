import os
import sys
import tempfile
from pathlib import Path

# Keep tests away from the real configuration and sockets.
_tmp = Path(tempfile.mkdtemp(prefix="hyprwink-test-"))
os.environ["XDG_CONFIG_HOME"] = str(_tmp / "config")
os.environ["XDG_DATA_HOME"] = str(_tmp / "data")
os.environ["XDG_RUNTIME_DIR"] = str(_tmp / "run")
os.environ["LANGUAGE"] = "en"      # texts as in the code
sys.path.insert(0, str(Path(__file__).parent))
# Test the working copy, not the installed package.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
