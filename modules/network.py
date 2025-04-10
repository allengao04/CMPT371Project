import pickle

'''
    Network utilities for send and receive data using Python TCP Socket object
'''

def send_data(sock, data):
    """Serialize and send a Python object over a TCP socket."""
    try:
        # Serialize the data (use pickle for simplicity)
        payload = pickle.dumps(data)
        # Send the length of the payload first (fixed 4-byte header)
        length = len(payload)
        sock.sendall(length.to_bytes(4, 'big') + payload)
    except Exception as e:
        # Handle send exceptions (e.g., broken connection)
        print(f"send_data error: {e}")

def recv_data(sock):
    """Receive a serialized Python object from a TCP socket."""
    try:
        # Read the 4-byte length header (type)
        raw_length = sock.recv(4)
        if not raw_length:
            return None  # connection closed
        length = int.from_bytes(raw_length, 'big')
        # Receive the data based on length
        data_bytes = b''
        while len(data_bytes) < length:
            packet = sock.recv(length - len(data_bytes))
            if not packet:
                return None
            data_bytes += packet
        # Deserialize the object
        data = pickle.loads(data_bytes)
        return data
    except Exception as e:
        print(f"recv_data error: {e}")
        return None
