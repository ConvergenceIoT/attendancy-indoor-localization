from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
import asyncio
import matlab.engine

app = FastAPI()
eng = matlab.engine.start_matlab()

# Shared data structure
shared_data = []

# Lock for synchronization
lock = asyncio.Lock()

# STOMP for client and android


# Handling requests to manage client and android
class AudioConfig(BaseModel):
    samplerate: int       # Recording Sample Rate
    recordLength: int     # Recording Length in seconds
    sleepTime: int        # Delay before playing chirp sound in milliseconds
    statusCode: int


@app.post("/beacon/")
async def beacon(audioConfig: AudioConfig):
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
async def client(audioConfig: AudioConfig):
    return {"status": "Client received", "data": audioConfig}


@app.get("/run-engine")
async def runEngine():
    eng.run('simple_beepbeep_tutorial_solution.m', nargout=0)

    return {"status": "Engine Run!", "data": "yeah"}

# Add more endpoints as needed
