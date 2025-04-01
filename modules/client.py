import pygame
import socket
import threading
import time
from network import send_data, recv_data
from helper import args

#setting player color 
PLAYER_COLORS = {
    1: (255, 0, 0),    # Red
    2: (0, 255, 0),    # Green
    3: (0, 0, 255),    # Blue
    4: (255, 255, 0)   # Yellow
}


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

        # Thread synchronization lock for state
        self.lock = threading.Lock()

        # Initialize Pygame for rendering
        pygame.init()
        # Calculate game area size
        game_area_width = self.map_width * self.GRID_SIZE
        game_area_height = self.map_height * self.GRID_SIZE
        # set up the window size 
        self.screen = pygame.display.set_mode((game_area_width, game_area_height))
        
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

    def get_player_color(self, player_id):
        """=Return a unique color for each player ID."""
        return PLAYER_COLORS.get(player_id, (200, 200, 200))  # Gray fallback

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
                    color = self.get_player_color(pid) # get the user color 
                    pygame.draw.rect(self.screen, color, rect)
                # Draw timer (if available)

                if time_left is not None:
                    minutes = time_left // 60
                    seconds = time_left % 60
                    timer_text = f"Time: {minutes:02d}:{seconds:02d}"
                    txt_surface = self.font.render(timer_text, True, self.color_text)
                    self.screen.blit(txt_surface, (20, 20))

                # Draw scores for each player
                y_offset = 20
                score_x = self.map_width * self.GRID_SIZE - 150
                for pid, info in players_snapshot.items():
                    score_text = f"Player {pid}: {info['score']}"
                    txt_surface = self.font.render(score_text, True, self.color_text)
                    # Display scores on the right side
                    self.screen.blit(txt_surface, (score_x, y_offset))
                    y_offset += 20
                # If a quiz question is active, draw the question overlay

                ## quiz box 
                # quiz_box_width = 1000
                # quiz_box_height = 600
                # quiz_box_x = (1000 - quiz_box_width) // 2  # Centered horizontally
                # quiz_box_y = (800 - quiz_box_height) // 2  # Centered vertically

                quiz_box_x = 100
                quiz_box_y = 100
                quiz_box_width = 800
                quiz_box_height = 500

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

                if in_question and current_question:
                    # # Draw semi-transparent overlay background( question background)
                    # pygame.draw.rect(self.screen, (255, 255, 255), (quiz_box_x, quiz_box_y, quiz_box_width, quiz_box_height))
                    # # overlay.fill((255, 255, 255, 230))  # white with slight transparency
                    # # self.screen.blit(overlay, (quiz_box_x, quiz_box_y))
                    # # Render question text
                    # question_text = current_question["text"]
                    # question_surface = pygame.font.Font(None, 36).render(question_text, True, self.color_overlay_text)
                    # question_x = quiz_box_x + 20  # question Padding from the left of  box 
                    # question_y = quiz_box_y + 30  # question Padding from the top of box 
                    # self.screen.blit(question_surface, (quiz_box_x, quiz_box_y))
                    # # Render multiple-choice options
                    # for idx, option in enumerate(current_question["options"], start=1):
                    #     option_text = f"{idx}. {option}"
                    #     option_surface = pygame.font.Font(None, 36).render(option_text, True, self.color_overlay_text)
                    #     option_x = quiz_box_x + 40  # Slight padding from the left 
                    #     option_y = quiz_box_y + 50 + (idx * 60)  # Even spacing
                    #     self.screen.blit(option_surface, (option_x, option_y))

                    # # Render "Incorrect! Try again." message below the options if the answer was wrong
                    # if last_answer_correct is False:
                    #     feedback_surface = pygame.font.Font(None,32).render(" Incorrect! Try again.", True, (255, 0, 0))
                    #     feedback_x = quiz_box_x + 40
                    #     feedback_y = quiz_box_y + quiz_box_height - 60  # Place at the bottom
                    #     self.screen.blit(feedback_surface, (feedback_x, feedback_y))

                    # Create an overlay surface with transparency and a border for UI enhancement
                    overlay = pygame.Surface((quiz_box_width, quiz_box_height), pygame.SRCALPHA)
                    overlay.fill((255, 255, 255, 230))  # White with slight transparency
                    pygame.draw.rect(overlay, (0, 0, 0), overlay.get_rect(), 2)  # Black border
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
                        feedback_surface = pygame.font.Font(None, 32).render("Incorrect! Try again.", True, (255, 0, 0))
                        feedback_y = quiz_box_y + quiz_box_height - 60  # bottom padding
                        self.screen.blit(feedback_surface, (quiz_box_x + 40, feedback_y))
            else:
                # Game over: display final scores
                overlay = pygame.Surface(self.screen.get_size())
                overlay.fill(self.color_bg)  # Background color
                self.screen.blit(overlay, (0, 0))

                font_title = pygame.font.Font(None, 80)  # Bigger font for title
                title_surface = font_title.render("GAME OVER", True, self.color_text)
                title_x = (1000 - title_surface.get_width()) // 2  # Center horizontally
                title_y = 100  # Higher up on the screen
                self.screen.blit(title_surface, (title_x, title_y))

                sorted_scores = sorted(players_snapshot.items(), key=lambda item: item[1]["score"], reverse=True)

                font_score = pygame.font.Font(None, 50)  # Larger font for scores
                y_pos = title_y + 80  # Start below the title

                for rank, (pid, info) in enumerate(sorted_scores, start=1):
                    score_line = f"{rank}. Player {pid} - Score: {info['score']}"
                    score_surface = font_score.render(score_line, True, self.color_text)
                    
                    # Center score text horizontally
                    score_x = (1000 - score_surface.get_width()) // 2
                    self.screen.blit(score_surface, (score_x, y_pos))
                        
                    y_pos += 50  # Increase spacing

                font_exit = pygame.font.Font(None, 40)
                exit_surface = font_exit.render("Press any key to exit", True, self.color_text)

                exit_x = (1000 - exit_surface.get_width()) // 2  # Center horizontally
                exit_y = y_pos + 50  # Below the last score
                self.screen.blit(exit_surface, (exit_x, exit_y))


            pygame.display.flip()
            clock.tick(30)  # Cap the frame rate to 30 FPS

        # Clean up Pygame on exit
        pygame.quit()


if __name__ == "__main__":
    # Parse Arguments
    ip_address = args.ip_address
    port = int(args.port)

    # Change host to the server's IP address if needed.
    client = Client(host=ip_address, port=port)
    client.connect_to_server()
    client.run()
