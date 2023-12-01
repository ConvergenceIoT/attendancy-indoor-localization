from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
import asyncio

app = FastAPI()

# Shared data structure
shared_data = []

# Lock for synchronization
lock = asyncio.Lock()


class AudioConfig(BaseModel):
    samplerate: int       # Recording Sample Rate
    recordLength: int     # Recording Length in seconds
    sleepTime: int        # Delay before playing chirp sound in milliseconds
    statusCode: int


@app.post("/beacon/")
async def receive_audio_config(audioConfig: AudioConfig):
    if audioConfig.statusCode == 0:
        print("Waiting mode")
    elif audioConfig.statusCode == 1:
        print("Beacon 1 and beepbeep")
    elif audioConfig.statusCode == 2:
        print("Beacon 2 and beepbeep")
    elif audioConfig.statusCode == 3:
        print("Beacon 3 and beepbeep")
    elif audioConfig.statusCode == 4:
        print("Beacon 4 and beepbeep")
    elif audioConfig.statusCode == 99:
        print("Local debug mode")
    else:
        print("Unknown status")

    return {"status": "Beacon received", "data": audioConfig}


@app.post("/client/")
async def receive_audio_config(audioConfig: AudioConfig):
    return {"status": "Client received", "data": audioConfig}

# Add more endpoints as needed
