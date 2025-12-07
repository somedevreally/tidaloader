import sys
from pathlib import Path

# Fix path to allow importing backend modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from tidal_client import TidalAPIClient

tidal_client = TidalAPIClient()
