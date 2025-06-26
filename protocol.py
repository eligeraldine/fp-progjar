import json
import base64
import random
import threading
import io
import math
import logging
from PIL import Image, ImageDraw

# Set logging level for the server protocol
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def generate_simple_image_b64(width, height, color, shape="square", border_color=None, border_width=0, alpha=255):
    """Generates a simple base64 encoded image with optional border and alpha."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))  # Transparent background
    d = ImageDraw.Draw(img)
    fill_color = color[:3] + (alpha,)

    if shape == "square":
        d.rectangle([0, 0, width, height], fill=fill_color)
    elif shape == "circle":
        d.ellipse([0, 0, width, height], fill=fill_color)
    elif shape == "triangle":
        d.polygon([(width / 2, 0), (0, height), (width, height)], fill=fill_color)
    elif shape == "diamond":
        d.polygon([(width / 2, 0), (width, height / 2), (width / 2, height), (0, height / 2)], fill=fill_color)
    elif shape == "cross":
        d.rectangle([width/4, 0, 3*width/4, height], fill=fill_color)
        d.rectangle([0, height/4, width, 3*height/4], fill=fill_color)
    elif shape == "door":
        d.rectangle([0, 0, width, height], fill=fill_color)
        d.ellipse([width * 0.7, height * 0.4, width * 0.9, height * 0.6], fill=(50, 50, 50, 255))
    elif shape == "brick":
        d.rectangle([0, 0, width, height], fill=fill_color)
        for i in range(0, height, 10):
            d.line([(0, i), (width, i)], fill=(fill_color[0]//2, fill_color[1]//2, fill_color[2]//2, 255), width=1)
        for i in range(0, width, 20):
            d.line([(i, 0), (i, height)], fill=(fill_color[0]//2, fill_color[1]//2, fill_color[2]//2, 255), width=1)

    if border_color and border_width > 0:
        for i in range(border_width):
            if shape in ["square", "brick", "door"]:
                d.rectangle([i, i, width - 1 - i, height - 1 - i], outline=border_color)
            elif shape == "circle":
                d.ellipse([i, i, width - 1 - i, height - 1 - i], outline=border_color)
            # Add border drawing for other shapes if necessary

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


class PlayerServerProtocol:
    """
    Manages the game state for all connected players (Fireboy/Watergirl),
    gems, hazards (fire/water pools), walls, and win/lose conditions.
    Handles commands from clients to update and retrieve game data.
    """

    def __init__(self):
        self.players = {}  # player_id -> {x, y, color_type, gems_collected, lives, at_exit}
        self.gems = {}     # gem_id -> {x, y, type: 'black'/'white'}
        self.hazards = {}  # hazard_id -> {x, y, type: 'black'/'white', width, height}
        self.walls = {}
        self.exit_area = {}
        self._lock = threading.Lock()

        self._next_gem_id = 0
        self.map_width = 640
        self.map_height = 480
        self.default_player_lives = 1

        # Competitive state
        self.winner = None  # Will be 'player_black' or 'player_white' when there's a winner
        self.black_gems_required = 0
        self.white_gems_required = 0

        # Game element images (base64 encoded) - updated for black/white
        self.black_player_image_b64 = generate_simple_image_b64(64, 64, (50, 50, 50, 255), "square", (200, 200, 200), 2)
        self.white_player_image_b64 = generate_simple_image_b64(64, 64, (200, 200, 200, 255), "square", (50, 50, 50), 2)
        self.black_gem_image_b64 = generate_simple_image_b64(20, 20, (50, 50, 50, 255), "diamond")
        self.white_gem_image_b64 = generate_simple_image_b64(20, 20, (255, 255, 255, 255), "diamond")
        self.black_hazard_image_b64 = generate_simple_image_b64(100, 50, (20, 20, 20), "square", alpha=200)
        self.white_hazard_image_b64 = generate_simple_image_b64(100, 50, (230, 230, 230), "square", alpha=200)
        self.exit_area_image_b64 = generate_simple_image_b64(80, 80, (50, 200, 50), "door", (20, 100, 20), 2, alpha=200)
        self.wall_image_b64 = generate_simple_image_b64(50, 50, (100, 100, 100), "brick", (50, 50, 50), 1)

        self._initialize_game_elements()

    # --- Initialization and Placement Methods ---

    def _initialize_game_elements(self):
        """Initializes gems, hazards, walls, and exit for the level."""
        self.gems.clear()
        self.hazards.clear()
        self.walls.clear()
        self._next_gem_id = 0
        self.winner = None # Reset winner on re-initialization
        self.black_gems_required = 0
        self.white_gems_required = 0

        logging.info("Server: Initializing competitive game elements.")

        # Walls (outer bounds and platforms)
        self._place_wall(0, self.map_height - 20, self.map_width, 20)
        self._place_wall(0, 0, 20, self.map_height)
        self._place_wall(self.map_width - 20, 0, 20, self.map_height)
        self._place_wall(0, 0, self.map_width, 20)
        self._place_wall(50, 400, self.map_width - 100, 20)
        self._place_wall(150, 300, 100, 20)
        self._place_wall(self.map_width - 250, 300, 100, 20)
        self._place_wall(50, 200, 150, 20)
        self._place_wall(self.map_width - 200, 200, 150, 20)
        self._place_wall(250, 100, 140, 20)

        # Hazards
        self.hazards['white_pool_1'] = {'x': 100, 'y': 420, 'type': 'white', 'width': 60, 'height': 20}
        self.hazards['white_pool_2'] = {'x': 300, 'y': 380, 'type': 'white', 'width': 60, 'height': 20}
        self.hazards['black_pool_1'] = {'x': self.map_width - 160, 'y': 420, 'type': 'black', 'width': 60, 'height': 20}
        self.hazards['black_pool_2'] = {'x': self.map_width - 340, 'y': 200, 'type': 'black', 'width': 60, 'height': 20}

        # Exit area
        self.exit_area = {'x': 280, 'y': 40, 'width': 80, 'height': 80}

        # Gems
        self._place_gem(70, 370, 'black')
        self._place_gem(200, 270, 'black')
        self._place_gem(120, 170, 'black')
        self._place_gem(self.map_width - 120, 370, 'white')
        self._place_gem(self.map_width - 240, 270, 'white')
        self._place_gem(self.map_width - 150, 170, 'white')

    def _place_wall(self, x, y, width, height):
        """Places a wall at a specific coordinate with given dimensions."""
        wall_id = f"wall_{len(self.walls)}"
        self.walls[wall_id] = {'x': x, 'y': y, 'width': width, 'height': height}
        logging.debug(f"Server: Placed wall {wall_id} at ({x}, {y}) with size {width}x{height}")

    def _place_gem(self, x, y, gem_type):
        """Places a gem at a specific coordinate."""
        gem_id = f"{gem_type}_gem_{self._next_gem_id}"
        self._next_gem_id += 1
        self.gems[gem_id] = {'x': x, 'y': y, 'type': gem_type}
        if gem_type == 'black':
            self.black_gems_required += 1
        else:
            self.white_gems_required += 1
        logging.debug(f"Server: Placed {gem_type} gem {gem_id} at ({x}, {y})")
        return gem_id

    # --- Command Processing ---

    def proses_string(self, command_string):
        """
        Processes incoming command strings from clients.
        Expected format: "COMMAND [ARG1] [ARG2] ..."
        Returns a JSON string response.
        """
        logging.info(f"Server: Processing command: {command_string}")
        parts = command_string.strip().split()
        command = parts[0].lower()
        args = parts[1:]
        result = {"status": "ERROR", "message": "Unknown command"}

        with self._lock:
            if command == "register_player":
                if len(args) == 1:
                    player_id = args[0]
                    result = self._register_player(player_id)
                else:
                    result = {"status": "ERROR", "message": "Usage: register_player <player_id>"}

            elif command == "set_player_state":
                if len(args) == 4:
                    player_id, x, y, lives = args
                    try:
                        x, y, lives = int(x), int(y), int(lives)
                        result = self._set_player_state(player_id, x, y, lives)
                    except ValueError:
                        result = {"status": "ERROR", "message": "Invalid state values"}
                else:
                    result = {"status": "ERROR", "message": "Usage: set_player_state <id> <x> <y> <lives>"}

            elif command == "get_game_state":
                result = self._get_game_state()

            elif command == "get_player_info":
                if len(args) == 1:
                    player_id = args[0]
                    result = self._get_player_info(player_id)
                else:
                    result = {"status": "ERROR", "message": "Usage: get_player_info <player_id>"}

            elif command == "collect_gem":
                if len(args) == 2:
                    player_id, gem_id = args
                    result = self._collect_gem(player_id, gem_id)
                else:
                    result = {"status": "ERROR", "message": "Usage: collect_gem <player_id> <gem_id>"}

            elif command == "check_hazard_collision":
                if len(args) == 2:
                    player_id, hazard_id = args
                    result = self._check_hazard_collision(player_id, hazard_id)
                else:
                    result = {"status": "ERROR", "message": "Usage: check_hazard_collision <player_id> <hazard_id>"}

            elif command == "player_at_exit":
                if len(args) == 1:
                    player_id = args[0]
                    result = self._player_at_exit(player_id)
                else:
                    result = {"status": "ERROR", "message": "Usage: player_at_exit <player_id>"}

            elif command == "reset_game":
               logging.info("Server: Full game reset command received.")
               result = self._reset_game()

        logging.debug(f"Server: Responding with: {result.get('status')} - {result.get('message', '')[:50]}...")
        return json.dumps(result)

    # --- Player Management ---

    def _register_player(self, color_choice):
        """Registers a player based on color choice ('black' or 'white')."""
        color_choice = color_choice.lower()
        if color_choice not in ['black', 'white']:
            return {"status": "ERROR", "message": "Invalid color choice. Must be 'black' or 'white'."}

        player_id = f"player_{color_choice}"
        
        # Check if a player with this color already exists
        if player_id in self.players:
            logging.warning(f"Server: Attempt to register an already existing color: {color_choice}.")
            return {"status": "ERROR", "message": f"Player color '{color_choice}' is already taken."}

        if color_choice == 'black':
            initial_x, initial_y = 70, 400 - 64
        else: # white
            initial_x, initial_y = self.map_width - 70 - 64, 400 - 64

        self.players[player_id] = {
            'x': initial_x,
            'y': initial_y,
            'color_type': color_choice,
            'gems_collected': 0,
            'lives': self.default_player_lives,
            'at_exit': False
        }
        logging.info(f"Server: Player {player_id} registered as {color_choice} at ({initial_x}, {initial_y}).")
        return {
            "status": "OK",
            "player_id": player_id,
            "color_type": color_choice,
            "message": f"Player {player_id} registered as {color_choice}.",
            "x": initial_x,
            "y": initial_y
        }

    def _set_player_state(self, player_id, x, y, lives):
        """Updates a player's state (position, lives)."""
        if player_id in self.players:
            self.players[player_id]['x'] = x
            self.players[player_id]['y'] = y
            self.players[player_id]['lives'] = lives
            logging.debug(f"Server: Player {player_id} state updated to ({x},{y}), lives {lives}")
            return {"status": "OK", "message": f"Player {player_id} state updated."}
        else:
            logging.warning(f"Server: Player {player_id} not found during set_player_state.")
            return {"status": "ERROR", "message": f"Player {player_id} not found."}

    def _get_player_info(self, player_id):
        """Returns specific player info including color type and image."""
        if player_id in self.players:
            player_data = self.players[player_id]
            color_type = player_data['color_type']
            face_b64 = self.black_player_image_b64 if color_type == 'black' else self.white_player_image_b64
            logging.debug(f"Server: Providing info for {player_id}, type {color_type}.")
            return {"status": "OK", "color_type": color_type, "face": face_b64}
        else:
            logging.warning(f"Server: Player {player_id} not found during get_player_info.")
            return {"status": "ERROR", "message": "Player not found."}

    # --- Game State ---

    def _get_game_state(self):
        """Returns the complete current game state (players, gems, hazards)."""
        players_data = {
            p_id: {
                'x': p_data['x'],
                'y': p_data['y'],
                'color_type': p_data['color_type'],
                'gems_collected': p_data['gems_collected'],
                'lives': p_data['lives'],
                'at_exit': p_data['at_exit']
            }
            for p_id, p_data in self.players.items()
        }
        gem_list = [
            {'id': g_id, 'x': g_data['x'], 'y': g_data['y'], 'type': g_data['type']}
            for g_id, g_data in self.gems.items()
        ]
        hazard_list = [
            {'id': h_id, 'x': h_data['x'], 'y': h_data['y'], 'type': h_data['type'], 'width': h_data['width'], 'height': h_data['height']}
            for h_id, h_data in self.hazards.items()
        ]
        wall_list = [
            {'id': w_id, 'x': w_data['x'], 'y': w_data['y'], 'width': w_data['width'], 'height': w_data['height']}
            for w_id, w_data in self.walls.items()
        ]
        logging.debug(f"Server: Sending full game state. Players: {len(self.players)}, Gems: {len(self.gems)}, Walls: {len(self.walls)}")
        return {
            "status": "OK",
            "players": players_data,
            "gems": gem_list,
            "hazards": hazard_list,
            "walls": wall_list,
            "exit_area": self.exit_area,
            "black_gem_image_b64": self.black_gem_image_b64,
            "white_gem_image_b64": self.white_gem_image_b64,
            "black_hazard_image_b64": self.black_hazard_image_b64,
            "white_hazard_image_b64": self.white_hazard_image_b64,
            "exit_area_image_b64": self.exit_area_image_b64,
            "wall_image_b64": self.wall_image_b64,
            "black_gems_required": self.black_gems_required,
            "white_gems_required": self.white_gems_required,
            "winner": self.winner 
        }

    # --- Game Actions ---

    def _collect_gem(self, player_id, gem_id):
        """Handles a player collecting a gem of their own color."""
        if self.winner: return {"status": "ERROR", "message": "Game has already ended."}
        if player_id not in self.players or gem_id not in self.gems:
            return {"status": "ERROR", "message": "Player or gem not found."}

        player = self.players[player_id]
        gem = self.gems[gem_id]

        if player['color_type'] == gem['type']:
            player['gems_collected'] += 1
            logging.info(f"Server: Player {player_id} collected {gem['type']} gem {gem_id}. Total: {player['gems_collected']}")
            del self.gems[gem_id]
            # No win check here, win is checked at the exit
            return {"status": "OK", "message": "Gem collected."}
        else:
            return {"status": "ERROR", "message": "Wrong gem color for this character."}

    def _check_hazard_collision(self, player_id, hazard_id):
        """Handles player-hazard collision, which can now result in an instant win for the opponent."""
        if self.winner: return {"status": "ERROR", "message": "Game has already ended."}
        if player_id not in self.players or hazard_id not in self.hazards:
            return {"status": "ERROR", "message": "Player or hazard not found."}

        player = self.players[player_id]
        hazard = self.hazards[hazard_id]
        
        opponent_color = 'white' if player['color_type'] == 'black' else 'black'
        
        # If a player hits the ONOPNENT's hazard color
        if player['color_type'] != hazard['type']:
            player['lives'] = 0
            self.winner = f"player_{opponent_color}" # The opponent wins
            logging.warning(f"Server: Player {player_id} hit wrong hazard. {self.winner} wins!")
            return {"status": "OK", "message": "Hazard hit, game over.", "winner": self.winner}
        else:
            return {"status": "OK", "message": "Safe hazard."}

    def _player_at_exit(self, player_id):
        """Sets a player's at_exit status and checks for win condition."""
        if self.winner: return {"status": "ERROR", "message": "Game has already ended."}
        if player_id in self.players:
            self.players[player_id]['at_exit'] = True
            logging.info(f"Server: Player {player_id} is at the exit.")
            self._check_race_win_condition(player_id)
            return {"status": "OK", "message": f"Player {player_id} is at exit."}
        return {"status": "ERROR", "message": "Player not found."}

    def _check_race_win_condition(self, player_id):
        """Checks if the player who reached the exit has met all conditions to win the race."""
        if self.winner: # Prevent re-assigning winner
            return

        player = self.players[player_id]
        required_gems = self.black_gems_required if player['color_type'] == 'black' else self.white_gems_required
        
        if player['at_exit'] and player['gems_collected'] >= required_gems:
            self.winner = player_id
            logging.warning(f"Server: GAME WON by {player_id}!")

    # --- Reset Methods ---

def _reset_game(self):
        """Resets the entire game to its initial state for a new match."""
        logging.warning(f"Server: Full game reset requested.")
        self._initialize_game_elements()
        
        # Reset all players that might be stored
        for pid_key in list(self.players.keys()):
            player_data = self.players[pid_key]
            if player_data['color_type'] == 'black':
                player_data['x'], player_data['y'] = 70, 400 - 64
            elif player_data['color_type'] == 'white':
                player_data['x'], player_data['y'] = self.map_width - 70 - 64, 400 - 64
            player_data['lives'] = self.default_player_lives
            player_data['gems_collected'] = 0
            player_data['at_exit'] = False
        
        # A better approach for full reset is to clear players and let them re-register
        self.players.clear()
        
        logging.info("Server: Game state has been reset.")
        return {"status": "OK", "message": f"Game state reset."}
