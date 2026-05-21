"""PPE Polling System - FastAPI Backend."""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import poll, registration, certification, response, results
from app.api.websocket import manager
from app.services import P2PManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

p2p = P2PManager()


@asynccontextmanager
async def lifespan(_application: FastAPI):
    """Application lifespan context manager."""
    logger.info("PPE Polling System starting up...")
    yield
    logger.info("PPE Polling System shutting down...")


app = FastAPI(
    title="PPE Polling System",
    description="Public Verification of Private Effort Polling Framework",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "PPE Polling System API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


app.include_router(poll.router, prefix="/api/poll", tags=["Protocol 1: Announcement"])
app.include_router(registration.router, prefix="/api/poll", tags=["Protocol 2: Registration"])
app.include_router(certification.router, prefix="/api/poll", tags=["Protocol 3: Certification"])
app.include_router(response.router, prefix="/api/poll", tags=["Protocol 4: Response"])
app.include_router(results.router, prefix="/api/poll", tags=["Protocol 5: Results"])


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    node_id: str,
    role: str
):
    """
    Blind signaling endpoint. The server never inspects PPE challenge content;
    all PPE messages are relayed directly between peers.
    """
    await manager.connect(websocket, session_id, node_id, role)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")
            msg_data = message.get("data", {})

            logger.debug(f"WebSocket message from {node_id}: {msg_type}")

            reply = await p2p.handle_message(msg_type, session_id, node_id, msg_data)
            if reply:
                await websocket.send_json(reply)

    except WebSocketDisconnect:
        manager.disconnect(session_id, node_id, websocket)
        logger.info(f"WebSocket disconnected: {node_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {node_id}: {e}")
        manager.disconnect(session_id, node_id, websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
