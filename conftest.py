# conftest.py — pytest root configuration
# Adds src/ to sys.path so that 'import abyss' works without installing the package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
