import warnings
import logging
from watchfiles import DefaultFilter

def log_check(message: str = "Loges initialized.", level: str = "DEBUG"):
    """Set up logging configuration with reduced noise from libraries."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.info(message)
        # Suppress all DeprecationWarnings (including LangChain)
    # warnings.filterwarnings("ignore", category=DeprecationWarning)
    # warnings.filterwarnings("ignore", category=UserWarning)
    # warnings.filterwarnings("ignore", category=FutureWarning)

    # # Reduce FastAPI and Uvicorn log noise
    # logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
    # logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # logging.getLogger("watchfiles").setLevel(logging.CRITICAL)
    # logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    # logging.getLogger("langchain").setLevel(logging.ERROR)

