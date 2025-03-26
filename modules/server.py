import socket
import threading
import time
from network import send_data, recv_data
from helper import args

# Optional: If game.py defines Player, Microphone classes or map data, those can be imported.

# Otherwise, define minimal classes for internal use as done here.

class Player:
    def __init__(self, pid, x, y):
        self.id = pid
        self.x = x
        self.y = y
        self.score = 0

class Microphone:
    def __init__(self, mid, x, y, question, options, correct_index):
        self.id = mid
        self.x = x
        self.y = y
        self.question = question
        self.options = options
        self.correct_index = correct_index
        self.answered = False
        self.active_by = None  # player id currently interacting (if any)
        self.lock = threading.Lock()  # NEW: dedicated mutex lock for concurrency

# -------------------------------
# Server Class
# -------------------------------

class Server:
    def __init__(self, host, port, time_limit, max_players=4):
        self.host = host
        self.port = port
        self.max_players = max_players
        self.time_limit = time_limit
        self.start_time = None
        self.game_started = False
        self.game_over = False

        # Game state data structures
        self.players = {}      # {player_id: Player}
        self.clients = {}      # {player_id: socket}
        self.microphones = []  # list of Microphone objects

        # Define the game world (grid size and obstacles)
        self.map_width = 50
        self.map_height = 40
        self.obstacles = set()
        # Example obstacles: a wall at x=15, y=5..9
        for y in range(5, 10):
            self.obstacles.add((15, y))

        # Initialize quiz questions and microphone objects
        q1 = "What is the capital of France?"
        opts1 = ["Paris", "London", "Rome", "Berlin"]
        q2 = "2 + 2 * 2 = ?"
        opts2 = ["6", "8", "4", "2"]
        q3 = "Which planet is known as the Red Planet?"
        opts3 = ["Earth", "Mars", "Jupiter", "Saturn"]
        self.microphones = [
            Microphone(1, 10, 5, q1, opts1, correct_index=0),
            Microphone(2, 4, 12, q2, opts2, correct_index=0),
            Microphone(3, 20, 18, q3, opts3, correct_index=1)
        ]

        # Synchronization lock for thread-safe state updates (global game state)
        self.lock = threading.Lock()

        # Set up the server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"Server listening on {self.host}:{self.port}")

    def start(self):
        """Start the server, accepting clients and managing game loop."""
        # Start a thread to accept new client connections
        accept_thread = threading.Thread(target=self.accept_clients, daemon=True)
        accept_thread.start()

        # Main server loop: handle game timer and game-over conditions
        try:
            while not self.game_over:
                time.sleep(1)
                with self.lock:
                    if self.game_started and not self.game_over:
                        current_time = time.time()
                        time_left = self.time_limit - int(current_time - self.start_time) if self.start_time else self.time_limit
                        if time_left <= 0:
                            self.game_over = True
                            break
                        state_msg = self.build_state_message()
                        self.broadcast(state_msg)
            if self.game_over:
                self.broadcast_game_over()
        except KeyboardInterrupt:
            print("Server shutting down (KeyboardInterrupt).")
        finally:
            self.stop()

    def accept_clients(self):
        """Accept incoming client connections and initialize players."""
        next_player_id = 1
        while not self.game_over:
            try:
                client_sock, addr = self.server_socket.accept()
            except OSError:
                break  # Socket closed, stop accepting
            with self.lock:
                if len(self.players) >= self.max_players:
                    send_data(client_sock, {"type": "error", "message": "Server full"})
                    client_sock.close()
                    continue
                player_id = next_player_id
                spawn_x, spawn_y = self.find_spawn_position(player_id)
                next_player_id += 1
                new_player = Player(player_id, spawn_x, spawn_y)
                self.players[player_id] = new_player
                self.clients[player_id] = client_sock
                print(f"Player {player_id} connected from {addr}, spawn at ({spawn_x},{spawn_y})")
                if not self.game_started:
                    self.game_started = True
                    self.start_time = time.time()
                init_msg = {
                    "type": "init",
                    "player_id": player_id,
                    "players": {pid: {"x": p.x, "y": p.y, "score": p.score} for pid, p in self.players.items()},
                    "microphones": [{"id": m.id, "x": m.x, "y": m.y, "answered": m.answered} for m in self.microphones],
                    "time_left": self.time_limit if not self.start_time else max(0, self.time_limit - int(time.time() - self.start_time))
                }
                send_data(client_sock, init_msg)
            client_thread = threading.Thread(target=self.handle_client, args=(client_sock, player_id), daemon=True)
            client_thread.start()
        print("Stopped accepting new clients.")

    def find_spawn_position(self, player_id):
        grid_width = self.map_width
        grid_height = self.map_height

        corner_positions = {
            1: (0, 2),  # Top-left
            2: (grid_width - 1, 2),  # Top-right
            3: (0, grid_height - 1),  # Bottom-left
            4: (grid_width - 1, grid_height - 1)  # Bottom-right
        }
        return corner_positions.get(player_id, (0, 0))

    def handle_client(self, client_socket, player_id):
        """Receive and handle messages from a single client."""
        while not self.game_over:
            data = recv_data(client_socket)
            if data is None:
                break
            msg_type = data.get("type")
            if msg_type == "move":
                direction = data.get("direction")
                with self.lock:
                    player = self.players.get(player_id)
                    if player:
                        new_x, new_y = player.x, player.y
                        if direction.lower() == "up":
                            new_y -= 1
                        elif direction.lower() == "down":
                            new_y += 1
                        elif direction.lower() == "left":
                            new_x -= 1
                        elif direction.lower() == "right":
                            new_x += 1
                        if 0 <= new_x < self.map_width and 0 <= new_y < self.map_height:
                            if (new_x, new_y) not in self.obstacles:
                                player.x = new_x
                                player.y = new_y
                with self.lock:
                    state_msg = self.build_state_message()
                self.broadcast(state_msg)
            elif msg_type == "interact":
                # Handle interaction: attempt to pick up a microphone (quiz)
                with self.lock:
                    player = self.players.get(player_id)
                    if not player:
                        continue
                    mic_obj = None
                    for m in self.microphones:
                        if m.x == player.x and m.y == player.y and not m.answered:
                            mic_obj = m
                            break
                    if mic_obj:
                        # NEW: Try to acquire the mic's lock without blocking
                        if mic_obj.lock.acquire(blocking=False):
                            # Successfully acquired the lock.
                            # Double-check that no one is using it.
                            if mic_obj.active_by is None:
                                mic_obj.active_by = player_id
                                question_msg = {
                                    "type": "question",
                                    "mic_id": mic_obj.id,
                                    "question": mic_obj.question,
                                    "options": mic_obj.options
                                }
                                send_data(self.clients[player_id], question_msg)
                            else:
                                mic_obj.lock.release()
                                info_msg = {"type": "info", "message": "Microphone is currently in use by another player."}
                                send_data(self.clients[player_id], info_msg)
                        else:
                            # Could not acquire the lock; mic is busy.
                            info_msg = {"type": "info", "message": "Microphone is currently in use by another player."}
                            send_data(self.clients[player_id], info_msg)
            elif msg_type == "answer":
                # Handle quiz answer submission
                mic_id = data.get("mic_id")
                answer_idx = data.get("answer")
                with self.lock:
                    mic_obj = next((m for m in self.microphones if m.id == mic_id), None)
                    if not mic_obj or mic_obj.answered:
                        continue
                    # Verify the player is the one who locked the mic
                    if mic_obj.active_by != player_id:
                        continue
                    if answer_idx == mic_obj.correct_index:
                        # Correct answer: mark quiz as answered, update score.
                        mic_obj.answered = True
                        mic_obj.active_by = None
                        # Release the mic's lock since the quiz is complete.
                        mic_obj.lock.release()
                        if player_id in self.players:
                            self.players[player_id].score += 1
                        state_msg = self.build_state_message()
                        all_answered = all(m.answered for m in self.microphones)
                        if all_answered:
                            self.game_over = True
                        result_msg = {"type": "answer_result", "correct": True}
                        send_data(self.clients[player_id], result_msg)
                    else:
                        # Incorrect answer: release the microphone for others.
                        mic_obj.active_by = None
                        mic_obj.lock.release()
                        result_msg = {"type": "answer_result", "correct": False}
                        send_data(self.clients[player_id], result_msg)
                # Broadcast updated state if a question was answered correctly.
                if mic_obj and mic_obj.answered:
                    self.broadcast(state_msg)
                    if self.game_over:
                        self.broadcast_game_over()
                        break
            # (Handle additional message types here if needed)
        # Cleanup after client disconnects or game end.
        with self.lock:
            if player_id in self.players:
                print(f"Player {player_id} disconnected.")
                self.players.pop(player_id, None)
                self.clients.pop(player_id, None)
                # Release any microphone held by the disconnecting player.
                for m in self.microphones:
                    if m.active_by == player_id:
                        m.active_by = None
                        try:
                            m.lock.release()
                        except RuntimeError:
                            # The lock may not be held by this thread; ignore if so.
                            pass
                if not self.game_over:
                    state_msg = self.build_state_message()
                    self.broadcast(state_msg)
        client_socket.close()

    def build_state_message(self):
        """Compose a game state message (players, microphones, time, etc.) for clients."""
        time_left_val = None
        if self.game_started and self.start_time:
            elapsed = int(time.time() - self.start_time)
            remaining = self.time_limit - elapsed
            time_left_val = max(0, remaining)
        players_data = {pid: {"x": p.x, "y": p.y, "score": p.score} for pid, p in self.players.items()}
        mics_data = [{"id": m.id, "x": m.x, "y": m.y, "answered": m.answered} for m in self.microphones]
        msg = {"type": "state", "players": players_data, "microphones": mics_data}
        if time_left_val is not None:
            msg["time_left"] = time_left_val
        if self.game_over:
            msg["game_over"] = True
        return msg

    def broadcast(self, data, exclude_id=None):
        """Send a message to all connected clients (optionally excluding one client)."""
        for pid, sock in list(self.clients.items()):
            if exclude_id is not None and pid == exclude_id:
                continue
            try:
                send_data(sock, data)
            except Exception as e:
                print(f"Error sending to Player {pid}: {e}")

    def broadcast_game_over(self):
        """Broadcast a game-over message with final scores to all players."""
        scores = {pid: {"score": p.score} for pid, p in self.players.items()}
        msg = {"type": "game_over", "players": scores}
        self.broadcast(msg)

    def stop(self):
        """Shut down the server and close all client connections."""
        self.game_over = True
        for pid, sock in list(self.clients.items()):
            sock.close()
        try:
            self.server_socket.close()
        except OSError:
            pass
        print("Server stopped.")


if __name__ == "__main__":
    # Parse Arguments
    ip_address = args.ip_address
    port = int(args.port)
    time_limit = int(args.time_limit)

    # Start Server
    server = Server(host=ip_address, port=port, time_limit=time_limit)
    server.start()
