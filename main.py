from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
import asyncio

app = FastAPI()

# Shared data structure
shared_data = []

# Lock for synchronization
lock = asyncio.Lock()


class Item(BaseModel):
    item: Any


@app.post("/add-data/")
async def add_data(item: Item):
    async with lock:  # Acquire lock before modifying the shared_data
        shared_data.append(item)
    return {"status": "Data added"}


@app.get("/get-data/")
async def get_data():
    return shared_data

# Add more endpoints as needed
