# app.py
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from engineio.payload import Payload
import numpy as np
import pyaudio
import threading
import json
from datetime import datetime
import base64
import eventlet
from flask_socketio import ConnectionRefusedError

eventlet.monkey_patch()
Payload.max_decode_packets = 100

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, ping_timeout=10, async_mode='eventlet', cors_allowed_origins='*')

class AudioStreamManager:
    def __init__(self):
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paFloat32
        self.CHANNELS = 1
        self.RATE = 44100
        self.active_streams = {}
        self.data_lock = threading.Lock()

        # Initialize PyAudio for server-side processing
        try:
            self.p = pyaudio.PyAudio()
        except Exception as e:
            print(f"Error initializing PyAudio: {e}")
            raise

    def add_stream(self, client_id):
        """Add a new client stream"""
        with self.data_lock:
            try:
                self.active_streams[client_id] = {
                    'data': np.zeros(self.CHUNK, dtype=np.float32),
                    'last_update': datetime.now(),
                    'latency': 0
                }
                print(f"Added new stream for client: {client_id}")
            except Exception as e:
                print(f"Error adding stream for client {client_id}: {e}")
    
    def remove_stream(self, client_id):
        """Remove a client stream"""
        with self.data_lock:
            try:
                if client_id in self.active_streams:
                    del self.active_streams[client_id]
                    print(f"Removed stream for client: {client_id}")
            except Exception as e:
                print(f"Error removing stream for client {client_id}: {e}")
    
    def update_stream_data(self, client_id, audio_data, timestamp):
        """Update stream data for a client"""
        with self.data_lock:
            try:
                if client_id in self.active_streams:
                    self.active_streams[client_id]['data'] = audio_data
                    self.active_streams[client_id]['last_update'] = datetime.now()
                    self.active_streams[client_id]['latency'] = \
                        (datetime.now().timestamp() - timestamp) * 1000
            except Exception as e:
                print(f"Error updating stream data for client {client_id}: {e}")

    def get_streams_data(self):
        """Get current state of all streams"""
        with self.data_lock:
            try:
                return {
                    client_id: {
                        'data': stream['data'].tolist(),
                        'latency': stream['latency']
                    }
                    for client_id, stream in self.active_streams.items()
                }
            except Exception as e:
                print(f"Error getting streams data: {e}")
                return {}

    def cleanup(self):
        """Cleanup PyAudio resources"""
        if hasattr(self, 'p'):
            self.p.terminate()

# Initialize the audio manager
audio_manager = AudioStreamManager()

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

def get_client_id():
    """Helper function to get client ID from current socket context"""
    from flask_socketio import rooms
    return rooms()[0] if rooms() else None

@socketio.on('connect')
def handle_connect():
    """Handle new client connections"""
    try:
        client_id = get_client_id()
        audio_manager.add_stream(client_id)
        print(f"Client connected: {client_id}")
    except Exception as e:
        print(f"Error in handle_connect: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnections"""
    try:
        client_id = get_client_id()
        audio_manager.remove_stream(client_id)
        print(f"Client disconnected: {client_id}")
    except Exception as e:
        print(f"Error in handle_disconnect: {e}")

@socketio.on('audio_data')
def handle_audio_data(data):
    """Handle incoming audio data from clients"""
    try:
        client_id = get_client_id()
        if not client_id:
            print("No client ID found")
            return

        audio_data = np.frombuffer(
            base64.b64decode(data['audio_data']),
            dtype=np.float32
        )
        timestamp = data['timestamp']
        
        if len(audio_data) == audio_manager.CHUNK:
            # Update stream data without synchronization logic
            with audio_manager.data_lock:
                if client_id in audio_manager.active_streams:
                    audio_manager.active_streams[client_id]['data'] = audio_data
                    audio_manager.active_streams[client_id]['last_update'] = datetime.now()
                    # Commenting out latency calculation used for sync
                    # audio_manager.active_streams[client_id]['latency'] = \
                    #     (datetime.now().timestamp() - timestamp) * 1000
                    audio_manager.active_streams[client_id]['latency'] = 0
            
            # Broadcast all streams' data
            socketio.emit('streams_update', audio_manager.get_streams_data())
            
    except Exception as e:
        print(f"Error processing audio data: {e}")
        import traceback
        traceback.print_exc()
            
    except Exception as e:
        print(f"Error processing audio data: {e}")
        import traceback
        traceback.print_exc()

def cleanup(signal, frame):
    """Cleanup function for graceful shutdown"""
    print("\nCleaning up...")
    audio_manager.cleanup()
    print("Cleanup completed. Exiting...")
    sys.exit(0)

if __name__ == '__main__':
    import signal
    import sys
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, cleanup)
    
    try:
        print("Starting server...")
        print("Access the application at http://localhost:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        print(f"Error starting server: {e}")
        audio_manager.cleanup()