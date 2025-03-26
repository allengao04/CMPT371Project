import socket
import threading
import time
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

    def start(self):
        """Main server loop"""
        accept_thread = threading.Thread(target=self.accept_clients, daemon=True)
        accept_thread.start()
<<<<<<< HEAD

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

=======
        self.run_lobby()
    
>>>>>>> b40f55d (added base server lobby)
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
<<<<<<< HEAD
        return corner_positions.get(player_id, (0, 0))
=======

        return corner_positions.get(player_id, (0, 0))  # Default to (0,0) if more than 4 players

    def broadcast_lobby_update(self):
        """Send current lobby state to all players"""
        msg = {
            "type": "lobby_state",
            "players": {pid: p.ready for pid, p in self.players.items()}
        }
        self.broadcast(msg)

    def run_lobby(self):
        """Admin lobby UI"""
        clock = pygame.time.Clock()
        while self.lobby_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.shutdown()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    if all(p.ready for p in self.players.values()):
                        self.start_game_countdown()

            # Draw lobby
            self.lobby_screen.fill((30, 30, 60))
            greeting = self.font.render(f"Welcome!!!", True, (255,255,255))
            ip_text = self.font.render(f"Server IP: {self.host}", True, (255,255,255))
            greeting_pos = greeting.get_rect(center=(550,50))
            ip_text_pos = ip_text.get_rect(center=(550,100))
            self.lobby_screen.blit(greeting, greeting_pos)
            self.lobby_screen.blit(ip_text, ip_text_pos)
            
            y = 150
            for pid, player in self.players.items():
                status = "Ready" if player.ready else "Waiting"
                color = (0,255,0) if player.ready else (255,0,0)
                text = self.font.render(f"Player {pid}: {status}", True, color)
                self.lobby_screen.blit(text, (50, y))
                y += 40
            
            pygame.display.flip()
            clock.tick(30)
        
        pygame.quit()

    def start_game_countdown(self):
        """10-second countdown before game starts"""
        for i in range(10, 0, -1):
            self.countdown = i
            self.broadcast({"type": "countdown", "time": i})
            time.sleep(1)
        self.lobby_active = False
        self.broadcast({"type": "game_start"})
>>>>>>> b40f55d (added base server lobby)

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
            elif msg_type == "player_ready":
                with self.lock:
                    player = self.players.get(player_id)
                    if player:
                        player.ready = not player.ready
                        self.broadcast_lobby_update()
                        if all(p.ready for p in self.players.values()): # if every connected player is ready, we can start the game.
                            self.start_game_
            elif msg_type == "start_countdown":
                if all(p.ready for p in self.players.values()):
                    self.start_game_countdown()
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
<<<<<<< HEAD
    # Parse Arguments
    ip_address = args.ip_address
    port = int(args.port)
    time_limit = int(args.time_limit)

    # Start Server
    server = Server(host=ip_address, port=port, time_limit=time_limit)
    server.start()
=======
    # Auto-detect available IP
    host = socket.gethostbyname(socket.gethostname())
    try:
        server = Server(host=host)
        server.start()
    except OSError:
        # Fallback to localhost if network unavailable
        server = Server(host="127.0.0.1")
        server.start()
>>>>>>> b40f55d (added base server lobby)
