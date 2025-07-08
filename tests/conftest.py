import sys
import os

# Ensure src/ is in sys.path for all tests, so 'trace_generator' is importable
SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src"))
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)
