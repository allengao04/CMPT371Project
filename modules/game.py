import threading

# Setting player colors
PLAYER_COLORS = {
    1: (255, 0, 0),    # Red
    2: (0, 255, 0),    # Green
    3: (0, 0, 255),    # Blue
    4: (255, 255, 0)   # Yellow
}

class Player:
    def __init__(self, pid, x, y):
        self.id = pid
        self.x = x
        self.y = y
        self.score = 0
        self.ready = False  # For lobby readiness
    
    
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
        self.lock = threading.RLock()  # Dedicated lock for concurrency control
        self.cooldowns = {}  # Dict: {player_id: timestamp_until_accessible}