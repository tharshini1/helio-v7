import os

import uvicorn


if __name__ == "__main__":
    # Local development entrypoint. On Render the Dockerfile starts uvicorn.
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8001")),
        reload=True,
    )
