import sys
import io
import socket
import logging
import json
import base64
import pygame
import time

# --- Constants ---

# Game window
WIDTH, HEIGHT = 800, 600
FPS = 60

# Sizes
CHARACTER_SIZE = (48, 48)
GEM_SIZE = (20, 20)
HAZARD_DEFAULT_SIZE = (100, 50)
EXIT_SIZE = (80, 80)
WALL_UNIT_SIZE = 20

# Physics
GRAVITY = 0.5
JUMP_STRENGTH = -10
TERMINAL_VELOCITY = 10

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
GREY = (150, 150, 150)
ORANGE = (255, 165, 0)
CYAN = (0, 255, 255)
WIN_GREEN = (0, 200, 0)

# --- Pygame Initialization ---

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Black vs. White")
clock = pygame.time.Clock()

# --- Fonts ---

font_large = pygame.font.Font(None, 74)
font_medium = pygame.font.Font(None, 36)
font_small = pygame.font.Font(None, 24)
font_tiny = pygame.font.Font(None, 18)

# --- Logging ---

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Networking ---

class ClientInterface:
    """Handles communication with the game server."""

    def __init__(self):
        self.server_address = ('127.0.0.1', 55554)

    def send_command(self, command_str=""):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(self.server_address)
            sock.sendall((command_str + "\r\n\r\n").encode('utf-8'))
            data_received = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk: break
                data_received += chunk
                if b"\r\n\r\n" in data_received: break
            decoded_data = data_received.decode('utf-8').strip()
            if decoded_data: return json.loads(decoded_data)
            else: return {"status": "ERROR", "message": "Empty response"}
        except ConnectionRefusedError:
            return {"status": "ERROR", "message": "Connection refused. Is the server running?"}
        except json.JSONDecodeError as e:
            return {"status": "ERROR", "message": f"Invalid JSON: {e}"}
        except Exception as e:
            return {"status": "ERROR", "message": f"Network error: {e}"}
        finally:
            sock.close()

    def register_player(self, color): return self.send_command(f"register_player {color}")
    def set_player_state(self, player_id, x, y, lives): return self.send_command(f"set_player_state {player_id} {x} {y} {lives}")
    def get_game_state(self): return self.send_command("get_game_state")
    def get_player_info(self, player_id): return self.send_command(f"get_player_info {player_id}")
    def collect_gem(self, player_id, gem_id): return self.send_command(f"collect_gem {player_id} {gem_id}")
    def check_hazard_collision(self, player_id, hazard_id): return self.send_command(f"check_hazard_collision {player_id} {hazard_id}")
    def player_at_exit(self, player_id): return self.send_command(f"player_at_exit {player_id}")
    def reset_game(self): return self.send_command(f"reset_game")


# --- Game Entities ---

