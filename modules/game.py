import pygame
import random

PLAYER_SPEED = 10 # move 10 pixelx per movement

class Player:
    def __init__(self, x, y, size, color):
        self.x = x
        self.y = y
        self.size = size
        self.color = color
        self.speed = PLAYER_SPEED  # Move one tile at a time
    
    def move(self, keys, obstacles):
        new_x, new_y = self.x, self.y
        if keys[pygame.K_w]:
            new_y -= self.speed
        if keys[pygame.K_s]:
            new_y += self.speed
        if keys[pygame.K_a]:
            new_x -= self.speed
        if keys[pygame.K_d]:
            new_x += self.speed
        
        if (new_x, new_y) not in obstacles:
            self.x, self.y = new_x, new_y
    
    def draw(self, screen):
        pygame.draw.circle(screen, self.color, (self.x + self.size // 2, self.y + self.size // 2), self.size // 2)

class GameWorld:
    def __init__(self, width, height, tile_size):
        self.width = width
        self.height = height
        self.tile_size = tile_size
        self.obstacles = self.generate_obstacles()
    
    def generate_obstacles(self):
        obstacles = set()
        for _ in range(50):  # 50 random obstacles
            x = random.randint(0, self.width // self.tile_size - 1) * self.tile_size
            y = random.randint(0, self.height // self.tile_size - 1) * self.tile_size
            obstacles.add((x, y))
        return obstacles
    
    def draw(self, screen):
        for x, y in self.obstacles:
            pygame.draw.rect(screen, (150, 75, 0), (x, y, self.tile_size, self.tile_size))