import socket
import threading
import time
import pygame
import pygame
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
        self.ready = False

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
        self.lock = threading.RLock()  # NEW: dedicated mutex lock for concurrency

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
        self.lobby_active = True
        self.countdown = None

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

        # Pygame initialization (MUST come before any Pygame operations)
        pygame.init()
        self.lobby_screen = pygame.display.set_mode((1100, 800))  # Minimum display setup
        pygame.display.set_caption("Server Lobby")
        self.font = pygame.font.SysFont('Arial', 24)
        
        # Verify initialization worked
        if not pygame.display.get_init():
            raise RuntimeError("Pygame display failed to initialize")

        # Pygame initialization (MUST come before any Pygame operations)
        pygame.init()
        self.lobby_screen = pygame.display.set_mode((1100, 800))  # Minimum display setup
        pygame.display.set_caption("Server Lobby")
        self.font = pygame.font.SysFont('Arial', 24)
        
        # Verify initialization worked
        if not pygame.display.get_init():
            raise RuntimeError("Pygame display failed to initialize")

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
                        # Update remaining time
                        current_time = time.time()
                        time_left = self.time_limit - int(current_time - self.start_time) if self.start_time else self.time_limit
                        if time_left <= 0:
                            # Time up: end game
                            self.game_over = True
                            break
                        # Send periodic state update (to sync timer on clients)
                        state_msg = self.build_state_message()
                        self.broadcast(state_msg)
            # If loop exited due to game_over (time up), broadcast final scores and end
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
                    # Reject new connections if game is full
                    send_data(client_sock, {"type": "error", "message": "Server full"})
                    client_sock.close()
                    continue
                # Assign new player ID and spawn position
                player_id = next_player_id
                spawn_x, spawn_y = self.find_spawn_position(player_id)
                next_player_id += 1
                new_player = Player(player_id, spawn_x, spawn_y)
                self.players[player_id] = new_player
                self.clients[player_id] = client_sock
                print(f"Player {player_id} connected from {addr}, spawn at ({spawn_x},{spawn_y})")
                # Start game when the first player connects
                if not self.game_started:
                    self.game_started = True
                    self.start_time = time.time()
                # Send initial game state to the new player
                init_msg = {
                    "type": "init",
                    "player_id": player_id,
                    "players": {pid: {"x": p.x, "y": p.y, "score": p.score} for pid, p in self.players.items()},
                    "microphones": [{"id": m.id, "x": m.x, "y": m.y, "answered": m.answered} for m in self.microphones],
                    "time_left": self.time_limit if not self.start_time else max(0, self.time_limit - int(time.time() - self.start_time))
                }
                send_data(client_sock, init_msg)
            # Launch a new thread to handle communication with this client
            client_thread = threading.Thread(target=self.handle_client, args=(client_sock, player_id), daemon=True)
            client_thread.start()
        print("Stopped accepting new clients.")

    def find_spawn_position(self, player_id):
   # """Assign each player to one of the four corners of the grid."""
        grid_width = self.map_width  # Example: 20
        grid_height = self.map_height  # Example: 16

        corner_positions = {
            1: (0, 2),  # Top-left
            2: (grid_width - 1, 2),  # Top-right
            3: (0, grid_height - 1),  # Bottom-left
            4: (grid_width - 1, grid_height - 1)  # Bottom-right
        }

        return corner_positions.get(player_id, (0, 0))  # Default to (0,0) if more than 4 players


    def handle_client(self, client_socket, player_id):
        """Receive and handle messages from a single client."""
        while not self.game_over:
            data = recv_data(client_socket)
            if data is None:
                # Client disconnected or connection error
                break
            msg_type = data.get("type")

            if msg_type == "player_ready":
                # Handle ready status toggle
                with self.lock:
                    player = self.players.get(player_id)
                    if player:
                        player.ready = not player.ready
                        print(f"Player {player_id} ready status: {player.ready}")
                        self.broadcast_lobby_update()
                        # Start countdown if all players are ready
                        if self.players and all(p.ready for p in self.players.values()):
                            self.start_game_countdown()

            elif msg_type == "move" and not self.lobby_active:
                # Handle movement input from client
                direction = data.get("direction")
                with self.lock:
                    player = self.players.get(player_id)
                    if player:
                        new_x, new_y = player.x, player.y
                        if direction == "up":
                            new_y -= 1
                        elif direction == "down":
                            new_y += 1
                        elif direction == "left":
                            new_x -= 1
                        elif direction == "right":
                            new_x += 1
                        # Bounds check and obstacle collision
                        if 0 <= new_x < self.map_width and 0 <= new_y < self.map_height:
                            if (new_x, new_y) not in self.obstacles:
                                player.x = new_x
                                player.y = new_y
                # Broadcast updated state after movement
                with self.lock:
                    state_msg = self.build_state_message()
                self.broadcast(state_msg)

            elif msg_type == "interact" and not self.lobby_active:
                # Handle interaction (attempt to use a microphone)
                with self.lock:
                    player = self.players.get(player_id)
                    if not player:
                        continue
                    # Check if there's an unanswered microphone at player's position
                    mic_obj = None
                    for m in self.microphones:
                        if m.x == player.x and m.y == player.y and not m.answered:
                            mic_obj = m
                            break
                    if mic_obj:
                        if mic_obj.active_by is None:
                            # Lock this microphone to this player and send question
                            mic_obj.active_by = player_id
                            question_msg = {
                                "type": "question",
                                "mic_id": mic_obj.id,
                                "question": mic_obj.question,
                                "options": mic_obj.options
                            }
                            send_data(self.clients[player_id], question_msg)
                        else:
                            # Microphone already in use by another player
                            info_msg = {"type": "info", "message": "Microphone is currently in use by another player."}
                            send_data(self.clients[player_id], info_msg)

            elif msg_type == "answer" and not self.lobby_active:
                # Handle quiz answer submission from client
                mic_id = data.get("mic_id")
                answer_idx = data.get("answer")
                # Determine correctness and update state
                with self.lock:
                    mic_obj = next((m for m in self.microphones if m.id == mic_id), None)
                    if not mic_obj or mic_obj.answered:
                        # Question already answered or invalid mic_id
                        continue
                    # Ensure this player activated the microphone
                    if mic_obj.active_by != player_id:
                        continue  # Not the player currently answering this question
                    if answer_idx == mic_obj.correct_index:
                        # Correct answer
                        mic_obj.answered = True
                        mic_obj.active_by = None
                        # Update score
                        if player_id in self.players:
                            self.players[player_id].score += 1
                        # Prepare state update and check game completion
                        state_msg = self.build_state_message()
                        all_answered = all(m.answered for m in self.microphones)
                        if all_answered:
                            self.game_over = True
                        # Notify answering player of success
                        result_msg = {"type": "answer_result", "correct": True}
                        send_data(self.clients[player_id], result_msg)
                    else:
                        # Incorrect answer
                        # Leave mic active_by as is, allowing the player to try again
                        result_msg = {"type": "answer_result", "correct": False}
                        send_data(self.clients[player_id], result_msg)
                        # Do not broadcast state on incorrect answer
                        mic_obj = None  # ensure we don't broadcast below
                # If a question was answered correctly, broadcast updated state
                if mic_obj and mic_obj.answered:
                    self.broadcast(state_msg)
                    if self.game_over:
                        # If that was the last question, announce game over
                        self.broadcast_game_over()
                        break

        # Cleanup after client disconnects or game ends
        with self.lock:
            if player_id in self.players:
                print(f"Player {player_id} disconnected.")
                # Remove player and free any mic they were using
                self.players.pop(player_id, None)
                self.clients.pop(player_id, None)
                for m in self.microphones:
                    if m.active_by == player_id:
                        m.active_by = None
                # If game is still ongoing, broadcast updated state (player removed)
                if not self.game_over and not self.lobby_active:
                    state_msg = self.build_state_message()
                    self.broadcast(state_msg)
                elif self.lobby_active:
                    # Update lobby state if in lobby
                    self.broadcast_lobby_update()
        client_socket.close()

    def build_state_message(self):
        """Compose a game state message (players, microphones, time, etc.) for clients."""
        # Compute remaining time
        time_left_val = None
        if self.game_started and self.start_time:
            elapsed = int(time.time() - self.start_time)
            remaining = self.time_limit - elapsed
            time_left_val = max(0, remaining)
        # Build data dictionaries
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
