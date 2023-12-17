from fastapi import Path
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
import time
from datetime import datetime
from scipy.optimize import minimize

app = FastAPI()
eng = matlab.engine.start_matlab()
lock = threading.Lock()
distances_lock = threading.Lock()

beacon_data = {}
client_data = {}
distances = {}

# Environment Variable
MESSAGE_QUEUE_HOST_AND_PORTS = [('10.210.60.11', 61613)]
SERVER_HOST_AND_PORTS = ('127.0.0.1', 8000)
BEACON_COUNT = 5
BEACON_PRESET = {
    1: {"x": 360, "y": 0},
    2: {"x": 0, "y": 363},
    3: {"x": 360, "y": 363},
    4: {"x": 700, "y": 363},
    5: {"x": 360, "y": 802}
}


class AudioConfig(BaseModel):
    samplerate: int
    recordLength: int
    sleepTime: int
    statusCode: int


class TestConfig(BaseModel):
    sleepTime: int


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
                    if 'id' in message_data:
                        beacon_id = int(message_data['id'])
                        if beacon_id in BEACON_PRESET:
                            # Use statusCode to find the location from BEACON_PRESET
                            beacon_location = BEACON_PRESET[int(beacon_id)]
                            # Update the position in message_data
                            message_data['position'] = beacon_location
                        else:
                            print(f"Unknown beacon statusCode: {beacon_id}")
                    beacon_data[beacon_number] = message_data
                    print(f"Data added to beacon_data[{beacon_number}]")
                except ValueError:
                    print("Invalid beacon number in destination:", destination)

            elif destination == '/topic//data/client':
                client_id = message_data.get('id')
                if client_id is not None:
                    client_data[client_id] = message_data
                    print(f"Data added to client_data[{client_id}]")
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
    conn.subscribe(destination='/topic//data/beacon/5', id=1, ack='auto')
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


@app.post("/command/all")
async def commandToAll(testConfig: TestConfig):
    command_folder = Path('./command/experiment')
    destinations = ['/topic//command/beacon/1', '/topic//command/beacon/2',
                    '/topic//command/beacon/3', '/topic//command/beacon/4',
                    '/topic//command/beacon/5',
                    '/topic//command/client']

    # Assuming there are equal numbers of beacon and client files
    for i in range(1, BEACON_COUNT + 1):  # Adjust range as necessary
        beacon_file_path = command_folder / f'beacon-{i}.json'
        client_file_path = command_folder / f'client-{i}.json'

        if beacon_file_path.exists():
            with open(beacon_file_path, 'r') as file:
                json_data = file.read()
                conn.send(body=json_data,
                          destination=f'/topic//command/beacon/{i}')

        if client_file_path.exists():
            with open(client_file_path, 'r') as file:
                json_data = file.read()
                conn.send(body=json_data,
                          destination=f'/topic//command/client')

        time.sleep(testConfig.sleepTime)
        print(
            f"Commands for beacon-{i} and client-{i} sent. Sleeping for {testConfig.sleepTime} seconds.")

    return {"status": "Commands sent to all devices"}


@app.post("/command/all/{id}")
async def commandToSpecific(id: int):
    command_folder = Path('./command/experiment')

    beacon_file_path = command_folder / f'beacon-{id}.json'
    client_file_path = command_folder / f'client-{id}.json'

    # Send command to the specific beacon
    if beacon_file_path.exists():
        with open(beacon_file_path, 'r') as file:
            json_data = file.read()
            conn.send(body=json_data,
                      destination=f'/topic//command/beacon/{id}')
            print(f"Command sent to beacon-{id}")

    # Send command to the specific client
    if client_file_path.exists():
        with open(client_file_path, 'r') as file:
            json_data = file.read()
            conn.send(body=json_data, destination=f'/topic//command/client')
            print(f"Command sent to client-{id}")

    return {"status": f"Commands sent to beacon-{id} and client-{id}"}


@app.post("/command/beacon")
async def commandToBeacon(audioConfig: AudioConfig):
    json_data = audioConfig.json()
    destinations = ['/topic//command/beacon/1', '/topic//command/beacon/2',
                    '/topic//command/beacon/3', '/topic//command/beacon/4', '/topic//command/beacon/5']
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

    valid_ids = range(1, BEACON_COUNT + 1)
    valid_beacon_ids = all(id in beacon_data for id in valid_ids)
    valid_client_ids = all(id in client_data for id in valid_ids)

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

    valid_ids = range(1, BEACON_COUNT + 1)
    valid_beacon_ids = all(id in beacon_data for id in valid_ids)
    valid_client_ids = all(id in client_data for id in valid_ids)

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
    anomaly_count = 0

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

                if distance <= -100 or abs(distance) >= 2000:
                    anomaly_count += 1

        # Release lock after updating
        distances_lock.release()

        if anomaly_count >= 2:
            return {"status": "outside (anomaly >= 2)", "distances": distances}
        else:
            return {"status": "success", "distances": distances}
    except Exception as e:
        # Ensure the lock is released even if an exception occurs
        distances_lock.release()
        return {"status": "Outside!", "message": str(e)}


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

    b1, b2, b3 = list(beacon_positions.keys())[:3]

    x1, y1 = beacon_positions[selected_beacons[0]
                              ]['x'], beacon_positions[selected_beacons[0]]['y']
    x2, y2 = beacon_positions[selected_beacons[1]
                              ]['x'], beacon_positions[selected_beacons[1]]['y']
    x3, y3 = beacon_positions[selected_beacons[2]
                              ]['x'], beacon_positions[selected_beacons[2]]['y']

    r1, r2, r3 = distances[selected_beacons[0]
                           ], distances[selected_beacons[1]], distances[selected_beacons[2]]

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


