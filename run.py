"""Entry point of the web app: uvicorn run:app"""

from app.config import get_settings
from app.logging_setup import setup_logging

setup_logging(get_settings().target_server)

from app.app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("run:app", host="127.0.0.1", port=5151, reload=True)
