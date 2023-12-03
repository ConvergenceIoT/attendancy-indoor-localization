import json
import threading
import stomp
import threading
from fastapi import FastAPI
from pydantic import BaseModel
import matlab.engine
import uvicorn
from scipy.io.wavfile import write
import numpy as np
from pathlib import Path
import json

app = FastAPI()
eng = matlab.engine.start_matlab()
lock = threading.Lock()

beacon_data = {}
client_data = {}


class AudioConfig(BaseModel):
    samplerate: int
    recordLength: int
    sleepTime: int
    statusCode: int


class StompListener(stomp.ConnectionListener):
    global beacon_data, client_data

    def on_error(self, frame):
        print('Received an error:', frame.body)

    def on_message(self, frame):
        print('Received a message:', frame.body)
        lock.acquire()
        try:
            message_data = json.loads(frame.body)
            destination = frame.headers['destination']

            if destination.startswith('/command/beacon/'):
                # Extract beacon number from the destination
                beacon_number = destination.split('/')[-1]
                try:
                    # Convert beacon number to an integer
                    beacon_number = int(beacon_number)
                    # Add message to beacon_data
                    beacon_data[beacon_number] = message_data
                    print(
                        f"Data added to beacon_data[{beacon_number}]:", message_data)
                except ValueError:
                    print("Invalid beacon number in destination:", destination)

            elif destination == '/command/client':
                if client_data is None:
                    client_data = {}

                client_id = message_data.get('id')
                if client_id is not None:
                    client_data[client_id] = message_data
                    print(
                        f"Data added to client_data[{client_id}]:", message_data)
                else:
                    print("Message does not contain an 'id' field")
        except Exception as e:
            print("An error occurred:", e)
        finally:
            lock.release()


def run_stomp():
    global conn
    # Specify the IP address and port of your ActiveMQ broker
    # 61613 is the default port for STOMP
    host_and_ports = [('10.210.60.168', 61613)]

    conn = stomp.Connection(host_and_ports=host_and_ports)
    conn.set_listener('', StompListener())
    conn.connect(wait=True)
    conn.subscribe(destination='/data/client', id=1, ack='auto')
    conn.subscribe(destination='/data/beacon/1', id=1, ack='auto')
    conn.subscribe(destination='/data/beacon/2', id=1, ack='auto')
    conn.subscribe(destination='/data/beacon/3', id=1, ack='auto')
    conn.subscribe(destination='/data/beacon/4', id=1, ack='auto')
    print("STOMP Connection established")


stomp_thread = threading.Thread(target=run_stomp)
stomp_thread.start()


@app.post("/command/both")
async def commandToBeaconAndClient(audioConfig: AudioConfig):
    json_data = audioConfig.json()
    if audioConfig.statusCode == 1:
        conn.send(body=json_data, destination='/command/beacon/1')
    elif audioConfig.statusCode == 2:
        conn.send(body=json_data, destination='/command/beacon/2')
    elif audioConfig.statusCode == 3:
        conn.send(body=json_data, destination='/command/beacon/3')
    elif audioConfig.statusCode == 4:
        conn.send(body=json_data, destination='/command/beacon/4')
    else:
        # ready mode
        conn.send(body=json_data, destination='/command/beacon/1')
        conn.send(body=json_data, destination='/command/beacon/2')
        conn.send(body=json_data, destination='/command/beacon/3')
        conn.send(body=json_data, destination='/command/beacon/4')

    conn.send(body=json_data, destination='/command/client')

    return {"status": "both(beacon, client) published!", "data": audioConfig}


@app.post("/command/beacon")
async def commandToBeacon(audioConfig: AudioConfig):
    json_data = audioConfig.json()
    if audioConfig.statusCode == 1:
        conn.send(body=json_data, destination='/command/beacon/1')
    elif audioConfig.statusCode == 2:
        conn.send(body=json_data, destination='/command/beacon/2')
    elif audioConfig.statusCode == 3:
        conn.send(body=json_data, destination='/command/beacon/3')
    elif audioConfig.statusCode == 4:
        conn.send(body=json_data, destination='/command/beacon/4')
    else:
        # ready mode
        conn.send(body=json_data, destination='/command/beacon/1')
        conn.send(body=json_data, destination='/command/beacon/2')
        conn.send(body=json_data, destination='/command/beacon/3')
        conn.send(body=json_data, destination='/command/beacon/4')

    return {"status": "beacon published!", "data": audioConfig}


@app.post("/command/client")
async def commandToClient(audioConfig: AudioConfig):
    json_data = audioConfig.json()
    conn.send(body=json_data, destination='/command/client')

    return {"status": "client published!", "data": audioConfig}


@app.get("/refresh")
async def refresh():
    global beacon_data, client_data
    beacon_data = {}
    client_data = {}

    return {"status": "refreshed!"}


@app.get("/raw-to-wav")
async def rawToWav():
    global beacon_data, client_data

    # Check if both dictionaries have entries with IDs 1 to 4
    valid_ids = range(1, 5)
    valid_beacon_ids = all(id in beacon_data for id in valid_ids)
    valid_client_ids = all(id in client_data for id in valid_ids)

    if not (valid_beacon_ids and valid_client_ids):
        return {"status": "Not all required IDs (1-4) are present in beacon_data and client_data"}

    wav_folder = Path('./wav')
    wav_folder.mkdir(exist_ok=True)  # Create the folder if it doesn't exist

    for data_type, data in [('client', client_data), ('beacon', beacon_data)]:
        for i in valid_ids:  # IDs 1 to 4
            raw_audio = np.array(data[i]['raw'], dtype=np.float32)
            sample_rate = 48000  # Replace with actual sample rate

            file_name = wav_folder / f"{data_type}-{i}.wav"
            write(file_name, sample_rate, raw_audio)
            print(f"Created {file_name}")

    return {"status": "Conversion complete"}


@app.get("/add-dummy")
async def addDummy():
    global beacon_data, client_data

    dummy_folder = Path('./dummy')  # Path to the dummy folder

    # Iterate over the dummy data files and add their contents to the appropriate dictionary
    for file_path in dummy_folder.glob('*.json'):
        with open(file_path, 'r') as file:
            data = json.load(file)
            if 'beacon' in file_path.stem:
                beacon_id = int(file_path.stem.split('-')[1])
                beacon_data[beacon_id] = data
            elif 'client' in file_path.stem:
                client_id = int(file_path.stem.split('-')[1])
                client_data[client_id] = data

    return {"status": "Dummy data added successfully"}


@app.get("/run-matlab")
async def runMatlab(audioConfig: AudioConfig):
    json_data = audioConfig.json()
    conn.send(body=json_data, destination='/command/client')

    return {"status": "client published!", "data": audioConfig}


@app.get("/run-engine")
async def runEngine():
    eng.run('simple_beepbeep_tutorial_solution.m', nargout=0)
    return {"status": "Engine Run!", "data": "yeah"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
