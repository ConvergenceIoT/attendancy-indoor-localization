import json
import threading
import stomp
from fastapi import FastAPI
from pydantic import BaseModel
import matlab.engine
import uvicorn
from scipy.io.wavfile import write
import numpy as np
from pathlib import Path

app = FastAPI()
eng = matlab.engine.start_matlab()
lock = threading.Lock()
distances_lock = threading.Lock()

beacon_data = {}
client_data = {}
distances = {}


class AudioConfig(BaseModel):
    samplerate: int
    recordLength: int
    sleepTime: int
    statusCode: int


class StompListener(stomp.ConnectionListener):
    def on_error(self, frame):
        print('Received an error:', frame.body)

    def on_message(self, frame):
        lock.acquire()
        try:
            message_data = json.loads(frame.body)
            destination = frame.headers['destination']

            if destination.startswith('/topic//data/beacon/'):
                beacon_number = destination.split('/')[-1]
                try:
                    beacon_number = int(beacon_number)
                    beacon_data[beacon_number] = message_data
                    print(
                        f"Data added to beacon_data[{beacon_number}]")
                except ValueError:
                    print("Invalid beacon number in destination:", destination)

            elif destination == '/topic//data/client':
                client_id = message_data.get('id')
                if client_id is not None:
                    client_data[client_id] = message_data
                    print(
                        f"Data added to client_data[{client_id}]")
                else:
                    print("Message does not contain an 'id' field")
        except Exception as e:
            print("An error occurred:", e)
        finally:
            lock.release()


def run_stomp():
    global conn
    host_and_ports = [('192.168.0.2', 61613)]

    conn = stomp.Connection(host_and_ports=host_and_ports)
    conn.set_listener('', StompListener())
    conn.connect(wait=True)
    conn.subscribe(destination='/topic//data/client', id=1, ack='auto')
    conn.subscribe(destination='/topic//data/beacon/1', id=1, ack='auto')
    conn.subscribe(destination='/topic//data/beacon/2', id=1, ack='auto')
    conn.subscribe(destination='/topic//data/beacon/3', id=1, ack='auto')
    conn.subscribe(destination='/topic//data/beacon/4', id=1, ack='auto')
    print("STOMP Connection established")


stomp_thread = threading.Thread(target=run_stomp)
stomp_thread.start()


@app.post("/command/both")
async def commandToBeaconAndClient(audioConfig: AudioConfig):
    json_data = audioConfig.json()
    destinations = ['/topic//command/beacon/1', '/topic//command/beacon/2',
                    '/topic//command/beacon/3', '/topic//command/beacon/4']
    if 1 <= audioConfig.statusCode <= 4:
        conn.send(body=json_data,
                  destination=destinations[audioConfig.statusCode - 1])
    else:
        for dest in destinations:
            conn.send(body=json_data, destination=dest)

    conn.send(body=json_data, destination='/topic//command/client')

    return {"status": "both(beacon, client) published!", "data": audioConfig}


@app.post("/command/beacon")
async def commandToBeacon(audioConfig: AudioConfig):
    json_data = audioConfig.json()
    destinations = ['/topic//command/beacon/1', '/topic//command/beacon/2',
                    '/topic//command/beacon/3', '/topic//command/beacon/4']
    if 1 <= audioConfig.statusCode <= 4:
        conn.send(body=json_data,
                  destination=destinations[audioConfig.statusCode - 1])
    else:
        for dest in destinations:
            conn.send(body=json_data, destination=dest)

    return {"status": "beacon published!", "data": audioConfig}


@app.post("/command/client")
async def commandToClient(audioConfig: AudioConfig):
    json_data = audioConfig.json()
    conn.send(body=json_data, destination='/topic//command/client')

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

    valid_ids = range(1, 5)
    valid_beacon_ids = all(id in beacon_data for id in valid_ids)
    valid_client_ids = all(id in client_data for id in valid_ids)

    if not (valid_beacon_ids and valid_client_ids):
        return {"status": "Not all required IDs (1-4) are present in beacon_data and client_data"}

    wav_folder = Path('./wav')
    wav_folder.mkdir(exist_ok=True)

    for data_type, data in [('client', client_data), ('beacon', beacon_data)]:
        for i in valid_ids:
            raw_audio = np.array(data[i]['raw'], dtype=np.float32)
            sample_rate = 48000

            file_name = wav_folder / f"{data_type}-{i}.wav"
            write(file_name, sample_rate, raw_audio)
            print(f"Created {file_name}")

    return {"status": "Conversion complete"}


