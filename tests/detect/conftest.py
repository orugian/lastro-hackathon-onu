"""Allow uv run pytest entrypoint to import workspace modules."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
