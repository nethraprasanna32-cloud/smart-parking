import os


# Load .env before any service reads os.environ; variables set in the shell win.
if os.getenv("LOAD_DOTENV", "1") != "0":
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))