class PlayerCharacter:
    def __init__(self, id, is_local_player=False, initial_color_choice=None):
        self.id = id
        self.is_local_player = is_local_player
        self.color_type = initial_color_choice
        self.x, self.y, self.speed = 0, 0, 5
        self.gems_collected, self.lives, self.at_exit = 0, 1, False
        self.image = None
        self.rect = pygame.Rect(self.x, self.y, CHARACTER_SIZE[0], CHARACTER_SIZE[1])
        self.vy, self.on_ground = 0, False
        
        if self.is_local_player:
            self.client_interface = ClientInterface()
            self._fetch_image()
        else:
            self._set_default_image()
        
        logging.info(f"PlayerCharacter: {self.id} (Local: {self.is_local_player}, Color: {self.color_type})")

    def _fetch_image(self):
        info_response = self.client_interface.get_player_info(self.id)
        if info_response and info_response.get('status') == 'OK' and info_response.get('face'):
            try:
                face_b64 = info_response['face']
                self.image = pygame.image.load(io.BytesIO(base64.b64decode(face_b64)))
                self.image = pygame.transform.scale(self.image, CHARACTER_SIZE)
            except Exception: self._set_default_image()
        else: self._set_default_image()

    def _set_default_image(self):
        self.image = pygame.Surface(CHARACTER_SIZE)
        if self.color_type == 'black':
            self.image.fill(BLACK); pygame.draw.rect(self.image, WHITE, self.image.get_rect(), 2)
        elif self.color_type == 'white':
            self.image.fill(WHITE); pygame.draw.rect(self.image, BLACK, self.image.get_rect(), 2)
        else: self.image.fill(GREY)

    def move(self, keys, walls):
        if not self.is_local_player or self.lives <= 0: return
        dx = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]: dx = -self.speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: dx = self.speed
        self.vy += GRAVITY
        self.vy = min(self.vy, TERMINAL_VELOCITY)
        if self.on_ground and (keys[pygame.K_UP] or keys[pygame.K_w]):
            self.vy, self.on_ground = JUMP_STRENGTH, False
        self.rect.x += dx
        for wall in walls:
            if self.rect.colliderect(wall.rect):
                if dx > 0: self.rect.right = wall.rect.left
                elif dx < 0: self.rect.left = wall.rect.right
        self.rect.y += self.vy
        self.on_ground = False
        for wall in walls:
            if self.rect.colliderect(wall.rect):
                if self.vy > 0: self.rect.bottom, self.vy, self.on_ground = wall.rect.top, 0, True
                elif self.vy < 0: self.rect.top, self.vy = wall.rect.bottom, 0
        self.x, self.y = self.rect.x, self.rect.y
        self.client_interface.set_player_state(self.id, self.x, self.y, self.lives)

    def update_from_server(self, p_data):
        self.x, self.y = p_data['x'], p_data['y']
        self.rect.topleft = (self.x, self.y)
        self.color_type = p_data['color_type']
        self.gems_collected, self.lives, self.at_exit = p_data['gems_collected'], p_data['lives'], p_data['at_exit']
        if self.image is None: self._set_default_image()

    def draw(self, surface):
        if self.lives > 0 and self.image: surface.blit(self.image, self.rect)

class Gem:
    def __init__(self, id, x, y, gem_type, image_b64=None):
        self.id, self.x, self.y, self.gem_type, self.image = id, x, y, gem_type, None
        self.size = GEM_SIZE
        if image_b64:
            try:
                self.image = pygame.image.load(io.BytesIO(base64.b64decode(image_b64)))
                self.image = pygame.transform.scale(self.image, self.size)
            except Exception: self._set_default_image()
        else: self._set_default_image()
        self.rect = self.image.get_rect(topleft=(self.x, self.y))
    def _set_default_image(self): self.image = pygame.Surface(self.size, pygame.SRCALPHA)
    def draw(self, surface): surface.blit(self.image, self.rect)

class Hazard:
    def __init__(self, id, x, y, hazard_type, width, height, image_b64=None):
        self.id, self.x, self.y, self.hazard_type = id, x, y, hazard_type
        self.width, self.height, self.image = width, height, None
        if image_b64:
            try:
                self.image = pygame.image.load(io.BytesIO(base64.b64decode(image_b64)))
                self.image = pygame.transform.scale(self.image, (self.width, self.height))
            except Exception: self._set_default_image()
        else: self._set_default_image()
        self.rect = self.image.get_rect(topleft=(self.x, self.y))
    def _set_default_image(self): self.image = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
    def draw(self, surface): surface.blit(self.image, self.rect)

class ExitArea:
    def __init__(self, x, y, width, height, image_b64=None):
        self.x, self.y, self.width, self.height, self.image = x, y, width, height, None
        if image_b64:
            try:
                self.image = pygame.image.load(io.BytesIO(base64.b64decode(image_b64)))
                self.image = pygame.transform.scale(self.image, (self.width, self.height))
            except Exception: self._set_default_image()
        else: self._set_default_image()
        self.rect = self.image.get_rect(topleft=(self.x, self.y))
    def _set_default_image(self): self.image = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
    def draw(self, surface): surface.blit(self.image, self.rect)

class Wall:
    def __init__(self, id, x, y, width, height, image_b64=None):
        self.id, self.x, self.y, self.width, self.height, self.image = id, x, y, width, height, None
        if image_b64:
            try:
                img = pygame.image.load(io.BytesIO(base64.b64decode(image_b64)))
                self.image = pygame.Surface((width, height))
                for i in range(0, width, img.get_width()):
                    for j in range(0, height, img.get_height()): self.image.blit(img, (i, j))
            except Exception: self._set_default_image()
        else: self._set_default_image()
        self.rect = self.image.get_rect(topleft=(self.x, self.y))
    def _set_default_image(self): self.image = pygame.Surface((self.width, self.height)); self.image.fill(GREY)
    def draw(self, surface): surface.blit(self.image, self.rect)


