import logging


def setup_logging():
    """
    Configure application and Uvicorn loggers with a unified format.
    """

    log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    formatter = logging.Formatter(log_format, datefmt=date_format)

    # Configure root logger (your logs)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Add handler to root logger
    root_handler = logging.StreamHandler()
    root_handler.setFormatter(formatter)
    root_logger.handlers = [root_handler]

    # --- Patch Uvicorn loggers ---

    # Uvicorn error log (startup/shutdown, stacktraces)
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.handlers = [root_handler]
    uvicorn_error.setLevel(logging.INFO)

    # Uvicorn access log (requests)
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = [root_handler]
    uvicorn_access.setLevel(logging.INFO)

    # Avoid double logs
    # Important for clean output
    uvicorn_error.propagate = False
    uvicorn_access.propagate = False
