import json
import base64
import threading
import io
import logging
import time
from PIL import Image, ImageDraw

# Set logging level for the server protocol
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def generate_simple_image_b64(width, height, color, shape="square", border_color=None, border_width=0, alpha=255):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill_color = color[:3] + (alpha,)
    outline_color = border_color[:3] + (255,) if border_color else None

    # Draw shapes
    if shape == "square":
        d.rectangle([0, 0, width, height], fill=fill_color)
    elif shape == "circle":
        d.ellipse([0, 0, width, height], fill=fill_color)
    elif shape == "diamond":
        d.polygon([(width / 2, 0), (width, height / 2), (width / 2, height), (0, height / 2)], fill=fill_color)
    elif shape == "door":
        d.rectangle([0, 0, width, height], fill=fill_color)
        d.ellipse([width * 0.7, height * 0.4, width * 0.9, height * 0.6], fill=(50, 50, 50, 255))
    elif shape == "brick":
        d.rectangle([0, 0, width, height], fill=fill_color)
        for i in range(0, height, 10):
            d.line([(0, i), (width, i)], fill=(fill_color[0] // 2, fill_color[1] // 2, fill_color[2] // 2, 255), width=1)
        for i in range(0, width, 20):
            d.line([(i, 0), (i, height)], fill=(fill_color[0] // 2, fill_color[1] // 2, fill_color[2] // 2, 255), width=1)

    # Draw borders on top
    if outline_color and border_width > 0:
        if shape == "diamond":
            d.polygon([(width / 2, 0), (width, height / 2), (width / 2, height), (0, height / 2)], outline=outline_color, width=border_width)
        elif shape == "circle":
            d.ellipse([0, 0, width - 1, height - 1], outline=outline_color, width=border_width)
        elif shape in ["square", "brick", "door"]:
            d.rectangle([border_width//2 -1, border_width//2 -1, width - border_width//2, height - border_width//2], outline=outline_color, width=border_width)


    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


class PlayerServerProtocol:
    def __init__(self):
        self._lock = threading.Lock()
        self.map_width = 800
        self.map_height = 600
        self.default_player_lives = 1
        
        self.players, self.gems, self.hazards, self.walls, self.exit_area = {}, {}, {}, {}, {}
        self.levels, self.total_stages = [], 5
        self.scores = {'player_black': 0, 'player_white': 0}
        self.current_level_index, self.match_winner, self.stage_winner, self.start_time, self._next_gem_id = 0, None, None, None, 0
        self.black_gems_required = 0
        self.white_gems_required = 0

        self.black_player_image_b64 = generate_simple_image_b64(48, 48, (50, 50, 50, 255), "square", (200, 200, 200), 2)
        self.white_player_image_b64 = generate_simple_image_b64(48, 48, (200, 200, 200, 255), "square", (50, 50, 50), 2)
        
        self.black_gem_image_b64 = generate_simple_image_b64(20, 20, (50, 50, 50, 255), "diamond", border_color=(255, 255, 255), border_width=2)
        self.white_gem_image_b64 = generate_simple_image_b64(20, 20, (255, 255, 255, 255), "diamond", border_color=(0, 0, 0), border_width=2)
        self.black_hazard_image_b64 = generate_simple_image_b64(100, 50, (20, 20, 20), "square", border_color=(255, 100, 0), border_width=2, alpha=200)
        self.white_hazard_image_b64 = generate_simple_image_b64(100, 50, (230, 230, 230), "square", border_color=(255, 100, 0), border_width=2, alpha=200)

        self.exit_area_image_b64 = generate_simple_image_b64(80, 80, (50, 200, 50), "door", (20, 100, 20), 2, alpha=200)
        self.wall_image_b64 = generate_simple_image_b64(20, 20, (100, 100, 100), "brick", (50, 50, 50), 1)

        self._full_reset()

    def _define_levels(self):
        self.levels = []
        
        # Level 1: Pengenalan Dasar
        self.levels.append({
            'start_pos': {'black': (50, 532), 'white': (702, 532)},
            'walls': [
                (0, 580, 800, 20), (200, 480, 400, 20), (300, 380, 200, 20),
                (550, 280, 100, 20), (250, 180, 100, 20),
            ],
            'hazards': [('white', 300, 560, 100, 20)],
            'gems': [('black', 250, 450), ('white', 500, 450), ('black', 350, 350), ('white', 400, 350)],
            'exit': (360, 40, 80, 80)
        })

        # Level 2: Platforming Awal
        self.levels.append({
            'start_pos': {'black': (50, 532), 'white': (702, 532)},
            'walls': [(0, 580, 150, 20), (650, 580, 150, 20), (250, 500, 100, 20), (450, 500, 100, 20), (100, 400, 100, 20), (600, 400, 100, 20), (300, 300, 200, 20)],
            'hazards': [('black', 150, 560, 50, 20)],
            'gems': [('black', 270, 470), ('white', 470, 470), ('black', 120, 370), ('white', 620, 370), ('black', 390, 270)],
            'exit': (360, 220, 80, 80)
        })

        # Level 3: Jalur Terpisah
        self.levels.append({
            'start_pos': {'black': (50, 332), 'white': (702, 332)},
            'walls': [(0, 380, 200, 20), (600, 380, 200, 20), (0, 580, 800, 20), (380, 480, 40, 100), (250, 250, 300, 20)],
            'hazards': [('white', 20, 560, 350, 20), ('black', 430, 560, 350, 20)],
            'gems': [('black', 100, 550), ('black', 200, 550), ('white', 600, 550), ('white', 700, 550), ('black', 390, 220), ('white', 490, 220)],
            'exit': (360, 100, 80, 80)
        })
        
        # Level 4: Panjat Vertikal
        self.levels.append({
            'start_pos': {'black': (50, 532), 'white': (702, 532)},
            'walls': [(0, 580, 800, 20), (150, 480, 50, 20), (600, 480, 50, 20), (300, 400, 200, 20), (100, 300, 50, 20), (650, 300, 50, 20), (250, 200, 300, 20)],
            'hazards': [('white', 200, 560, 100, 20), ('black', 500, 560, 100, 20)],
            'gems': [('black', 160, 450), ('white', 610, 450), ('black', 390, 370), ('white', 110, 270), ('black', 660, 270)],
            'exit': (360, 40, 80, 80)
        })
        
        # Level 5: Ujian Terakhir (The Gauntlet)
        self.levels.append({
            'start_pos': {'black': (30, 532), 'white': (722, 532)},
            'walls': [(0, 580, 100, 20), (700, 580, 100, 20), (150, 500, 20, 80), (630, 500, 20, 80), (250, 450, 300, 20), (380, 200, 40, 250), (100, 350, 100, 20), (600, 350, 100, 20), (200, 150, 400, 20)],
            'hazards': [('black', 100, 560, 600, 20), ('white', 250, 430, 300, 20)],
            'gems': [('black', 60, 550), ('white', 730, 550), ('black', 110, 320), ('white', 610, 320), ('black', 250, 120), ('white', 500, 120)],
            'exit': (360, 40, 80, 80)
        })

    def _load_level(self, level_index):
        if level_index >= len(self.levels):
            logging.error(f"Attempted to load invalid level index: {level_index}")
            return
        level_data = self.levels[level_index]
        self.current_level_index = level_index
        self.gems.clear(); self.hazards.clear(); self.walls.clear()
        self.black_gems_required = 0; self.white_gems_required = 0
        self._next_gem_id = 0; self.stage_winner = None
        self._place_wall(0, self.map_height - 20, self.map_width, 20)
        self._place_wall(0, 0, 20, self.map_height)
        self._place_wall(self.map_width - 20, 0, 20, self.map_height)
        self._place_wall(0, 0, self.map_width, 20)
        for wall in level_data.get('walls', []): self._place_wall(*wall)
        for hazard in level_data.get('hazards', []):
            h_id = f"{hazard[0]}_pool_{len(self.hazards)}"
            self.hazards[h_id] = {'type': hazard[0], 'x': hazard[1], 'y': hazard[2], 'width': hazard[3], 'height': hazard[4]}
        for gem in level_data.get('gems', []): self._place_gem(gem[1], gem[2], gem[0])
        exit_data = level_data.get('exit')
        self.exit_area = {'x': exit_data[0], 'y': exit_data[1], 'width': exit_data[2], 'height': exit_data[3]}
        for pid, player in self.players.items():
            self._reset_player_for_new_stage(player, level_data.get('start_pos'))
        logging.info(f"Server: Level {level_index + 1} loaded.")

    def _reset_player_for_new_stage(self, player_data, start_positions):
        color = player_data['color_type']
        if start_positions and color in start_positions:
            player_data['x'], player_data['y'] = start_positions[color]
        else:
            player_data['x'] = 50 if color == 'black' else self.map_width - 50 - 48
            player_data['y'] = self.map_height - 20 - 48
        player_data['lives'] = self.default_player_lives
        player_data['gems_collected'] = 0
        player_data['at_exit'] = False

    def _load_next_stage(self):
        if self.match_winner: return
        if self.current_level_index + 1 < self.total_stages: self._load_level(self.current_level_index + 1)
        else: self._determine_final_winner()

    def _determine_final_winner(self):
        if self.scores['player_black'] > self.scores['player_white']: self.match_winner = 'player_black'
        elif self.scores['player_white'] > self.scores['player_black']: self.match_winner = 'player_white'
        else: self.match_winner = 'draw'
        logging.warning(f"MATCH OVER! Final Winner: {self.match_winner}")

    def _full_reset(self):
        self.players.clear()
        self.scores = {'player_black': 0, 'player_white': 0}
        self.match_winner = None; self.stage_winner = None; self.start_time = None
        self._define_levels()
        self._load_level(0)
        logging.warning("SERVER: Full game has been reset to initial state.")

    def _place_wall(self, x, y, width, height):
        wall_id = f"wall_{len(self.walls)}"; self.walls[wall_id] = {'x': x, 'y': y, 'width': width, 'height': height}

    def _place_gem(self, x, y, gem_type):
        gem_id = f"{gem_type}_gem_{self._next_gem_id}"; self._next_gem_id += 1
        self.gems[gem_id] = {'x': x, 'y': y, 'type': gem_type}
        if gem_type == 'black':
            self.black_gems_required += 1
        elif gem_type == 'white':
            self.white_gems_required += 1
        return gem_id

    def proses_string(self, command_string):
        parts = command_string.strip().split()
        command, args = parts[0].lower(), parts[1:]
        result = {"status": "ERROR", "message": "Unknown command"}
        with self._lock:
            if not self.start_time and len(self.players) >= 1: self.start_time = time.time()
            if command == "register_player":
                result = self._register_player(args[0]) if args else {"status": "ERROR"}
            elif command == "set_player_state":
                if len(args) == 4:
                    try: result = self._set_player_state(args[0], int(args[1]), int(args[2]), int(args[3]))
                    except (ValueError, IndexError): result = {"status": "ERROR"}
                else: result = {"status": "ERROR"}
            elif command == "get_game_state": result = self._get_game_state()
            elif command == "get_player_info": result = self._get_player_info(args[0]) if args else {"status": "ERROR"}
            elif command == "collect_gem": result = self._collect_gem(args[0], args[1]) if len(args) == 2 else {"status": "ERROR"}
            elif command == "check_hazard_collision": result = self._check_hazard_collision(args[0], args[1]) if len(args) == 2 else {"status": "ERROR"}
            elif command == "player_at_exit": result = self._player_at_exit(args[0]) if args else {"status": "ERROR"}
            elif command == "reset_game": self._full_reset(); result = {"status": "OK"}
        return json.dumps(result)

    def _register_player(self, color_choice):
        color_choice = color_choice.lower()
        if color_choice not in ['black', 'white']: return {"status": "ERROR", "message": "Invalid color."}
        player_id = f"player_{color_choice}"
        if player_id in self.players: return {"status": "ERROR", "message": "Color is taken."}
        player_data = {'color_type': color_choice}
        self.players[player_id] = player_data
        self._reset_player_for_new_stage(player_data, self.levels[self.current_level_index].get('start_pos'))
        if len(self.players) == 1 and not self.start_time: self.start_time = time.time()
        logging.info(f"Player {player_id} registered.")
        return {"status": "OK", "player_id": player_id, "color_type": color_choice, "x": player_data['x'], "y": player_data['y']}

    def _set_player_state(self, player_id, x, y, lives):
        if player_id in self.players:
            self.players[player_id].update({'x': x, 'y': y, 'lives': lives}); return {"status": "OK"}
        return {"status": "ERROR", "message": "Player not found."}

    def _get_player_info(self, player_id):
        if player_id in self.players:
            color = self.players[player_id]['color_type']
            face_b64 = self.black_player_image_b64 if color == 'black' else self.white_player_image_b64
            return {"status": "OK", "color_type": color, "face": face_b64}
        return {"status": "ERROR", "message": "Player not found."}

    def _get_game_state(self):
        elapsed_time = (time.time() - self.start_time) if self.start_time else 0
        
        game_info_data = {
            "current_stage": self.current_level_index + 1,
            "total_stages": self.total_stages,
            "scores": self.scores,
            "elapsed_time": elapsed_time,
            "stage_winner": self.stage_winner,
            "match_winner": self.match_winner,
            "required_gems": {
                'black': self.black_gems_required,
                'white': self.white_gems_required
            }
        }
        
        return {
            "status": "OK",
            "players": {p_id: {**p_data} for p_id, p_data in self.players.items()},
            "gems": [{'id': g_id, **g_data} for g_id, g_data in self.gems.items()],
            "hazards": [{'id': h_id, **h_data} for h_id, h_data in self.hazards.items()],
            "walls": [{'id': w_id, **w_data} for w_id, w_data in self.walls.items()],
            "exit_area": self.exit_area,
            "images": {
                "black_gem": self.black_gem_image_b64, "white_gem": self.white_gem_image_b64,
                "black_hazard": self.black_hazard_image_b64, "white_hazard": self.white_hazard_image_b64,
                "exit": self.exit_area_image_b64, "wall": self.wall_image_b64
            },
            "game_info": game_info_data
        }

    def _handle_stage_win(self, winner_id):
        if self.stage_winner: return
        self.stage_winner = winner_id
        self.scores[winner_id] += 1
        logging.warning(f"STAGE {self.current_level_index+1} WON by {winner_id}! Score: {self.scores}")
        if self.scores[winner_id] >= (self.total_stages//2+1): self._determine_final_winner()
        elif self.current_level_index+1 >= self.total_stages: self._determine_final_winner()
        else: threading.Timer(3.0, self._load_next_stage).start()

    def _collect_gem(self, player_id, gem_id):
        if self.match_winner or self.stage_winner: return {"status":"ERROR"}
        if player_id in self.players and gem_id in self.gems:
            player, gem = self.players[player_id], self.gems[gem_id]
            if player['color_type'] == gem['type']:
                player['gems_collected'] += 1
                del self.gems[gem_id]; return {"status":"OK"}
        return {"status":"ERROR"}

    def _check_hazard_collision(self, player_id, hazard_id):
        if self.match_winner or self.stage_winner: return {"status":"ERROR"}
        if player_id in self.players and hazard_id in self.hazards:
            player, hazard = self.players[player_id], self.hazards[hazard_id]
            if player['color_type'] != hazard['type']:
                player['lives'] = 0
                opponent_id = 'player_white' if player['color_type'] == 'black' else 'player_black'
                self._handle_stage_win(opponent_id); return {"status": "OK"}
        return {"status": "OK"}

    def _player_at_exit(self, player_id):
        if self.match_winner or self.stage_winner:
            return {"status": "OK", "message": "Stage has already been won."}
        
        if player_id in self.players:
            player = self.players[player_id]
            player['at_exit'] = True
            
            required_gems = self.black_gems_required if player['color_type'] == 'black' else self.white_gems_required
            
            if player['gems_collected'] >= required_gems:
                self._handle_stage_win(player_id)
            
            return {"status": "OK", "message": "Player at exit processed."}
            
        return {"status": "ERROR", "message": "Player not found."}