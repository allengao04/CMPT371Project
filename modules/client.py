import pygame
import socket
import threading
import time
from network import send_data, recv_data

class Client:
    def __init__(self, host='localhost', port=5000):
        self.host = host
        self.port = port
        self.sock = None
        self.player_id = None

        # Game state (synchronized with server)
        self.players = {}      # {player_id: {"x": ..., "y": ..., "score": ...}, ...}
        self.microphones = []  # [ {"id": ..., "x": ..., "y": ..., "answered": ...}, ... ]
        self.time_left = None
        self.game_over = False

        # Quiz state for the local player
        self.in_question = False
        self.current_question = None   # {"id": ..., "text": ..., "options": [...]}
        self.last_answer_correct = None  # Tracks result of last answer attempt (for feedback)

        # Thread synchronization lock for state
        self.lock = threading.Lock()

        # Initialize Pygame for rendering
        pygame.init()
        self.screen = pygame.display.set_mode((640, 480))
        pygame.display.set_caption("Multiplayer Quiz Game")
        self.font = pygame.font.SysFont(None, 24)
        # Define some colors for drawing
        self.color_bg = (200, 200, 200)         # background color
        self.color_player = (0, 0, 255)         # local player color
        self.color_other_player = (0, 255, 0)   # other players color
        self.color_microphone = (255, 165, 0)   # microphone object color (orange)
        self.color_text = (0, 0, 0)            # text color (black)
        self.color_overlay_bg = (255, 255, 255) # overlay background (white)
        self.color_overlay_text = (0, 0, 0)    # overlay text color (black)

    def connect_to_server(self):
        """Connect to the game server and perform initial handshake to get game state."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        init_data = recv_data(self.sock)
        if init_data and init_data.get("type") == "init":
            with self.lock:
                self.player_id = init_data["player_id"]
                self.players = init_data.get("players", {})
                self.microphones = init_data.get("microphones", [])
                self.time_left = init_data.get("time_left", None)
            print(f"Connected to server as Player {self.player_id}")
        else:
            raise ConnectionError("Failed to receive initial game state from server.")

    def network_listener(self):
        """Background thread to receive messages from the server and update local state."""
        while True:
            data = recv_data(self.sock)
            if not data:
                # Connection closed or error
                print("Disconnected from server.")
                break
            msg_type = data.get("type")
            if msg_type == "state":
                # Update game state (positions, scores, microphones, time)
                with self.lock:
                    if "players" in data:
                        self.players = data["players"]
                    if "microphones" in data:
                        self.microphones = data["microphones"]
                    if "time_left" in data:
                        self.time_left = data["time_left"]
                    if data.get("game_over"):
                        self.game_over = True
                continue  # proceed to next message
            elif msg_type == "question":
                # Received a quiz question to display (for this client only)
                with self.lock:
                    self.in_question = True
                    self.current_question = {
                        "id": data["mic_id"],
                        "text": data["question"],
                        "options": data["options"]
                    }
                    self.last_answer_correct = None
                print(f"Quiz question received: {data['question']}")
            elif msg_type == "answer_result":
                # Feedback on an answer submitted by this player
                correct = data.get("correct", False)
                with self.lock:
                    if correct:
                        # Correct answer; exit quiz mode
                        self.in_question = False
                        self.current_question = None
                        self.last_answer_correct = True
                    else:
                        # Incorrect; stay in quiz mode for retry
                        self.last_answer_correct = False
                if correct:
                    print("Answered correctly!")
                else:
                    print("Answer was incorrect, try again.")
            elif msg_type == "game_over":
                # Game over message with final scores
                with self.lock:
                    self.game_over = True
                    if "players" in data:
                        self.players = data["players"]  # update final scores
                print("Game over received from server.")
                break
            # (Other message types like "info" can be handled similarly)
        # Clean up when done
        self.sock.close()

    def send_move(self, direction):
        """Send a movement command (direction: 'up','down','left','right') to the server."""
        send_data(self.sock, {"type": "move", "direction": direction})

    def send_interact(self):
        """Send an interaction command to the server (attempt to use a microphone)."""
        send_data(self.sock, {"type": "interact"})

    def send_answer(self, mic_id, answer_index):
        """Send an answer choice for a quiz question to the server."""
        msg = {"type": "answer", "mic_id": mic_id, "answer": answer_index}
        send_data(self.sock, msg)

    def run(self):
        """Main loop for handling user input and rendering the game state."""
        # Start the network listener thread
        listener = threading.Thread(target=self.network_listener, daemon=True)
        listener.start()

        clock = pygame.time.Clock()
        running = True
        while running:
            # Handle Pygame events (input, quit)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    # If game over screen is up, any key can exit the game
                    if self.game_over:
                        running = False
                        continue
                    if not self.in_question:
                        # Movement keys (WASD or arrow keys)
                        if event.key in (pygame.K_w, pygame.K_UP):
                            self.send_move("up")
                        elif event.key in (pygame.K_s, pygame.K_DOWN):
                            self.send_move("down")
                        elif event.key in (pygame.K_a, pygame.K_LEFT):
                            self.send_move("left")
                        elif event.key in (pygame.K_d, pygame.K_RIGHT):
                            self.send_move("right")
                        # Interaction key (E or Space) to trigger quiz at microphone
                        elif event.key in (pygame.K_e, pygame.K_SPACE):
                            self.send_interact()
                    else:
                        # If currently answering a question, number keys select an answer
                        selected_index = None
                        if event.key == pygame.K_1:
                            selected_index = 0
                        elif event.key == pygame.K_2:
                            selected_index = 1
                        elif event.key == pygame.K_3:
                            selected_index = 2
                        elif event.key == pygame.K_4:
                            selected_index = 3
                        if selected_index is not None and self.current_question:
                            # Ensure the selected option is valid, then send answer
                            if 0 <= selected_index < len(self.current_question["options"]):
                                self.send_answer(self.current_question["id"], selected_index)
                        # Allow cancelling the quiz UI with ESCAPE
                        if event.key == pygame.K_ESCAPE:
                            with self.lock:
                                self.in_question = False
                                self.current_question = None
                                self.last_answer_correct = None

            # Drawing the game state
            self.screen.fill(self.color_bg)
            # Copy state under lock to avoid inconsistency while drawing
            with self.lock:
                players_snapshot = {pid: info.copy() for pid, info in self.players.items()}
                mics_snapshot = [mic.copy() for mic in self.microphones]
                time_left = self.time_left
                in_question = self.in_question
                current_question = self.current_question.copy() if self.current_question else None
                last_answer_correct = self.last_answer_correct
                game_over_flag = self.game_over

            if not game_over_flag:
                # Draw microphones that are not yet answered
                for mic in mics_snapshot:
                    if not mic.get("answered"):
                        # Represent microphone as a rectangle on the grid
                        rect = pygame.Rect(mic["x"] * 20, mic["y"] * 20, 20, 20)
                        pygame.draw.rect(self.screen, self.color_microphone, rect)
                # Draw players
                for pid, info in players_snapshot.items():
                    rect = pygame.Rect(info["x"] * 20, info["y"] * 20, 20, 20)
                    color = self.color_player if pid == self.player_id else self.color_other_player
                    pygame.draw.rect(self.screen, color, rect)
                # Draw timer (if available)
                if time_left is not None:
                    minutes = time_left // 60
                    seconds = time_left % 60
                    timer_text = f"Time: {minutes:02d}:{seconds:02d}"
                    txt_surface = self.font.render(timer_text, True, self.color_text)
                    self.screen.blit(txt_surface, (10, 10))
                # Draw scores for each player
                y_offset = 10
                for pid, info in players_snapshot.items():
                    score_text = f"Player {pid}: {info['score']}"
                    txt_surface = self.font.render(score_text, True, self.color_text)
                    # Display scores on the right side
                    self.screen.blit(txt_surface, (500, y_offset))
                    y_offset += 20
                # If a quiz question is active, draw the question overlay
                if in_question and current_question:
                    # Draw semi-transparent overlay background
                    overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                    overlay.fill((255, 255, 255, 230))  # white with slight transparency
                    self.screen.blit(overlay, (0, 0))
                    # Render question text
                    question_text = current_question["text"]
                    question_surface = self.font.render(question_text, True, self.color_overlay_text)
                    self.screen.blit(question_surface, (50, 100))
                    # Render multiple-choice options
                    for idx, option in enumerate(current_question["options"], start=1):
                        option_text = f"{idx}. {option}"
                        option_surface = self.font.render(option_text, True, self.color_overlay_text)
                        self.screen.blit(option_surface, (70, 130 + 30 * idx))
                    # If last answer attempt was wrong, show feedback
                    if last_answer_correct is False:
                        feedback_surface = self.font.render("Incorrect! Try again.", True, (255, 0, 0))
                        self.screen.blit(feedback_surface, (50, 130 + 30 * (len(current_question["options"]) + 1)))
            else:
                # Game over: display final scores
                overlay = pygame.Surface(self.screen.get_size())
                overlay.fill(self.color_bg)
                self.screen.blit(overlay, (0, 0))
                title_surface = self.font.render("Game Over", True, self.color_text)
                self.screen.blit(title_surface, (260, 80))
                # List scores sorted by performance
                sorted_scores = sorted(players_snapshot.items(), key=lambda item: item[1]["score"], reverse=True)
                y_pos = 130
                for rank, (pid, info) in enumerate(sorted_scores, start=1):
                    score_line = f"{rank}. Player {pid} - Score: {info['score']}"
                    line_surface = self.font.render(score_line, True, self.color_text)
                    self.screen.blit(line_surface, (180, y_pos))
                    y_pos += 30
                exit_surface = self.font.render("Press any key to exit", True, self.color_text)
                self.screen.blit(exit_surface, (200, y_pos + 20))

            pygame.display.flip()
            clock.tick(30)  # Cap the frame rate to 30 FPS

        # Clean up Pygame on exit
        pygame.quit()

# Example usage (if running this module directly):
# client = Client(host="127.0.0.1", port=5000)
# client.connect_to_server()
# client.run()

if __name__ == "__main__":
    # Change host to the server's IP address if needed.
    client = Client(host="127.0.0.1", port=5000)
    client.connect_to_server()
    client.run()