# @app.get("/trilateration")
# async def perform_trilateration():
#     # Extract beacon positions from beacon_data
#     beacon_positions = {str(beacon_id): beacon_data[beacon_id]['position']
#                         for beacon_id in beacon_data}
#     try:
#         print("Beacon Positions:", beacon_positions)

#         x, y = trilateration(beacon_positions)
#         return {"status": "success", "x": x, "y": y}
#     except Exception as e:
#         print("Error in trilateration:", e)  # Debug: Print the error
#         return {"status": "error", "message": str(e)}

@app.get("/trilateration")
async def perform_trilateration():
    # Extract beacon positions from beacon_data
    beacon_positions = {str(beacon_id): beacon_data[beacon_id]['position']
                        for beacon_id in beacon_data}

    beacon_positions_int_keys = {
        int(k): v for k, v in beacon_positions.items()}

    try:
        # Sort beacons by their distances (ensure distances and beacon_positions use the same type of keys)
        sorted_beacons = sorted(distances.keys(), key=lambda b: distances[b])

        # Select the first three beacons
        selected_beacons = sorted_beacons[:3]

        # Prepare the positions of the selected beacons for trilateration
        selected_beacon_positions = {
            b: beacon_positions_int_keys[b] for b in selected_beacons if b in beacon_positions_int_keys}

        # Ensure we have positions for all selected beacons
        if len(selected_beacon_positions) < 3:
            raise ValueError(
                "Insufficient beacon position data for selected beacons")

        x, y = trilateration(selected_beacon_positions)
        return {"status": "success", "x": x, "y": y}
    except Exception as e:
        print("Error in trilateration:", e)  # Debug: Print the error
        return {"status": "error", "message": str(e)}


def quadrilateration(beacon_positions, distances):
    if len(beacon_positions) < 4 or len(distances) < 4:
        raise ValueError("Insufficient data for quadrilateration")

    # Select the first four beacons available
    selected_beacons = list(beacon_positions.keys())[:4]

    # Objective function to minimize
    def objective_function(point):
        x, y = point
        return sum((np.sqrt((x - beacon_positions[b]['x'])**2 + (y - beacon_positions[b]['y'])**2) - distances[b])**2 for b in selected_beacons)

    # Initial guess - can be improved based on specific use case
    initial_guess = [0, 0]

    # Perform minimization
    result = minimize(objective_function, initial_guess)

    if result.success:
        return result.x[0], result.x[1]
    else:
        raise ValueError("Quadrilateration failed to converge")


# @app.get("/quadrilateration")
# async def perform_quadrilateration():
#     # Extract beacon positions from beacon_data
#     beacon_positions = {str(beacon_id): beacon_data[beacon_id]['position']
#                         for beacon_id in beacon_data}
#     try:
#         x, y = quadrilateration(beacon_positions, distances)
#         return {"status": "success", "x": x, "y": y}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}

@app.get("/quadrilateration")
async def perform_quadrilateration():
    # Extract beacon positions from beacon_data
    beacon_positions = {str(beacon_id): beacon_data[beacon_id]['position']
                        for beacon_id in beacon_data}
    # Convert beacon_positions keys to integers for consistency
    beacon_positions_int_keys = {
        int(k): v for k, v in beacon_positions.items()}

    try:
        # Sort beacons by their distances (ensure distances and beacon_positions use the same type of keys)
        sorted_beacons = sorted(distances.keys(), key=lambda b: distances[b])

        # Select the first four beacons
        selected_beacons = sorted_beacons[:4]

        # Prepare the positions of the selected beacons for quadrilateration
        selected_beacon_positions = {
            b: beacon_positions_int_keys[b] for b in selected_beacons if b in beacon_positions_int_keys}

        # Ensure we have positions for all selected beacons
        if len(selected_beacon_positions) < 4:
            raise ValueError(
                "Insufficient beacon position data for selected beacons")

        x, y = quadrilateration(selected_beacon_positions, distances)
        return {"status": "success", "x": x, "y": y}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/check")
async def check_data():

    return {
        "beacon_data": beacon_data,
        "client_data": client_data,
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


class Location(BaseModel):
    x: float
    y: float


table_coordinates = {
    0: (75, 0),
    1: (75, 128),
    2: (75, 246),
    3: (75, 363),
    4: (75, 473),
    5: (75, 583),
    6: (360, 0),
    7: (360, 128),
    8: (360, 246),
    9: (360, 363),
    10: (360, 473),
    11: (360, 583),
    12: (360, 691),
    13: (360, 802),
    14: (625, 0),
    15: (625, 128),
    16: (625, 246),
    17: (625, 363),
    18: (625, 473),
    19: (625, 583),
    20: (625, 691),
    21: (625, 802)
}


@app.post("/locate")
async def locate(position: Location):
    closest_table = None
    min_distance = float('inf')

    for table_number, (x, y) in table_coordinates.items():
        distance = ((position.x - x) ** 2 + (position.y - y) ** 2) ** 0.5
        if distance < min_distance:
            min_distance = distance
            closest_table = table_number

    return {"answer": closest_table}


if __name__ == "__main__":
    uvicorn.run(
        app, host=SERVER_HOST_AND_PORTS[0], port=SERVER_HOST_AND_PORTS[1])
