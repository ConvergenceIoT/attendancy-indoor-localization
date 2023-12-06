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
from datetime import datetime

app = FastAPI()
eng = matlab.engine.start_matlab()
lock = threading.Lock()
distances_lock = threading.Lock()

beacon_data = {}
client_data = {}
distances = {}

# Environment Variable
MESSAGE_QUEUE_HOST_AND_PORTS = [('10.210.61.235', 61613)]
SERVER_HOST_AND_PORTS = ('127.0.0.1', 8000)


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
    global conn, HOST_AND_PORTS

    conn = stomp.Connection(host_and_ports=MESSAGE_QUEUE_HOST_AND_PORTS)
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


@app.get("/raw-backup")
async def rawBackup():
    global beacon_data, client_data

    valid_ids = range(1, 5)
    valid_beacon_ids = all(id in beacon_data for id in valid_ids)
    valid_client_ids = all(id in client_data for id in valid_ids)

    if not (valid_beacon_ids and valid_client_ids):
        return {"status": "Not all required IDs (1-4) are present in beacon_data and client_data"}

    current_date = datetime.now().strftime("%d-%H-%M-%S")

    wav_folder = Path(f'./backup/{current_date}/wav')
    wav_folder.mkdir(parents=True, exist_ok=True)
    json_folder = Path(f'./backup/{current_date}/json')
    json_folder.mkdir(parents=True, exist_ok=True)

    for data_type, data in [('client', client_data), ('beacon', beacon_data)]:
        for i in valid_ids:
            raw_audio = np.array(data[i]['raw'], dtype=np.float32)
            sample_rate = 48000

            file_name = wav_folder / f"{data_type}-{i}.wav"
            write(file_name, sample_rate, raw_audio)
            print(f"Created {file_name}")

            # Create and write the JSON file
            json_file_name = json_folder / f"{data_type}-{i}.json"
            with open(json_file_name, 'w') as json_file:
                json.dump(data[i], json_file)
            print(f"Created {json_file_name}")

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


@app.get("/run-matlab")
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

    # Ensure there is sufficient data for trilateration
    if len(beacon_positions) < 3 or len(distances) < 3:
        raise ValueError("Insufficient data for trilateration")

    # Convert all keys in distances to integers, if they are strings
    distances = {int(k): v for k, v in distances.items()}
    beacon_positions = {int(k): v for k, v in beacon_positions.items()}

    # Select first three beacons for trilateration
    # Ensure the selected beacons exist in both beacon_positions and distances
    selected_beacons = [b for b in beacon_positions if b in distances]
    if len(selected_beacons) < 3:
        raise ValueError("Insufficient matching data for trilateration")

    b1, b2, b3 = selected_beacons[:3]

    x1, y1 = beacon_positions[b1]['x'], beacon_positions[b1]['y']
    x2, y2 = beacon_positions[b2]['x'], beacon_positions[b2]['y']
    x3, y3 = beacon_positions[b3]['x'], beacon_positions[b3]['y']

    r1, r2, r3 = distances[b1], distances[b2], distances[b3]

    A = 2 * x2 - 2 * x1
    B = 2 * y2 - 2 * y1
    C = r1**2 - r2**2 - x1**2 + x2**2 - y1**2 + y2**2
    D = 2 * x3 - 2 * x2
    E = 2 * y3 - 2 * y2
    F = r2**2 - r3**2 - x2**2 + x3**2 - y2**2 + y3**2

    if (B * D - E * A) == 0:
        raise ValueError("Cannot solve the equations (division by zero)")

    x = (C * E - F * B) / (E * A - B * D)
    y = (C * D - A * F) / (B * D - A * E)

    return x, y


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
    # Create new dictionaries excluding 'raw' data
    beacon_data_without_raw = {id: {key: value for key, value in data.items() if key != 'raw'}
                               for id, data in beacon_data.items()}
    client_data_without_raw = {id: {key: value for key, value in data.items() if key != 'raw'}
                               for id, data in client_data.items()}

    return {
        "beacon_data": beacon_data_without_raw,
        "client_data": client_data_without_raw
    }


@app.get("/clear")
async def clear_data():
    global beacon_data, client_data, distances

    beacon_data = {}
    client_data = {}
    distances = {}

    return {
        "beacon_data": beacon_data,
        "client_data": client_data,
        "distances": distances
    }


if __name__ == "__main__":
    uvicorn.run(
        app, host=SERVER_HOST_AND_PORTS[0], port=SERVER_HOST_AND_PORTS[1])
