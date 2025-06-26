import sys
import io
import socket
import logging
import json
import base64
import pygame

# --- Constants ---

# Game window
WIDTH, HEIGHT = 640, 480
FPS = 60

# Sizes
CHARACTER_SIZE = (64, 64)
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

# --- Logging ---

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Networking ---

class ClientInterface:
    """Handles communication with the game server."""

    def __init__(self):
        # DIUBAH: Tidak lagi menyimpan idplayer, karena interface ini generik
        self.server_address = ('127.0.0.1', 55554)
        logging.info(f"ClientInterface: Initialized for server {self.server_address}")

    def send_command(self, command_str=""):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(self.server_address)
            sock.sendall((command_str + "\r\n\r\n").encode('utf-8'))
            data_received = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data_received += chunk
                if b"\r\n\r\n" in data_received:
                    break
            decoded_data = data_received.decode('utf-8').strip()
            if decoded_data:
                return json.loads(decoded_data)
            else:
                return {"status": "ERROR", "message": "Empty response"}
        except ConnectionRefusedError:
            return {"status": "ERROR", "message": "Connection refused"}
        except json.JSONDecodeError as e:
            return {"status": "ERROR", "message": f"Invalid JSON response: {e}"}
        except Exception as e:
            return {"status": "ERROR", "message": f"Network error: {e}"}
        finally:
            sock.close()

    # DIUBAH: Menerima argumen warna
    def register_player(self, color):
        return self.send_command(f"register_player {color}")

    # DIUBAH: Semua metode sekarang menerima player_id secara eksplisit
    def set_player_state(self, player_id, x, y, lives):
        return self.send_command(f"set_player_state {player_id} {x} {y} {lives}")

    def get_game_state(self):
        return self.send_command("get_game_state")

    def get_player_info(self, player_id):
        return self.send_command(f"get_player_info {player_id}")

    def collect_gem(self, player_id, gem_id):
        return self.send_command(f"collect_gem {player_id} {gem_id}")

    def check_hazard_collision(self, player_id, hazard_id):
        return self.send_command(f"check_hazard_collision {player_id} {hazard_id}")

    def player_at_exit(self, player_id):
        return self.send_command(f"player_at_exit {player_id}")

    # DIUBAH: reset_team_game menjadi reset_game dan tidak perlu argumen
    def reset_game(self):
        logging.info(f"ClientInterface: Sending reset_game command")
        return self.send_command(f"reset_game")


# --- Game Entities ---