# --- Lobby Screen ---

def show_lobby_screen(client_interface):
    error_message, cooldown, my_pid = "", 0, None
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and cooldown <= 0 and not my_pid:
                if event.key == pygame.K_b: color = "black"
                elif event.key == pygame.K_w: color = "white"
                else: continue
                response = client_interface.register_player(color)
                if response and response['status'] == 'OK':
                    my_pid, error_message = response['player_id'], ""
                else: error_message, cooldown = response.get('message', 'Failed'), 120
        screen.fill(BLACK)
        title_text = font_large.render("Black vs. White", True, WHITE)
        screen.blit(title_text, title_text.get_rect(center=(WIDTH // 2, 80)))
        state = client_interface.get_game_state()
        if state['status'] != 'OK':
            err_text = font_medium.render(state['message'], True, RED)
            screen.blit(err_text, err_text.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
        else:
            players = state.get('players', {})
            b_taken = any(p['color_type'] == 'black' for p in players.values())
            w_taken = any(p['color_type'] == 'white' for p in players.values())
            if not my_pid:
                b_text = font_medium.render("Press [B] for Black", True, GREY if b_taken else WHITE)
                w_text = font_medium.render("Press [W] for White", True, GREY if w_taken else WHITE)
                screen.blit(b_text, b_text.get_rect(center=(WIDTH // 2, 200)))
                screen.blit(w_text, w_text.get_rect(center=(WIDTH // 2, 250)))
            else:
                wait_text = font_medium.render("You are in! Waiting for opponent...", True, GREEN)
                screen.blit(wait_text, wait_text.get_rect(center=(WIDTH // 2, 220)))
            if error_message:
                err_text = font_small.render(error_message, True, RED)
                screen.blit(err_text, err_text.get_rect(center=(WIDTH // 2, 300)))
            if b_taken and w_taken:
                pygame.display.flip(); time.sleep(1)
                final_state = client_interface.get_game_state()
                my_data = next(((pid, p['color_type']) for pid, p in final_state['players'].items() if pid == my_pid), None)
                if my_data: return my_data
                # Fallback for player 2
                all_ids = list(final_state['players'].keys())
                other_id = next((pid for pid in all_ids if pid != my_pid), None)
                my_id = other_id if my_pid is None else my_pid
                return my_id, final_state['players'][my_id]['color_type']

        if cooldown > 0: cooldown -= 1
        pygame.display.flip(); clock.tick(FPS)


# --- Main Game Loop ---

def main_game_loop():
    client_interface = ClientInterface()
    player_id, player_color = show_lobby_screen(client_interface)
    local_player = PlayerCharacter(player_id, is_local_player=True, initial_color_choice=player_color)
    other_players, gem_objects, hazard_objects, wall_objects, images_b64 = {}, {}, {}, {}, {}
    exit_object, match_ended, match_win_status, last_stage = None, False, "", 0
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
        state = client_interface.get_game_state()
        if not (state and state['status'] == 'OK'):
            time.sleep(1); continue
        game_info = state['game_info']
        if game_info['match_winner'] and not match_ended:
            match_ended = True
            winner_id = game_info['match_winner']
            if winner_id == 'draw': match_win_status = "DRAW"
            else: match_win_status = "WIN" if winner_id == local_player.id else "LOSE"
        if match_ended:
            screen.fill(BLACK)
            msg, color = {"WIN": ("MATCH WON!", WIN_GREEN), "LOSE": ("MATCH LOST!", RED), "DRAW": ("IT'S A DRAW!", WHITE)}.get(match_win_status)
            status_text = font_large.render(msg, True, color)
            restart_text = font_small.render("Press R to Play Again or Q to Quit", True, WHITE)
            screen.blit(status_text, status_text.get_rect(center=(WIDTH//2, HEIGHT//2 - 40)))
            screen.blit(restart_text, restart_text.get_rect(center=(WIDTH//2, HEIGHT//2 + 40)))
            keys = pygame.key.get_pressed()
            if keys[pygame.K_q]: running = False
            if keys[pygame.K_r]: client_interface.reset_game(); main_game_loop(); return
        else:
            current_stage = game_info['current_stage']
            if current_stage != last_stage:
                logging.info(f"--- Entering Stage {current_stage} ---")
                gem_objects.clear(); hazard_objects.clear(); wall_objects.clear(); exit_object = None
                last_stage = current_stage
            
            p_ids = set(state['players'].keys())
            for p_id, p_data in state['players'].items():
                if p_id == local_player.id: local_player.update_from_server(p_data)
                else:
                    if p_id not in other_players: other_players[p_id] = PlayerCharacter(p_id, initial_color_choice=p_data['color_type'])
                    other_players[p_id].update_from_server(p_data)
            for p_id in list(other_players.keys()):
                if p_id not in p_ids: del other_players[p_id]
            
            if not images_b64: images_b64 = state.get('images', {})
            
            if not wall_objects and state.get('walls'):
                for w in state['walls']: wall_objects[w['id']] = Wall(w['id'],w['x'],w['y'],w['width'],w['height'],images_b64.get('wall'))
            if not hazard_objects and state.get('hazards'):
                for h in state['hazards']: hazard_objects[h['id']] = Hazard(h['id'],h['x'],h['y'],h['type'],h['width'],h['height'],images_b64.get(f"{h['type']}_hazard"))
            g_ids = {g['id'] for g in state['gems']}
            for g_id in list(gem_objects.keys()):
                if g_id not in g_ids: del gem_objects[g_id]
            for g in state['gems']:
                if g['id'] not in gem_objects: gem_objects[g['id']] = Gem(g['id'],g['x'],g['y'],g['type'],images_b64.get(f"{g['type']}_gem"))
            if not exit_object and state.get('exit_area'):
                e = state['exit_area']; exit_object = ExitArea(e['x'], e['y'], e['width'], e['height'], images_b64.get('exit'))

            if not game_info['stage_winner']:
                keys = pygame.key.get_pressed()
                local_player.move(keys, list(wall_objects.values()))
                if local_player.lives > 0:
                    for g_id, gem in list(gem_objects.items()):
                        if local_player.rect.colliderect(gem.rect) and gem.gem_type == local_player.color_type:
                            client_interface.collect_gem(local_player.id, g_id); del gem_objects[g_id]; break
                    for h_id, hazard in hazard_objects.items():
                        if local_player.rect.colliderect(hazard.rect) and hazard.hazard_type != local_player.color_type:
                            client_interface.check_hazard_collision(local_player.id, h_id); break
                    if exit_object and local_player.rect.colliderect(exit_object.rect) and not local_player.at_exit:
                        client_interface.player_at_exit(local_player.id)
            
            screen.fill(BLACK)
            for w in wall_objects.values(): w.draw(screen)
            for h in hazard_objects.values(): h.draw(screen)
            for g in gem_objects.values(): g.draw(screen)
            if exit_object: exit_object.draw(screen)
            local_player.draw(screen)
            for p in other_players.values(): p.draw(screen)
            
            scores = game_info['scores']
            score_text = font_medium.render(f"Score: B {scores['player_black']} - W {scores['player_white']}", True, WHITE)
            screen.blit(score_text, (10, 10))
            stage_text = font_medium.render(f"Stage: {game_info['current_stage']}/{game_info['total_stages']}", True, WHITE)
            screen.blit(stage_text, (WIDTH - stage_text.get_width() - 10, 10))
            elapsed_time = game_info['elapsed_time']
            mins, secs = int(elapsed_time // 60), int(elapsed_time % 60)
            stopwatch_text = font_medium.render(f"{mins:02d}:{secs:02d}", True, WHITE)
            screen.blit(stopwatch_text, (WIDTH // 2 - stopwatch_text.get_width() // 2, 10))
            
            if game_info['stage_winner']:
                winner_name = "BLACK" if "black" in game_info['stage_winner'] else "WHITE"
                stage_win_text = font_large.render(f"{winner_name} WINS THE STAGE!", True, GREEN)
                screen.blit(stage_win_text, stage_win_text.get_rect(center=(WIDTH//2, HEIGHT//2)))
        
        pygame.display.flip()
        clock.tick(FPS)
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main_game_loop()