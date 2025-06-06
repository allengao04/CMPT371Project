import socket
import threading
import time
import random
import json
import pygame
from network import send_data, recv_data
from game import Microphone, Player, PLAYER_COLORS
from helper import args

'''
    Server side code that is responsible for:
        - handle clients when they try to connect with the server
        - communicate with the client through TCP socket and custom messaging scheme
        - server will initialize a client object as well
        - draw lobby screen and game play screen
        - reading quiz questions from quizQuestions.json and handle the creation of the quiz objects
        - handling cocurrency between 'microphone' objects
'''


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
        self.countdown = None  # For lobby countdown display

        # Game state data structures
        self.players = {}      # {player_id: Player}
        self.clients = {}      # {player_id: socket}
        self.microphones = []  # List of Microphone objects

        # Define the game world (grid size and obstacles)
        self.GRID_SIZE = 20
        self.map_width = 50
        self.map_height = 40
        self.obstacles = set()
        for y in range(5, 10):
            self.obstacles.add((15, y))

        # Read quiz bank from file and randomly generate 10 quiz objects
        try:
            with open("./quizQuestions.json", "r") as f:
                quiz_data = json.load(f)
            all_questions = quiz_data.get("Questions", [])
            # Convert the correct_index from string to int for each question.
            for q in all_questions:
                q["correct_index"] = int(q["correct_index"])
            num_quiz = min(10, len(all_questions))
            random.shuffle(all_questions)
            selected_questions = all_questions[:num_quiz]
            self.unused_questions = all_questions[num_quiz:]  # remaining unique questions

            self.microphones = []
            mic_id = 1
            for question in selected_questions:
                # Generate a random valid position
                while True:
                    x = random.randint(0, self.map_width - 1)
                    y = random.randint(0, self.map_height - 1)
                    if (x, y) not in self.obstacles:
                        break
                self.microphones.append(Microphone(mic_id, x, y, question["question"], question["options"], question["correct_index"]))
                mic_id += 1
        except Exception as e:
            print(f"Error loading quiz bank: {e}")
            # set empty questions and objects when error
            self.microphones = []
            self.unused_questions = []

        # Synchronization lock for thread-safe state updates
        self.lock = threading.Lock()

        # Set up the server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"Server listening on {self.host}:{self.port}")

        # Pygame initialization for lobby and game display
        pygame.init()
        # Match client window size: 1000 x 800 (50*20 x 40*20)
        self.lobby_screen = pygame.display.set_mode((1000, 800))
        pygame.display.set_caption("Server Lobby")
        self.font = pygame.font.SysFont(None, 24)

        # Colors for quiz overlay
        self.color_overlay_bg = (255, 255, 255)
        self.color_overlay_text = (0, 0, 0)

        # Define some colors for drawing
        self.color_bg = (200, 200, 200)         # background color
        self.color_player = (0, 0, 255)         # local player color
        self.color_other_player = (0, 255, 0)   # other players color
        self.color_microphone = (255, 165, 0)   # microphone object color (orange)
        self.color_text = (0, 0, 0)            # text color (black)
        self.color_overlay_bg = (255, 255, 255) # overlay background (white)
        self.color_overlay_text = (0, 0, 0)    # overlay text color (black)

        # Additional attributes for quiz state (for server player)
        self.in_question = False
        self.current_question = None   # Format: {"id": mic_id, "text": question, "options": [...]}
        self.last_answer_correct = None  # None, True, or False

        # Define the server-controlled player (use player_id 1)
        self.server_player_id = 1
        spawn_x, spawn_y = self.find_spawn_position(self.server_player_id)
        self.players[self.server_player_id] = Player(self.server_player_id, spawn_x, spawn_y)
        self.players[self.server_player_id].ready = True  # Server is auto-ready

    def draw_game(self):
        self.lobby_screen.fill((200, 200, 200))  # Light gray background

        if not self.game_over:
            # Draw microphones
            for mic in self.microphones:
                if not mic.answered:
                    rect = pygame.Rect(mic.x * 20, mic.y * 20, 20, 20)
                    pygame.draw.rect(self.lobby_screen, self.color_microphone, rect)
            
            # Draw players
            for pid, info in self.players.items():
                rect = pygame.Rect(info.x * 20, info.y * 20, 20, 20)
                color = self.get_player_color(pid)
                pygame.draw.rect(self.lobby_screen, color, rect)
            
            # Draw timer
            if self.start_time:
                elapsed = int(time.time() - self.start_time)
                time_left = max(0, self.time_limit - elapsed)
                timer_text = f"Time: {time_left // 60:02d}:{time_left % 60:02d}"
                txt_surface = self.font.render(timer_text, True, self.color_text)
                self.lobby_screen.blit(txt_surface, (20, 20))
            
            # Draw scores
            y_offset = 20
            score_x = self.map_width * self.GRID_SIZE - 150
            for pid, info in self.players.items():
                score_text = f"Player {pid}: {info.score}"
                txt_surface = self.font.render(score_text, True, self.color_text)
                self.lobby_screen.blit(txt_surface, (score_x, y_offset))
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
            if self.in_question and self.current_question:
                # Define quiz box dimensions and position (you can adjust these as needed)
                quiz_box_x = 100
                quiz_box_y = 100
                quiz_box_width = 800
                quiz_box_height = 500

                # Create an overlay surface with transparency and a border for UI enhancement
                overlay = pygame.Surface((quiz_box_width, quiz_box_height), pygame.SRCALPHA)
                overlay.fill((255, 255, 255, 230))  # White with slight transparency
                pygame.draw.rect(overlay, self.color_text, overlay.get_rect(), 2)  # Black border
                self.lobby_screen.blit(overlay, (quiz_box_x, quiz_box_y))

                # Set fonts for the question and options
                font_question = pygame.font.Font(None, 36)
                font_option = pygame.font.Font(None, 36)

                # Wrap the question text
                max_text_width = quiz_box_width - 40  # leave some horizontal padding
                wrapped_lines = wrap_text(self.current_question["text"], font_question, max_text_width)
                line_y = quiz_box_y + 20  # top padding inside the quiz box

                # Render each wrapped line of the question
                for line in wrapped_lines:
                    line_surface = font_question.render(line, True, self.color_overlay_text)
                    self.lobby_screen.blit(line_surface, (quiz_box_x + 20, line_y))
                    line_y += font_question.get_linesize() + 5  # add small spacing between lines

                # Add some extra spacing after the question text before options
                option_y = line_y + 20
                for idx, option in enumerate(self.current_question["options"], start=1):
                    option_text = f"{idx}. {option}"
                    option_surface = font_option.render(option_text, True, self.color_overlay_text)
                    self.lobby_screen.blit(option_surface, (quiz_box_x + 40, option_y))
                    option_y += font_option.get_linesize() + 15  # spacing between options

                # Render feedback message if the last answer was incorrect
                if self.last_answer_correct is False:
                    feedback_surface = pygame.font.Font(None, 32).render("Incorrect! Please press 'ECS' to exit and trg again!", True, (255, 0, 0))
                    feedback_y = quiz_box_y + quiz_box_height - 60  # bottom padding
                    self.lobby_screen.blit(feedback_surface, (quiz_box_x + 40, feedback_y))

        else:
            # Draw game over screen
            overlay = pygame.Surface(self.lobby_screen.get_size())
            overlay.fill(self.color_bg)
            self.lobby_screen.blit(overlay, (0, 0))
            
            # Title
            title_font = pygame.font.Font(None, 80)
            title = title_font.render("GAME OVER", True, self.color_text)
            title_x = (self.lobby_screen.get_width() - title.get_width()) // 2
            self.lobby_screen.blit(title, (title_x, 100))
            
            # Scores
            sorted_scores = sorted(self.players.items(), 
                                key=lambda item: item[1].score, reverse=True)
            y_pos = 180
            for rank, (pid, info) in enumerate(sorted_scores, start=1):
                score_text = f"{rank}. Player {pid}: {info.score}"
                text = pygame.font.Font(None, 50).render(score_text, True, self.color_text)
                text_x = (self.lobby_screen.get_width() - text.get_width()) // 2
                self.lobby_screen.blit(text, (text_x, y_pos))
                y_pos += 50
            
            # Exit prompt
            exit_text = pygame.font.Font(None, 40).render(
                "Press any key to exit", True, self.color_text)
            exit_x = (self.lobby_screen.get_width() - exit_text.get_width()) // 2
            self.lobby_screen.blit(exit_text, (exit_x, y_pos + 50))

        if hasattr(self, 'info_message') and time.time() - self.info_message_time < 3:
            msg_surface = self.font.render(self.info_message, True, (255, 0, 0))
            self.lobby_screen.blit(msg_surface, (self.lobby_screen.get_width()//2 - msg_surface.get_width()//2, 10))    

        pygame.display.flip()

    def move_player(self, player, direction):
        """Helper method for moving a player in the game loop."""
        new_x, new_y = player.x, player.y
        if direction == "up":
            new_y -= 1
        elif direction == "down":
            new_y += 1
        elif direction == "left":
            new_x -= 1
        elif direction == "right":
            new_x += 1
        if 0 <= new_x < self.map_width and 0 <= new_y < self.map_height:
            if (new_x, new_y) not in self.obstacles:
                player.x, player.y = new_x, new_y

    def server_interact(self, player):
        """When the server interacts with a mic, enter quiz mode."""
        for mic in self.microphones:
            if mic.x == player.x and mic.y == player.y and not mic.answered:
                
                if mic.cooldowns.get(self.server_player_id, 0) > time.time():
                    self.info_message = "Please wait 3 seconds before trying again."
                    self.info_message_time = time.time()
                    return

                if mic.lock.acquire(blocking=False):
                    if mic.active_by is None:
                        mic.active_by = player.id
                        self.in_question = True
                        self.current_question = {
                            "id": mic.id,
                            "text": mic.question,
                            "options": mic.options
                        }
                        self.last_answer_correct = None
                    else:
                        print("Mic is in use.")
                return

    def start(self):
        """Main server loop handling lobby and game phases."""
        accept_thread = threading.Thread(target=self.accept_clients, daemon=True)
        accept_thread.start()
        self.run_lobby()  # Lobby phase

        # Main game loop after lobby
        clock = pygame.time.Clock()
        try:
            while not self.game_over:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.stop()
                        return
                    elif event.type == pygame.KEYDOWN:
                        with self.lock:
                            # In quiz mode
                            if self.in_question:
                                # if last answer was wrong, do not process number keys until ESC is pressed.
                                if self.last_answer_correct is False:
                                    if event.key == pygame.K_ESCAPE:
                                        # Cancel quiz mode and allow new attempts (unlock mic)
                                        mic_id = self.current_question["id"]
                                        mic = next((m for m in self.microphones if m.id == mic_id), None)
                                        if mic:
                                            mic.active_by = None
                                            try:
                                                mic.lock.release()
                                            except RuntimeError:
                                                pass
                                            mic.cooldowns[self.server_player_id] = time.time() + 3
                                        self.in_question = False
                                        self.current_question = None
                                        self.last_answer_correct = None
                                        self.broadcast(self.build_state_message())
                                    continue  # Ignore other keys until ESC is pressed
                                selected_index = None
                                if event.key == pygame.K_1:
                                    selected_index = 0
                                elif event.key == pygame.K_2:
                                    selected_index = 1
                                elif event.key == pygame.K_3:
                                    selected_index = 2
                                elif event.key == pygame.K_4:
                                    selected_index = 3
                                elif event.key == pygame.K_ESCAPE: # When 'ECS' is pressed, apply 3 second cooldown
                                    if self.current_question:
                                        mic_id = self.current_question["id"]
                                        mic = next((m for m in self.microphones if m.id == mic_id), None)
                                        if mic:
                                            mic.active_by = None
                                            try:
                                                mic.lock.release()
                                            except RuntimeError:
                                                pass
                                            mic.cooldowns[self.server_player_id] = time.time() + 3 # 3 second cooldown
                                    # Cancel quiz mode if desired
                                    self.in_question = False
                                    self.current_question = None
                                    self.last_answer_correct = None
                                    self.broadcast(self.build_state_message())
                                    continue

                                # Check if key pressed equal the correct answer
                                if selected_index is not None and self.current_question:
                                    mic_id = self.current_question["id"]
                                    mic = next((m for m in self.microphones if m.id == mic_id), None)
                                    if mic:
                                        # Correct answer
                                        if selected_index == mic.correct_index:
                                            mic.answered = True
                                            mic.active_by = None
                                            self.in_question = False
                                            self.current_question = None
                                            self.players[self.server_player_id].score += 1
                                            self.last_answer_correct = True
                                            print("Server answered correctly!")

                                        # Incorrect answer and release the lock from the object  
                                        else:
                                            # On wrong answer, show feedback and keep the quiz overlay active.
                                            self.last_answer_correct = False
                                            print("Server answered incorrectly. Press ESC to cancel.")
                                            # Do not cancel the quiz overlay automatically; clients can now see that the mic is free.
                                            mic.active_by = None
                                            try:
                                                mic.lock.release()
                                            except RuntimeError:
                                                pass
                                            mic.cooldowns[self.server_player_id] = time.time() + 3
                                        self.broadcast(self.build_state_message())

                            # Action not in quiz mode 
                            else:
                                # Normal movement and interact
                                player = self.players.get(self.server_player_id)
                                if event.key in (pygame.K_w, pygame.K_UP):
                                    self.move_player(player, "up")
                                elif event.key in (pygame.K_s, pygame.K_DOWN):
                                    self.move_player(player, "down")
                                elif event.key in (pygame.K_a, pygame.K_LEFT):
                                    self.move_player(player, "left")
                                elif event.key in (pygame.K_d, pygame.K_RIGHT):
                                    self.move_player(player, "right")
                                elif event.key in (pygame.K_e, pygame.K_SPACE):
                                    self.server_interact(player)
                                elif self.game_over:
                                    self.stop()
                                    return
                with self.lock:
                    if self.game_started and not self.game_over:
                        current_time = time.time()
                        elapsed = int(current_time - self.start_time)
                        time_left = max(0, self.time_limit - elapsed)
                        if time_left <= 0:
                            self.game_over = True
                        state_msg = self.build_state_message()
                        self.broadcast(state_msg)
                self.draw_game()
                clock.tick(60)
            # Wait for key press at game over screen
            while self.game_over:
                for event in pygame.event.get():
                    if event.type == pygame.KEYDOWN:
                        self.stop()
                        return
                self.draw_game()
                clock.tick(60)
        except KeyboardInterrupt:
            print("Server shutting down (KeyboardInterrupt).")
        finally:
            self.stop()
            pygame.quit()

    def accept_clients(self):
        """Accept incoming client connections and initialize players."""
        next_player_id = 2 # Since server is player 1
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
                # Initialize configuration for client
                player_id = next_player_id
                spawn_x, spawn_y = self.find_spawn_position(player_id)
                next_player_id += 1
                new_player = Player(player_id, spawn_x, spawn_y)
                self.players[player_id] = new_player
                self.clients[player_id] = client_sock
                print(f"Player {player_id} connected from {addr}, spawn at ({spawn_x},{spawn_y})")
                # Send initial game state to client
                init_msg = {
                    "type": "init",
                    "player_id": player_id,
                    "players": {pid: {"x": p.x, "y": p.y, "score": p.score} for pid, p in self.players.items()},
                    "microphones": [{"id": m.id, "x": m.x, "y": m.y, "answered": m.answered} for m in self.microphones],
                    "time_left": self.time_limit if not self.start_time else max(0, self.time_limit - int(time.time() - self.start_time))
                }
                send_data(client_sock, init_msg)
                
                # Broadcast updated lobby state
                self.broadcast_lobby_update()
            client_thread = threading.Thread(target=self.handle_client, args=(client_sock, player_id), daemon=True)
            client_thread.start()

        print("Stopped accepting new clients.")

    # Helper function to find spawn location base on player id
    def find_spawn_position(self, player_id):
        """Assign players to predefined corners of the map."""
        '''
            Player 1: top-left corner
            Player 2: top-right corner
            Player 3: bottom-left corner
            Player 4: bottom-right corner
        '''
        grid_width = self.map_width
        grid_height = self.map_height
        corner_positions = {
            1: (0, 2),
            2: (grid_width - 1, 2),
            3: (0, grid_height - 1),
            4: (grid_width - 1, grid_height - 1)
        }
        return corner_positions.get(player_id, (0, 0))


    def broadcast_lobby_update(self):
        """Send current lobby state to all players."""
        msg = {
            "type": "lobby_state",
            "players": {pid: p.ready for pid, p in self.players.items()}
        }
        self.broadcast(msg)

    def get_player_color(self, player_id):
        """=Return a unique color for each player ID."""
        return PLAYER_COLORS.get(player_id, (200, 200, 200))  # Gray fallback

    def run_lobby(self):
        """Pygame-based lobby loop handling player readiness."""
        clock = pygame.time.Clock()
        while self.lobby_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.stop()
                    return
            # Draw Lobby and display IP address and Port number
            self.lobby_screen.fill((30, 30, 60))
            title = self.font.render("Server Lobby - Waiting for Players", True, (255, 255, 255))
            server_ip = self.font.render(f"Server IP: {self.host}", True, (255, 255, 255))
            server_port = self.font.render(f"Server Port: {self.port}", True, (255, 255, 255))
            title_rect = title.get_rect(center=(self.lobby_screen.get_width() // 2, 80))
            ip_rect = server_ip.get_rect(center=(self.lobby_screen.get_width() // 2, 50))
            port_rect = server_port.get_rect(center=(self.lobby_screen.get_width() // 2, 20))
            self.lobby_screen.blit(title, title_rect)
            self.lobby_screen.blit(server_ip, ip_rect)
            self.lobby_screen.blit(server_port, port_rect)
            y = 150

            # Draw each player's Ready Status
            for pid, player in self.players.items():
                status = "Ready" if player.ready else "Waiting"
                color = (0, 255, 0) if player.ready else (255, 0, 0)
                text = self.font.render(f"Player {pid}: {status}", True, color)
                text_rect = text.get_rect(center=(self.lobby_screen.get_width() // 2, y))
                self.lobby_screen.blit(text, text_rect)
                y += 40
            pygame.display.flip()
            clock.tick(60)

    def start_game_countdown(self):
        """10-second countdown before game starts"""
        for i in range(5, 0, -1):
            self.countdown = i
            self.broadcast({"type": "countdown", "time": i})
            time.sleep(1)
        self.lobby_active = False
        self.broadcast({"type": "game_start"})
        self.start_time = time.time()
        self.game_started = True

    def handle_client(self, client_socket, player_id):
        """Handle messages from a connected client."""
        while not self.game_over:
            data = recv_data(client_socket)
            if data is None:
                break
            
            msg_type = data.get("type")
            if msg_type == "player_ready" and self.lobby_active:
                with self.lock:
                    player = self.players.get(player_id)
                    if player:
                        player.ready = not player.ready
                        self.broadcast_lobby_update()
                        if all(p.ready for p in self.players.values()):
                            self.start_game_countdown()
                            
            elif msg_type == "move" and not self.lobby_active:
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
                        if 0 <= new_x < self.map_width and 0 <= new_y < self.map_height:
                            if (new_x, new_y) not in self.obstacles:
                                player.x = new_x
                                player.y = new_y
                with self.lock:
                    state_msg = self.build_state_message()
                self.broadcast(state_msg)
                
            elif msg_type == "interact" and not self.lobby_active:
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
                        # Check if the player is on cooldown for this mic:
                        if mic_obj.cooldowns.get(player_id, 0) > time.time():
                            info_msg = {"type": "info", "message": "Please wait 3 seconds before trying again."}
                            send_data(self.clients[player_id], info_msg)
                            continue

                        # Try to acquire the lock:
                        if mic_obj.lock.acquire(blocking=False):
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
                            info_msg = {"type": "info", "message": "Microphone is currently in use by another player."}
                            send_data(self.clients[player_id], info_msg)

            elif msg_type == "answer" and not self.lobby_active:
                mic_id = data.get("mic_id")
                answer_idx = data.get("answer")

                with self.lock:
                    mic_obj = next((m for m in self.microphones if m.id == mic_id), None)
                    if not mic_obj or mic_obj.answered:
                        continue
                    if mic_obj.active_by != player_id:
                        continue

                    if answer_idx == mic_obj.correct_index:
                        # Correct answer branch
                        mic_obj.answered = True
                        mic_obj.active_by = None
                        mic_obj.lock.release()

                        # update player's score
                        if player_id in self.players:
                            self.players[player_id].score += 1

                        state_msg = self.build_state_message()

                        # Check if all current microphones are answered and no unused questions remain
                        all_answered = all(m.answered for m in self.microphones)
                        if all_answered and not self.unused_questions:
                            self.game_over = True
                        result_msg = {"type": "answer_result", "correct": True}
                        send_data(self.clients[player_id], result_msg)

                        # Spawn a new quiz object if available and if one was answered correctly
                        if self.unused_questions:
                            new_question = self.unused_questions.pop(0)
                            while True:
                                new_x = random.randint(0, self.map_width - 1)
                                new_y = random.randint(0, self.map_height - 1)
                                if (new_x, new_y) not in self.obstacles:
                                    break
                            new_mic_id = max(m.id for m in self.microphones) + 1 if self.microphones else 1
                            new_mic = Microphone(new_mic_id, new_x, new_y, new_question["question"], new_question["options"], new_question["correct_index"])
                            self.microphones.append(new_mic)
                    else: # Incorrect answer: release the microphone for others.
                        mic_obj.active_by = None
                        mic_obj.cooldowns[player_id] = time.time() + 3
                        mic_obj.lock.release()
                        send_data(self.clients[player_id], {"type": "answer_result", "correct": False})
                if mic_obj and mic_obj.answered:
                    self.broadcast(state_msg)
                    if self.game_over:
                        self.broadcast_game_over()
                        break

            elif msg_type == "cancel_quiz" and not self.lobby_active:
                mic_id = data.get("mic_id")
                if mic_id is None:
                    # Optionally log or send back an error
                    continue
                with self.lock:
                    mic_obj = next((m for m in self.microphones if m.id == mic_id), None)
                    if mic_obj and mic_obj.active_by == player_id:
                        mic_obj.active_by = None
                        try:
                            mic_obj.lock.release()
                        except RuntimeError:
                            pass
                        mic_obj.cooldowns[player_id] = time.time() + 3
                        info_msg = {"type": "info", "message": "Quiz cancelled. You may try again."}
                        send_data(self.clients[player_id], info_msg)

        # Cleanup on disconnect
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
                            pass
                if not self.game_over:
                    state_msg = self.build_state_message()
                    self.broadcast(state_msg)
                    
        client_socket.close()

    def build_state_message(self):
        """Construct game state message for clients."""
        time_left = max(0, self.time_limit - int(time.time() - self.start_time)) if self.start_time else self.time_limit
        players_data = {pid: {"x": p.x, "y": p.y, "score": p.score} for pid, p in self.players.items()}
        mics_data = [{"id": m.id, "x": m.x, "y": m.y, "answered": m.answered} for m in self.microphones]
        msg = {
            "type": "state",
            "players": players_data,
            "microphones": mics_data,
            "time_left": time_left,
            "game_over": self.game_over
        }
        return msg

    def broadcast(self, data, exclude_id=None):
        """Send data to all connected clients."""
        for pid, sock in list(self.clients.items()):
            if exclude_id is not None and pid == exclude_id:
                continue
            try:
                send_data(sock, data)
            except Exception as e:
                print(f"Error sending to Player {pid}: {e}")

    def broadcast_game_over(self):
        """Notify all clients the game has ended with final scores."""
        players_data = {pid: {"x": p.x, "y": p.y, "score": p.score} for pid, p in self.players.items()}
        self.broadcast({"type": "game_over", "players": players_data})

    def stop(self):
        """Shutdown server and cleanup resources."""
        self.game_over = True
        for pid, sock in self.clients.items():
            sock.close()
        self.server_socket.close()
        print("Server stopped.")

if __name__ == "__main__":
    # Parse Arugments
    ip_address = args.ip_address
    port = int(args.port)
    time_limit = int(args.time_limit)

    # Start server
    server = Server(host=ip_address, port=port, time_limit=time_limit)
    server.start()