# DIUBAH: Seluruh kelas PlayerCharacter dimodifikasi
class PlayerCharacter:
    """Represents a player character (Black or White) in the game."""

    def __init__(self, id, is_local_player=False, initial_color_choice=None, initial_x=None, initial_y=None):
        self.id = id
        self.is_local_player = is_local_player
        self.color_type = initial_color_choice # DIUBAH: dari character_type ke color_type
        self.x = initial_x if initial_x is not None else 0
        self.y = initial_y if initial_y is not None else 0
        self.speed = 5
        self.gems_collected = 0 # DIUBAH: Menjadi satu atribut saja
        self.lives = 1
        self.at_exit = False
        self.image = None
        self.rect = pygame.Rect(self.x, self.y, CHARACTER_SIZE[0], CHARACTER_SIZE[1])
        self.vy = 0
        self.on_ground = False
        
        if self.is_local_player:
            self.client_interface = ClientInterface()
            # DIUBAH: Logika registrasi baru
            self._register_with_server(initial_color_choice)
        else:
            self.image = pygame.Surface(CHARACTER_SIZE)
            self.image.fill(GREY)
        
        logging.info(f"PlayerCharacter: Initializing {self.id} (Local: {self.is_local_player}, Color: {self.color_type})")

    # BARU: Metode registrasi yang baru
    def _register_with_server(self, color):
        response = self.client_interface.register_player(color)
        if response and response['status'] == 'OK':
            self.id = response['player_id'] # Dapatkan ID resmi dari server
            self.color_type = response['color_type']
            self.x = response.get('x', self.x)
            self.y = response.get('y', self.y)
            self.rect.topleft = (self.x, self.y)
            logging.info(f"PlayerCharacter: Registered as {self.id} at ({self.x}, {self.y})")
            info_response = self.client_interface.get_player_info(self.id)
            if info_response and info_response['status'] == 'OK' and info_response.get('face'):
                try:
                    face_b64 = info_response['face']
                    self.image = pygame.image.load(io.BytesIO(base64.b64decode(face_b64)))
                    self.image = pygame.transform.scale(self.image, CHARACTER_SIZE)
                except Exception as e:
                    self._set_default_image()
            else:
                self._set_default_image()
        else:
            logging.error(f"Failed to register as {color}: {response.get('message')}")
            self.id = None # Sinyal kegagalan registrasi

    # DIUBAH: Menggunakan color_type black/white
    def _set_default_image(self):
        self.image = pygame.Surface(CHARACTER_SIZE)
        if self.color_type == 'black':
            self.image.fill(BLACK)
            pygame.draw.rect(self.image, WHITE, self.image.get_rect(), 2) # Beri border putih
        elif self.color_type == 'white':
            self.image.fill(WHITE)
            pygame.draw.rect(self.image, BLACK, self.image.get_rect(), 2) # Beri border hitam
        else:
            self.image.fill(GREY)

    # DIUBAH: Kontrol disatukan untuk pemain lokal
    def move(self, keys=None, walls=None):
        if not self.is_local_player or self.lives <= 0:
            return
            
        dx = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx = -self.speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx = self.speed
            
        self.vy += GRAVITY
        self.vy = min(self.vy, TERMINAL_VELOCITY)
        
        if self.on_ground and (keys[pygame.K_UP] or keys[pygame.K_w]):
            self.vy = JUMP_STRENGTH
            self.on_ground = False
            
        # Logika fisika dan tabrakan dinding tetap sama
        self.rect.x += dx
        if walls:
            for wall in walls:
                if self.rect.colliderect(wall.rect):
                    if dx > 0: self.rect.right = wall.rect.left
                    elif dx < 0: self.rect.left = wall.rect.right
        self.rect.y += self.vy
        self.on_ground = False
        if walls:
            for wall in walls:
                if self.rect.colliderect(wall.rect):
                    if self.vy > 0:
                        self.rect.bottom = wall.rect.top
                        self.vy = 0
                        self.on_ground = True
                    elif self.vy < 0:
                        self.rect.top = wall.rect.bottom
                        self.vy = 0
        
        self.x = self.rect.x
        self.y = self.rect.y
        self.client_interface.set_player_state(self.id, self.x, self.y, self.lives)

    # DIUBAH: Mengupdate atribut baru
    def update_from_server(self, player_data):
        self.x = player_data['x']
        self.y = player_data['y']
        self.rect.topleft = (self.x, self.y)
        self.color_type = player_data['color_type']
        self.gems_collected = player_data['gems_collected']
        self.lives = player_data['lives']
        self.at_exit = player_data['at_exit']
        if self.image is None or (self.image.get_at((0,0)) == GREY and self.color_type):
            self._set_default_image()

    def draw(self, surface):
        if self.lives > 0:
            if self.image:
                surface.blit(self.image, self.rect)
            else: # Fallback
                pygame.draw.rect(surface, GREY, self.rect)

