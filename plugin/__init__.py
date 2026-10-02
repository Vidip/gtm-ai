"""Load .env (if present) before any submodule reads os.environ at import time."""
from dotenv import load_dotenv

load_dotenv()
