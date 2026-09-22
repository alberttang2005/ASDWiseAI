"""Vercel Python entrypoint. The deployment packager supplies backend/."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from web.serverless import create_serverless_app
app = create_serverless_app()