class Gem:
    """Represents a collectible gem (fire or water)."""
    def __init__(self, id, x, y, gem_type, image_b64=None):
        self.id = id
        self.x = x
        self.y = y
        self.gem_type = gem_type
        self.image = None
        self.size = GEM_SIZE
        if image_b64:
            try:
                self.image = pygame.image.load(io.BytesIO(base64.b64decode(image_b64)))
                self.image = pygame.transform.scale(self.image, self.size)
            except Exception as e:
                self._set_default_image()
        else:
            self._set_default_image()
        self.rect = self.image.get_rect(topleft=(self.x, self.y))

    def _set_default_image(self):
        self.image = pygame.Surface(self.size, pygame.SRCALPHA)
        if self.gem_type == 'black':
            pygame.draw.circle(self.image, ORANGE, (self.size[0] // 2, self.size[1] // 2), self.size[0] // 2 - 2)
        elif self.gem_type == 'white':
            pygame.draw.rect(self.image, CYAN, (2, 2, self.size[0]-4, self.size[1]-4))

    def draw(self, surface):
        surface.blit(self.image, self.rect)

    def update_position(self, x, y):
        self.x = x
        self.y = y
        self.rect.topleft = (self.x, self.y)

class Hazard:
    """Represents a hazard (fire or water pool)."""
    def __init__(self, id, x, y, hazard_type, width, height, image_b64=None):
        self.id = id
        self.x = x
        self.y = y
        self.hazard_type = hazard_type
        self.width = width
        self.height = height
        self.image = None
        if image_b64:
            try:
                self.image = pygame.image.load(io.BytesIO(base64.b64decode(image_b64)))
                self.image = pygame.transform.scale(self.image, (self.width, self.height))
            except Exception as e:
                self._set_default_image()
        else:
            self._set_default_image()
        self.rect = self.image.get_rect(topleft=(self.x, self.y))

    def _set_default_image(self):
        self.image = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        if self.hazard_type == 'black':
            self.image.fill((255, 0, 0, 100))
        elif self.hazard_type == 'white':
            self.image.fill((0, 0, 255, 100))

    def draw(self, surface):
        surface.blit(self.image, self.rect)

class ExitArea:
    """Represents the exit area for the players."""
    def __init__(self, x, y, width, height, image_b64=None):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.image = None
        if image_b64:
            try:
                self.image = pygame.image.load(io.BytesIO(base64.b64decode(image_b64)))
                self.image = pygame.transform.scale(self.image, (self.width, self.height))
            except Exception as e:
                self._set_default_image()
        else:
            self._set_default_image()
        self.rect = self.image.get_rect(topleft=(self.x, self.y))

    def _set_default_image(self):
        self.image = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.image.fill((50, 200, 50, 150))

    def draw(self, surface):
        surface.blit(self.image, self.rect)

class Wall:
    """Represents a static wall or platform."""
    def __init__(self, id, x, y, width, height, image_b64=None):
        self.id = id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.image = None
        if image_b64:
            try:
                self.image = pygame.image.load(io.BytesIO(base64.b64decode(image_b64)))
                self.image = pygame.transform.scale(self.image, (self.width, self.height))
            except Exception as e:
                self._set_default_image()
        else:
            self._set_default_image()
        self.rect = self.image.get_rect(topleft=(self.x, self.y))

    def _set_default_image(self):
        self.image = pygame.Surface((self.width, self.height))
        self.image.fill((100, 100, 100))

    def draw(self, surface):
        surface.blit(self.image, self.rect)

# --- Main Game Loop ---

def main_game_loop():
    # =================================================================================
    # FASE 1: INISIALISASI SESI PERMAINAN
    # =================================================================================
    # Bagian ini hanya berjalan sekali setiap kali permainan baru dimulai.

    # 1. Meminta pemain memilih warna
    player_color = ""
    while player_color not in ["black", "white"]:
        player_color = input("Choose your color (black/white): ").lower()
        if player_color not in ["black", "white"]:
            print("Invalid choice. Please type 'black' or 'white'.")

    # 2. Membuat objek pemain lokal dan mendaftarkannya ke server
    local_player = PlayerCharacter(f"player_{player_color}", is_local_player=True, initial_color_choice=player_color)

    # 3. Pemeriksaan kritis: Pastikan registrasi berhasil sebelum melanjutkan
    if not local_player.id:
        logging.error("Main Loop: Failed to register player. Is the server running? Is the color taken? Exiting.")
        pygame.quit()
        sys.exit()

    # 4. Menyiapkan "wadah" kosong untuk menyimpan semua objek game
    other_players = {}  # Untuk menyimpan data pemain lain (lawan)
    gem_objects = {}    # Untuk menyimpan semua objek gem
    hazard_objects = {} # Untuk menyimpan semua objek hazard
    wall_objects = {}   # Untuk menyimpan semua objek dinding/platform
    exit_object = None  # Untuk menyimpan objek pintu keluar

    # 5. Variabel untuk menyimpan gambar dari server (agar tidak perlu diminta berulang kali)
    black_gem_img_b64, white_gem_img_b64 = None, None
    black_hazard_img_b64, white_hazard_img_b64 = None, None
    exit_img_b64, wall_img_b64 = None, None
    
    # 6. Variabel untuk menyimpan skor yang dibutuhkan untuk menang
    black_gems_required, white_gems_required = 0, 0

    # 7. "Bendera" (flags) untuk mengontrol alur permainan
    game_ended = False  # Menjadi True jika ada pemenang
    win_status = ""     # Akan diisi dengan "WIN" atau "LOSE"

    # =================================================================================
    # FASE 2: LOOP PERMAINAN AKTIF
    # =================================================================================
    # 'running = True' memulai loop. Loop akan terus berjalan selama 'running' adalah True.
    running = True
    while running:
        # 8. Penanganan Event (Input dari Pengguna)
        for event in pygame.event.get():
            if event.type == pygame.QUIT: # Jika pemain menekan tombol 'X' di jendela
                running = False # Ini akan menghentikan loop utama

        # -----------------------------------------------------------------------------
        # 9. Logika Layar Akhir Permainan (Menang/Kalah)
        # -----------------------------------------------------------------------------
        if game_ended:
            screen.fill(BLACK) # Bersihkan layar menjadi hitam
            # Tampilkan pesan sesuai status menang/kalah
            if win_status == "WIN":
                status_text = font_large.render("CONGRATS YOU WIN!", True, WIN_GREEN)
            else:
                status_text = font_large.render("GAME OVER! YOU LOSE!", True, RED)
            
            # Tampilkan instruksi untuk restart atau keluar
            restart_text = font_small.render("Press R to Restart or Q to Quit", True, WHITE)
            
            # Atur posisi teks di tengah layar
            status_rect = status_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40))
            restart_rect = restart_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 40))
            
            # Gambar teks ke layar
            screen.blit(status_text, status_rect)
            screen.blit(restart_text, restart_rect)
            
            pygame.display.flip() # Update tampilan layar

            # Cek input keyboard untuk restart atau quit
            keys = pygame.key.get_pressed()
            if keys[pygame.K_q]:
                running = False # Hentikan loop
            if keys[pygame.K_r]:
                logging.info("Restarting game...")
                local_player.client_interface.reset_game() # Kirim perintah reset ke server
                main_game_loop() # Panggil ulang fungsi ini dari awal untuk memulai sesi baru
                return # WAJIB: Keluar dari eksekusi fungsi yang sekarang agar tidak tumpang tindih

            clock.tick(FPS) # Jaga FPS tetap stabil
            continue # WAJIB: Lewati sisa dari loop dan mulai dari awal (kembali ke 'if game_ended:')
        
        # -----------------------------------------------------------------------------
        # 10. Update Game State dari Server (Jika permainan belum berakhir)
        # -----------------------------------------------------------------------------
        game_state = local_player.client_interface.get_game_state()
        if game_state and game_state['status'] == 'OK':
            # a. Cek apakah server telah mengumumkan pemenang
            winner_id = game_state.get('winner')
            if winner_id and not game_ended:
                game_ended = True # Set bendera bahwa permainan berakhir
                win_status = "WIN" if winner_id == local_player.id else "LOSE"

            # b. Update data pemain (lokal dan lawan)
            current_player_ids = set(game_state['players'].keys())
            for p_id, p_data in game_state['players'].items():
                if p_id == local_player.id:
                    local_player.update_from_server(p_data)
                else:
                    if p_id not in other_players:
                        other_players[p_id] = PlayerCharacter(p_id, is_local_player=False)
                    other_players[p_id].update_from_server(p_data)
            
            for p_id in list(other_players.keys()):
                if p_id not in current_player_ids:
                    del other_players[p_id]

            # c. Ambil data gambar (hanya sekali)
            if not black_gem_img_b64: black_gem_img_b64 = game_state.get('black_gem_image_b64')
            if not white_gem_img_b64: white_gem_img_b64 = game_state.get('white_gem_image_b64')
            if not black_hazard_img_b64: black_hazard_img_b64 = game_state.get('black_hazard_image_b64')
            if not white_hazard_img_b64: white_hazard_img_b64 = game_state.get('white_hazard_image_b64')
            if not exit_img_b64: exit_img_b64 = game_state.get('exit_area_image_b64')
            if not wall_img_b64: wall_img_b64 = game_state.get('wall_image_b64')
            
            # d. Ambil skor yang dibutuhkan
            black_gems_required = game_state.get('black_gems_required', 0)
            white_gems_required = game_state.get('white_gems_required', 0)

            # e. Update atau buat objek di dunia game (Gem, Hazard, Dinding, Pintu Keluar)
            current_gem_ids = set(g['id'] for g in game_state['gems'])
            for g_data in game_state['gems']:
                g_id, g_type = g_data['id'], g_data['type']
                if g_id not in gem_objects:
                    img_b64 = black_gem_img_b64 if g_type == 'black' else white_gem_img_b64
                    gem_objects[g_id] = Gem(g_id, g_data['x'], g_data['y'], g_type, img_b64)
            for g_id in list(gem_objects.keys()):
                if g_id not in current_gem_ids:
                    del gem_objects[g_id]

            for h_data in game_state['hazards']:
                h_id, h_type = h_data['id'], h_data['type']
                if h_id not in hazard_objects:
                    img_b64 = black_hazard_img_b64 if h_type == 'black' else white_hazard_img_b64
                    hazard_objects[h_id] = Hazard(h_id, h_data['x'], h_data['y'], h_type, h_data['width'], h_data['height'], img_b64)

            if not wall_objects and game_state.get('walls'):
                for w_data in game_state['walls']:
                    wall_objects[w_data['id']] = Wall(w_data['id'], w_data['x'], w_data['y'], w_data['width'], w_data['height'], wall_img_b64)

            if not exit_object and game_state.get('exit_area'):
                e_data = game_state['exit_area']
                exit_object = ExitArea(e_data['x'], e_data['y'], e_data['width'], e_data['height'], exit_img_b64)

        # -----------------------------------------------------------------------------
        # 11. Input Pemain dan Pergerakan
        # -----------------------------------------------------------------------------
        keys = pygame.key.get_pressed()
        local_player.move(keys, list(wall_objects.values()))

        # -----------------------------------------------------------------------------
        # 12. Deteksi Tabrakan (Hanya untuk pemain lokal)
        # -----------------------------------------------------------------------------
        if local_player.lives > 0:
            for g_id, gem in list(gem_objects.items()):
                if local_player.rect.colliderect(gem.rect):
                    if gem.gem_type == local_player.color_type:
                        local_player.client_interface.collect_gem(local_player.id, g_id)
                        break 
            
            for h_id, hazard in hazard_objects.items():
                if local_player.rect.colliderect(hazard.rect):
                    if hazard.hazard_type != local_player.color_type:
                        local_player.client_interface.check_hazard_collision(local_player.id, h_id)
                        break
            
            if exit_object and local_player.rect.colliderect(exit_object.rect) and not local_player.at_exit:
                local_player.client_interface.player_at_exit(local_player.id)

        # -----------------------------------------------------------------------------
        # 13. Menggambar Semuanya ke Layar
        # -----------------------------------------------------------------------------
        screen.fill(BLACK) # Latar belakang
        for wall in wall_objects.values(): wall.draw(screen)
        for hazard in hazard_objects.values(): hazard.draw(screen)
        for gem in gem_objects.values(): gem.draw(screen)
        if exit_object: exit_object.draw(screen)
        
        local_player.draw(screen) # Gambar pemain kita
        for player in other_players.values(): player.draw(screen) # Gambar pemain lawan

        # Tampilkan HUD (Heads-Up Display)
        required_gems = black_gems_required if local_player.color_type == 'black' else white_gems_required
        score_text = font_medium.render(f"Gems: {local_player.gems_collected}/{required_gems}", True, WHITE)
        screen.blit(score_text, (10, 10))
        
        color_text = font_medium.render(f"You are: {local_player.color_type.capitalize()}", True, WHITE)
        screen.blit(color_text, (10, 40))
        
        pygame.display.flip() # Final: update semua yang sudah digambar ke layar
        clock.tick(FPS) # Menjaga kecepatan game agar tidak terlalu cepat/lambat

    # =================================================================================
    # FASE 3: KELUAR DARI PERMAINAN
    # =================================================================================
    # Baris ini hanya akan dieksekusi jika 'running' menjadi False.
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main_game_loop()

if __name__ == "__main__":
    main_game_loop()
