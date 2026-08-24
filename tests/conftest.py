"""Keep the local W1 command package importable without changing core packaging."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
