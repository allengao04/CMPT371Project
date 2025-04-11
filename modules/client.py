import pygame
import socket
import threading
import time
from game import PLAYER_COLORS
from network import send_data, recv_data
from helper import args

'''
    Intialize a Client object and connect to server with host and port:
        - drawing lobby screen and game screen when it is running
        - communicate with the server with TCP socket and a custom messaging scheme
        - handle game state when receiving data from the server
'''


class Client:
    def __init__(self, host, port):
        # Grid and map setup
        self.GRID_SIZE = 20
        self.map_width = 50  # Number of tiles horizontally
        self.map_height = 40  # Number of tiles vertically

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

        # Lobby state
        self.in_lobby = True
        self.players_ready = {}
        self.countdown = None
        self.ready = False

        # Thread synchronization lock for state
        self.lock = threading.Lock()

        # Initialize Pygame for rendering
        pygame.init()
        game_area_width = self.map_width * self.GRID_SIZE
        game_area_height = self.map_height * self.GRID_SIZE
        self.screen = pygame.display.set_mode((game_area_width, game_area_height))
        
        pygame.display.set_caption("Multiplayer Quiz Game")
        self.font = pygame.font.SysFont(None, 24)
        # Define some colors
        self.color_bg = (200, 200, 200)         # background color
        self.color_player = (0, 0, 255)         # local player color
        self.color_other_player = (0, 255, 0)   # other players color
        self.color_microphone = (255, 165, 0)   # microphone object color (orange)
        self.color_text = (0, 0, 0)             # text color (black)
        self.color_overlay_bg = (255, 255, 255) # overlay background (white)
        self.color_overlay_text = (0, 0, 0)     # overlay text color (black)

    def connect_to_server(self):
        """Connect to the game server and perform initial handshake to get game state."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))

        # initialize data sent from server when connection is setup
        init_data = recv_data(self.sock)
        if init_data and init_data.get("type") == "init":
            with self.lock:
                self.player_id = init_data["player_id"]
                self.players = init_data.get("players", {})
            print(f"Connected as Player {self.player_id}")
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
            if data.get("type") == "lobby_state":
                with self.lock:
                    self.players_ready = data["players"]
                    
            elif data.get("type") == "countdown":
                with self.lock:
                    self.countdown = data["time"]
                    
            elif data.get("type") == "game_start":
                with self.lock:
                    self.in_lobby = False

            elif msg_type == "state":
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

            elif msg_type == "info":
                message = data.get("message", "")
                print(f"[INFO]: {message}")
                with self.lock:
                    self.info_message = message
                    self.info_message_time = time.time()
        # Clean up when done
        self.sock.close()

    def draw_lobby(self):
        """Render the lobby screen with visible UI elements"""

        # Ready button - CENTERED version
        button_width, button_height = 200, 50
        button_x = self.screen.get_width()//2 - button_width//2
        button_y = self.screen.get_height()//2
        self.button = pygame.Rect(button_x, button_y, button_width, button_height)  # Store as instance variable

        # Draw button with hover effect
        mouse_pos = pygame.mouse.get_pos()
        button_color = (0, 200, 0) if self.button.collidepoint(mouse_pos) else (0, 150, 0)
        pygame.draw.rect(self.screen, button_color, self.button)
        
        # Button text
        button_text = "READY" if not self.ready else "UNREADY"
        text_surf = self.font.render(button_text, True, (255, 255, 255))
        text_rect = text_surf.get_rect(center=self.button.center)
        self.screen.blit(text_surf, text_rect)
        
        # Instructions
        help_font = pygame.font.SysFont('Arial', 24)
        help_text = help_font.render("Click READY when all players have joined", 
                                True, (200, 200, 200))
        self.screen.blit(help_text, (self.screen.get_width()//2 - help_text.get_width()//2, 
                                button_y + button_height + 20))
        
        # Countdown display
        if self.countdown:
            count_font = pygame.font.SysFont('Arial', 72)
            count_text = count_font.render(str(self.countdown), True, (255, 255, 255))
            count_rect = count_text.get_rect(center=(self.screen.get_width()//2, 
                                                self.screen.get_height()//2 - 50))
            self.screen.blit(count_text, count_rect)

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

    def get_player_color(self, player_id):
        """=Return a unique color for each player ID."""
        return PLAYER_COLORS.get(player_id, (200, 200, 200))  # Gray fallback
    
    def run(self):
        """Main loop for handling user input and rendering the game state."""
        listener = threading.Thread(target=self.network_listener, daemon=True)
        listener.start()

        clock = pygame.time.Clock()
        running = True
        
        while running:
            # Handle Pygame events (input, quit)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                # Handle lobby interactions
                if self.in_lobby:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if hasattr(self, 'button') and self.button.collidepoint(event.pos):
                            self.ready = not self.ready
                            send_data(self.sock, {"type": "player_ready"})
                
                # Handle game interactions (only when not in lobby and not game over)
                elif not self.game_over:
                    if event.type == pygame.KEYDOWN:
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
                            # If answering a question
                            selected_index = None
                            if event.key == pygame.K_1:
                                selected_index = 0
                            elif event.key == pygame.K_2:
                                selected_index = 1
                            elif event.key == pygame.K_3:
                                selected_index = 2
                            elif event.key == pygame.K_4:
                                selected_index = 3
                            elif event.key == pygame.K_ESCAPE:
                                mic_id = self.current_question["id"] if self.current_question else None
                                with self.lock:
                                    self.in_question = False
                                    self.current_question = None
                                    self.last_answer_correct = None
                                send_data(self.sock, {"type": "cancel_quiz", "mic_id": mic_id})
                            
                            if selected_index is not None and self.current_question:
                                if 0 <= selected_index < len(self.current_question["options"]):
                                    self.send_answer(self.current_question["id"], selected_index)
                            
                            # Cancel quiz with ESCAPE
                            elif event.key == pygame.K_ESCAPE:
                                with self.lock:
                                    self.in_question = False
                                    self.current_question = None
                                    self.last_answer_correct = None
                    
                    # Handle game over (any key to exit)
                    elif event.type == pygame.KEYDOWN and self.game_over:
                        running = False

            # Clear screen
            self.screen.fill(self.color_bg)
            
            # Draw appropriate screen based on game state
            if self.in_lobby:
                self.draw_lobby()
            else:
                # Get thread-safe snapshot of game state
                with self.lock:
                    players_snapshot = {pid: info.copy() for pid, info in self.players.items()}
                    mics_snapshot = [mic.copy() for mic in self.microphones]
                    time_left = self.time_left
                    in_question = self.in_question
                    current_question = self.current_question.copy() if self.current_question else None
                    last_answer_correct = self.last_answer_correct
                    game_over_flag = self.game_over

                if not game_over_flag:
                    # Draw microphones
                    for mic in mics_snapshot:
                        if not mic.get("answered"):
                            rect = pygame.Rect(mic["x"] * 20, mic["y"] * 20, 20, 20)
                            pygame.draw.rect(self.screen, self.color_microphone, rect)
                    
                    # Draw players
                    for pid, info in players_snapshot.items():
                        rect = pygame.Rect(info["x"] * 20, info["y"] * 20, 20, 20)
                        color = self.get_player_color(pid)
                        pygame.draw.rect(self.screen, color, rect)
                    
                    # Draw timer
                    if time_left is not None:
                        minutes = time_left // 60
                        seconds = time_left % 60
                        timer_text = f"Time: {minutes:02d}:{seconds:02d}"
                        txt_surface = self.font.render(timer_text, True, self.color_text)
                        self.screen.blit(txt_surface, (20, 20))
                    
                    # Draw scores
                    y_offset = 20
                    score_x = self.map_width * self.GRID_SIZE - 150
                    for pid, info in players_snapshot.items():
                        score_text = f"Player {pid}: {info['score']}"
                        txt_surface = self.font.render(score_text, True, self.color_text)
                        self.screen.blit(txt_surface, (score_x, y_offset))
                        y_offset += 20

                    def wrap_text(text, font, max_width):
                        """Split text into multiple lines that fit within max_width."""
                        words = text.split(' ')
                        lines = []
                        current_line = ""
                        for word in words:
                            test_line = current_line + word + " "
                            if font.size(test_line)[0] <= max_width:
                                current_line = test_line
                            else:
                                lines.append(current_line.strip())
                                current_line = word + " "
                        if current_line:
                            lines.append(current_line.strip())
                        return lines
                    
                    # Draw question if active
                    if in_question and current_question:
                        # Define quiz box dimensions and position (you can adjust these as needed)
                        quiz_box_x = 100
                        quiz_box_y = 100
                        quiz_box_width = 800
                        quiz_box_height = 500

                        # Create an overlay surface with transparency and a border for UI enhancement
                        overlay = pygame.Surface((quiz_box_width, quiz_box_height), pygame.SRCALPHA)
                        overlay.fill((255, 255, 255, 230))  # White with slight transparency
                        pygame.draw.rect(overlay, self.color_text, overlay.get_rect(), 2)  # Black border
                        self.screen.blit(overlay, (quiz_box_x, quiz_box_y))

                        # Set fonts for the question and options
                        font_question = pygame.font.Font(None, 36)
                        font_option = pygame.font.Font(None, 36)

                        # Wrap the question text
                        max_text_width = quiz_box_width - 40  # leave some horizontal padding
                        wrapped_lines = wrap_text(current_question["text"], font_question, max_text_width)
                        line_y = quiz_box_y + 20  # top padding inside the quiz box

                        # Render each wrapped line of the question
                        for line in wrapped_lines:
                            line_surface = font_question.render(line, True, self.color_overlay_text)
                            self.screen.blit(line_surface, (quiz_box_x + 20, line_y))
                            line_y += font_question.get_linesize() + 5  # add small spacing between lines

                        # Add some extra spacing after the question text before options
                        option_y = line_y + 20
                        for idx, option in enumerate(current_question["options"], start=1):
                            option_text = f"{idx}. {option}"
                            option_surface = font_option.render(option_text, True, self.color_overlay_text)
                            self.screen.blit(option_surface, (quiz_box_x + 40, option_y))
                            option_y += font_option.get_linesize() + 15  # spacing between options

                        # Render feedback message if the last answer was incorrect
                        if last_answer_correct is False:
                            feedback_surface = pygame.font.Font(None, 32).render("Incorrect! Please press 'ECS' to exit and trg again!", True, (255, 0, 0))
                            feedback_y = quiz_box_y + quiz_box_height - 60  # bottom padding
                            self.screen.blit(feedback_surface, (quiz_box_x + 40, feedback_y))
                
                else:
                    # Draw game over screen
                    overlay = pygame.Surface(self.screen.get_size())
                    overlay.fill(self.color_bg)
                    self.screen.blit(overlay, (0, 0))
                    
                    # Title
                    title_font = pygame.font.Font(None, 80)
                    title = title_font.render("GAME OVER", True, self.color_text)
                    title_x = (self.screen.get_width() - title.get_width()) // 2
                    self.screen.blit(title, (title_x, 100))
                    
                    # Scores
                    sorted_scores = sorted(players_snapshot.items(), 
                                        key=lambda item: item[1]["score"], reverse=True)
                    y_pos = 180
                    for rank, (pid, info) in enumerate(sorted_scores, start=1):
                        score_text = f"{rank}. Player {pid}: {info['score']}"
                        text = pygame.font.Font(None, 50).render(score_text, True, self.color_text)
                        text_x = (self.screen.get_width() - text.get_width()) // 2
                        self.screen.blit(text, (text_x, y_pos))
                        y_pos += 50
                    
                    # Exit prompt
                    exit_text = pygame.font.Font(None, 40).render(
                        "Press any key to exit", True, self.color_text)
                    exit_x = (self.screen.get_width() - exit_text.get_width()) // 2
                    self.screen.blit(exit_text, (exit_x, y_pos + 50))

            if hasattr(self, 'info_message') and time.time() - self.info_message_time < 3:
                msg_surface = self.font.render(self.info_message, True, (255, 0, 0))
                self.screen.blit(msg_surface, (self.screen.get_width()//2 - msg_surface.get_width()//2, 10))    
            pygame.display.flip()
            clock.tick(60)

        pygame.quit()

if __name__ == "__main__":
    # Parse Arguments
    ip_address = args.ip_address
    port = int(args.port)

    # Change host to the server's IP address if needed.
    client = Client(host=ip_address, port=port)
    client.connect_to_server()
    client.run()
