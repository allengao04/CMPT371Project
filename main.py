import pygame
import random
from modules.ui import GameUI
from modules.game import GameWorld, Player

# Constants
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
TILE_SIZE = 40  # Grid size
FPS = 60  # Variable frame rate

# Initialize Pygame
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Multiplayer Quiz Game")
clock = pygame.time.Clock()

def main():
    running = True
    game_world = GameWorld(SCREEN_WIDTH, SCREEN_HEIGHT, TILE_SIZE)
    game_ui = GameUI(screen, SCREEN_WIDTH, SCREEN_HEIGHT)
    player = Player(random.randint(0, SCREEN_WIDTH // TILE_SIZE) * TILE_SIZE,
                    random.randint(0, SCREEN_HEIGHT // TILE_SIZE) * TILE_SIZE, TILE_SIZE, (0, 255, 0))
    
    while running:
        screen.fill((50, 50, 50))  # Background color
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            game_ui.handle_event(event, player)
        
        # Update game state
        player.move(pygame.key.get_pressed(), game_world.obstacles)
        
        # Draw everything
        game_world.draw(screen)
        player.draw(screen)
        game_ui.draw()
        
        pygame.display.flip()
        clock.tick(FPS)
    
    pygame.quit()

if __name__ == "__main__":
    main()