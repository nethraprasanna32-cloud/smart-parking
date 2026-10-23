"""FastAPI backend package."""
import os


# Settings from .env in the project root (alerts, passwords, ...). Loaded here,
# before any service reads os.environ. Variables already set in the shell win.
if os.getenv("LOAD_DOTENV", "1") != "0":
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))