@app.get("/add-dummy")
async def addDummy():
    global beacon_data, client_data

    dummy_folder = Path('./dummy')

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


@app.post("/run-matlab")
async def calculate_distances():
    # Acquire lock to safely access and modify the distances dictionary
    distances_lock.acquire()
    try:
        # Assuming beacon_data and client_data are already populated
        for beacon_id in beacon_data:
            if beacon_id in client_data:
                # Extract speaker-to-microphone distances
                clientSTMDistance = client_data[beacon_id]['micLength']
                beaconSTMDistance = beacon_data[beacon_id]['micLength']

                # Call MATLAB function
                distance = eng.beepbeepdistance(
                    beacon_id, clientSTMDistance, beaconSTMDistance, nargout=1)

                # Update distances dictionary
                distances[beacon_id] = distance

        # Release lock after updating
        distances_lock.release()
        return {"status": "success", "distances": distances}
    except Exception as e:
        # Ensure the lock is released even if an exception occurs
        distances_lock.release()
        return {"status": "error", "message": str(e)}


def trilateration(beacon_positions):
    global distances

    """
    Calculate the user's position based on trilateration.
    :param beacon_positions: Dictionary of beacon positions (x, y coordinates).
    :param distances: Dictionary of distances from beacons.
    :return: (x, y) coordinates of the user.
    """
    # Trilateration algorithm implementation
    # For simplicity, this example assumes at least three beacons.
    # You can extend this to handle more complex scenarios.
    try:
        distances_lock.acquire()

        if len(beacon_positions) < 3 or len(distances) < 3:
            raise ValueError("Insufficient data for trilateration")

        print(1)

        # TODO: 이 부분 수정!!
        beacons = list(beacon_positions.keys())
        print(beacons)
        A = 2 * (beacon_positions[beacons[1]]['x'] -
                 beacon_positions[beacons[0]]['x'])
        B = 2 * (beacon_positions[beacons[1]]['y'] -
                 beacon_positions[beacons[0]]['y'])
        C = distances[beacons[0]]**2 - distances[beacons[1]]**2 \
            - beacon_positions[beacons[0]]['x']**2 + beacon_positions[beacons[1]]['x']**2 \
            - beacon_positions[beacons[0]]['y']**2 + \
            beacon_positions[beacons[1]]['y']**2
        D = 2 * (beacon_positions[beacons[2]]['x'] -
                 beacon_positions[beacons[1]]['x'])
        E = 2 * (beacon_positions[beacons[2]]['y'] -
                 beacon_positions[beacons[1]]['y'])
        F = distances[beacons[1]]**2 - distances[beacons[2]]**2 \
            - beacon_positions[beacons[1]]['x']**2 + beacon_positions[beacons[2]]['x']**2 \
            - beacon_positions[beacons[1]]['y']**2 + \
            beacon_positions[beacons[2]]['y']**2

        print(2)

        if ((E * A) - (B * D)) == 0 or ((B * D) - (A * E)) == 0:
            print("Zero Divison!")
            raise ValueError("Zero Division")

        x = ((C * E) - (F * B)) / ((E * A) - (B * D))
        y = ((C * D) - (A * F)) / ((B * D) - (A * E))
        return x, y
    finally:
        distances_lock.release()


@app.get("/trilateration")
async def perform_trilateration():
    # Extract beacon positions from beacon_data
    beacon_positions = {str(beacon_id): beacon_data[beacon_id]['position']
                        for beacon_id in beacon_data}
    try:
        print("Beacon Positions:", beacon_positions)

        x, y = trilateration(beacon_positions)
        return {"status": "success", "x": x, "y": y}
    except Exception as e:
        print("Error in trilateration:", e)  # Debug: Print the error
        return {"status": "error", "message": str(e)}


@app.get("/check")
async def check_data():
    beacon_data_ids = list(beacon_data.keys())
    client_data_ids = list(client_data.keys())

    return {
        "beacon_data_ids": beacon_data_ids,
        "client_data_ids": client_data_ids
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
