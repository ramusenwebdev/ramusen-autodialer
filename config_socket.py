import socketio

# SOCKET_URL = 'wss://www.ramusen.io/socket.io/'
SOCKET_URL = 'ws://localhost:5000/socket.io/'

sio = socketio.Client()

# Event when the connection is established
@sio.event
def connect():
    print("Socket.IO connected")

# Event when the connection is disconnected
@sio.event
def disconnect():
    print("Socket.IO disconnected")

# Event to handle messages from the server (example)
@sio.event
def message(data):
    print(f"Received message: {data}")
