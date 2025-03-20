import pygame
import json

class GameUI:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height
        self.quiz_active = False
        self.current_question = None
        self.load_questions()
    
    def load_questions(self):
        with open("quizQuestions.json", "r") as file:
            self.questions = json.load(file)["Questions"]
    
    def start_quiz(self, question):
        self.quiz_active = True
        self.current_question = question
    
    def handle_event(self, event, player):
        if self.quiz_active and event.type == pygame.MOUSEBUTTONDOWN:
            x, y = event.pos
            # Check if clicked on an option (simplified)
            self.quiz_active = False  # Close quiz after click (for now)
    
    def draw(self):
        if self.quiz_active and self.current_question:
            pygame.draw.rect(self.screen, (200, 200, 200), (600, 300, 800, 400))
            font = pygame.font.Font(None, 36)
            question_text = font.render(self.current_question["question"], True, (0, 0, 0))
            self.screen.blit(question_text, (620, 320))

            for i, option in enumerate(self.current_question["options"]):
                option_text = font.render(f"{i+1}. {option}", True, (0, 0, 0))
                self.screen.blit(option_text, (620, 360 + i * 40))