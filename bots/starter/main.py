"""Starter bot - a simple example to demonstrate usage of the Controller API.

Each unit gets its own Player instance; the engine calls run() once per round.
Use Controller.get_entity_type() to branch on what kind of unit you are.

This bot:
- Core: spawns up to 3 builder bots on random adjacent tiles
- Builder bot: builds a harvester on any adjacent ore tile, then moves in a
random direction (laying a road first so the tile is passable), and places
a marker recording the current round number
"""

import heapq

from cambc import Controller, Direction, EntityType, Environment, Position

# non-centre directions
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

class Player:
    def __init__(self):
        self.first_turn = True
        self.bot: Bot

    def run(self, ct: Controller) -> None:
        if self.first_turn:
            etype = ct.get_entity_type()
            if etype == EntityType.CORE:
                self.bot = Core(ct)
            elif etype == EntityType.BUILDER_BOT:
                core_pos: Position
                move_dir = Direction.NORTH
                # Find the core to determine starting coordinates and initial movement direction
                for uID in ct.get_nearby_units():
                    if ct.get_entity_type(uID) == EntityType.CORE:
                        core_pos = ct.get_position(uID)
                        move_dir = ct.get_position().direction_to(core_pos).opposite()
                        break
                self.bot = BuilderBot(ct, core_pos, move_dir)
            
            self.first_turn = False
        
        self.bot.turn_start(ct)
        self.bot.turn_end(ct)
		

class Bot:
	def __init__(self, ct: Controller):
		# Cache map dimensions gloabally for this unit
		self.map_width = ct.get_map_width()
		self.map_height = ct.get_map_height()

		# Initialisation of bitboards for different map features 
		self.walls_board = 0
		self.axionite_ores_board = 0
		self.titanium_ores_board = 0
		self.walkable_board = 0
		# What's a bitboard you ask? Well look no further Motion has got you covered.
		# Essentially we map every tile on the map to a index on a binary number
		# So if we had a 4 tile map a bitboard would look something like 0110 where tile 1 is assigned the value 0 and tile 3 is assigned 1
		# Why use bit boards? Parallel queries. We can check if a tile is a wall by doing a single logical AND between the walls bitboard and a bitmask with a 1 at the index of the tile we want to query. This is much faster than querying the tile environment through the API every time we want to check if a tile is a wall.

		# Run the map scan upon spawn
		self._init_static_bitboards(ct)

	def _init_static_bitboards(self, ct: Controller):
		"""Scans the map and initialises bitboards for walls, ores, and walkable tiles.
		  O(n) where n is the number of tiles on the map. WITHIN THE VISION RANGE (I forgot about the vision constraint)."""
		
		# Unfortunately there is no exploit to query the whole map then save it to a bit board.
		# So we have to scan the visible map tile by tile and set the corresponding bits in the bit boards. This is O(n) where n is the number of tiles in vision range.	
		for pos in ct.get_nearby_tiles():
			# Get the correct index of the bit you are affecting
			index = pos.y * self.map_width + pos.x
			# Moves the bit to the correct index of the bit board. (Tile 34 will be mapped to the 34th index in the binary number for example)
			# The << is the logical left shift operator btw. Left is the input number you want to shift and the right hand side is the number of times you want to shift it
			bit_mask = 1 << index

			env = ct.get_tile_env(pos)

			if env == Environment.WALL:
				# Performs a logical OR to flip the bit to a 1 at the position of the wall in the walls bit board 
				self.walls_board |= bit_mask
			else:
				# As there is no wall here we can set the bit 1 in the walkable bitboard to indicate it is walkable
				self.walkable_board |= bit_mask
				if env == Environment.ORE_TITANIUM:
					# If there is an ore there you flip the bit to 1 to indicate there is ore there (I think you get the gist now)
					self.titanium_ores_board |= bit_mask
				elif env == Environment.ORE_AXIONITE:
					self.axionite_ores_board |= bit_mask
	
	def check_bit(self, bitboard:int, pos: Position) -> bool:
		"""Returns True if the bit at th given position is 1."""
		# Maps the position to the correct index for the bitboard
		# Equation makes sense if you think hard enough. Think of the pos.y as all the completed rows so far
		# then think of pos.x as how far you have made it along the current row.
		index = pos.y * self.map_width + pos.x
		bitmask = 1 << index
		# Does a logical AND of the bitmask and the bitboard. 
		# If it returns anything other than 0 then it returns true.
		# Why does it work? Because every index of the bitboard other than the index you are querying is set to zero.
		# So a logical AND sets all of these bits to zero regardless of it's state.
		# This just leaves the index of the target bit and the index of the of the tile being queried.
		# This leaves a binary (See what I did there) possiblity for the final output: Either the values of the bit at the index or 0.
		return (bitboard & (bitmask)) != 0
	
	def set_bit(self, bitboard: int, pos: Position) -> int:
		"""Turns the bit ON at a given Position and returns the new board."""
		# Still maps the input position to the correct index for the bitboard. Nothing has changed here.
		index = pos.y * self.map_width + pos.x
		bitmask = 1 << index
		# Alright so here we are peforming a logical OR on the bitboard at the index of the tile given.
		# Two things here. As it is an OR it preserves the preserves the other indices in the board (1 OR 0 = 1, 0 OR 0 = 0).
		# The second thing is that if the bit at the index provided is already on (is 1) it remains 1 as 1 OR 1 = 1 (Kind of inferred from the first point but idc).
		return bitboard | bitmask
	
	def clear_bit(self, bitboard: int, pos: Position) -> int:
		"""Turns the bit OFF at the given Postion and returns the new board."""
		# Need I say anymore?
		index = pos.y * self.map_width + pos.x
		bitmask = 1 << index 
		# And with the NOT of the bitmask so everything is flipped.
		# This means that the index of input tile is set to 0 and everything is set to 1. And well 0 AND anything is 0.
		return bitboard & ~(bitmask)
	
	def update_terrain_vision(self, ct:Controller):
		"""Called after moving to map newly revealed terrain."""  
		# This acts as a way to fill in the dark areas of map memory.
		for pos in ct.get_nearby_tiles():
			index = pos.y * self.map_width + pos.x 
			bitmask = 1 << index

			# Skip if we have already mapped this tile
			# This works as at this index the tile is either walkable or not walkable (Crazy right?)
			# Hence the logical OR will always return 1 between the two boards
			# And it is being logical ANDed with the bit mask which is guaranteed to be 1 at this position.
			# In the case that this block has just entered the vision range both boards will be 0 and the logical OR will return 0.
			if (self.walkable_board | self.walls_board) & bitmask:
				continue
			
			env = ct.get_tile_env(pos)
			if env == Environment.WALL:
				self.walls_board |= bitmask
			else:
				self.walkable_board |= bitmask
				if env == Environment.ORE_TITANIUM:
					self.titanium_ores_board |= bitmask
				elif env == Environment.ORE_AXIONITE:
					self.axionite_ores_board |= bitmask

			#sym_x = (self.map_width - 1) - pos.x 
			#sym_y = (self.map_height - 1) - pos.y 
			#sym_index = sym_y * self.map_width + sym_x 
			#sym_bitmask = 1 << sym_index

			#complete_mask = bitmask | sym_bitmask

	def turn_start(self,ct):
		pass

	def turn_end(self, ct):
		pass


class BuilderBot(Bot):
	def __init__(self, ct:Controller, core_pos: Position, move_dir: Direction):
		# Initialises the parent class (Bot) to generate the bit boards and inherit the corresponding variables and functions
		super().__init__(ct)

		self.core_pos = core_pos
		self.move_dir = move_dir
		self.target = None 
		self.conveying = False 
		self.returning = False

		# Bitboard for the buildings
		self.buildings_board = 0
		
		# The ordered list of positions and the corresponding bitboard
		self.path = [] # List[Position] - ordered steps from current position to target
		self.path_index = 0 # How far along the path we are
		self.path_board = None # Bitboard representation of the path for parallel collision detection

	# Static so it can be alled through the class without needing to pass in self
	@staticmethod
	def chebyshev(a: Position, b: Position) -> int:
		"""
		Chebyshev distance - admissible heuristic (Never overestimates the true path length) for 8-directional movement.
		"""
		return max(abs(a.x - b.x), abs(a.y - b.y))
	
	def get_neighbours(self, pos: Position):
		"""
		Returns walkable neighbour positions (non-wall, non-ore, in-bounds)
		Ore is excluded as the bots can not walk on ore.
		"""

		for d in DIRECTIONS:
			# Delta returns the (dx,dy) for a step in the given direction
			nx, ny = pos.x + d.delta()[0], pos.y + d.delta()[1]

			# Bounds check
			if nx < 0 or nx >= self.map_width or ny < 0 or ny >= self.map_height:
				continue
			
			neighbour = Position(nx, ny)
			index = ny * self.map_width + nx 
			bitmask = 1 << index

			# Wall check via bitboard
			
			if (self.walls_board & bitmask) != 0: 
				continue
			# Ore check
			if (self.titanium_ores_board & bitmask) != 0:
				continue
			if (self.axionite_ores_board & bitmask) != 0:
				continue
			
			# Yield turns this function into a function generator. It is queried by a for each loop.
			yield neighbour

	def a_star(self, start: Position, goal: Position):
		"""
		A* search from start to goal.
		
		Returns a list of Positions representing the path (excluding start, including the final walkable tile adjacent to the goal)
		Or None if no path is found
		"""

		# If the goal is ore, we want to reach an adjacent tile, not the ore itself.
		# Check using if the goal is on the bots current ore bitboard
		goal_is_ore = (
			self.check_bit(self.titanium_ores_board, goal) or self.check_bit(self.axionite_ores_board, goal)
		)

		# Open set: The ordered set of tiles yet to be explored.
		# Priority queue of (f_score, tiebreaker, position) f score from the f(n) = g(n) + h(n) equation in the A* definition
		# The tiebreaker (counter) prevent Position comparison when f_scores are equal (the first one will come first)

		counter = 0 
		open_set = []
		heapq.heappush(open_set, (0, counter, start))

		# came_from: maps each position to the position we reached it from (kind of like a linked list)
		came_from = {}

		# g_score : The best known cost from start to each position
		g_score = {start: 0}

		# closed_set: position we have fully expanded
		closed_set = set()

		while open_set:
			f, _, current = heapq.heappop(open_set)

			# Skip if already fully expanded
			if current in closed_set:
				continue

			# Goal check: if the target is ore, we stop when we are adjacent to it.
			# Otherwise we stop when we reach the goal itself.
			if goal_is_ore:
				if current.distance_squared(goal) <= 2:
					return self.reconstruct_path(came_from, current)
			else:
				if current == goal:
					return self.reconstruct_path(came_from, current)
				
			"""
			A note on the reconstruction of the path. Since the heuristic is admissible is it guaranteed that the path taken to get to the current tile is the optimal path. 
			Hence we can reconstruct the optimal path to the target by backtracking through the came_from map from the target to the start.
			If you look below after we add the closed set as we explore all of its adjacent tiles. We then add it's neighbour to the open set using heap pus which orders the open set by the f score. 
			If you look above we pop the tile with the lowest f score then we add that tile to the closed set once again as we look through it's neighbours.
			This means we always explore the tile with the lowest f score first and we never explore a tile more than once. Hence when we reach the target tile we have explored the optimal path to get there and we can reconstruct it using the came_from map.
			"""
				
			closed_set.add(current)

			for neighbour in self.get_neighbours(current):
				if neighbour in closed_set:
					continue
				
				 # Uniform cost of 1 per step for now
				tentative_g = g_score[current] + 1
				
				# Checks if this path to the neighbour is better than any previously recorded path (or if there is no recorded path)
				# The second argument is the default value if neighbour is not in g_score, which is infinity as we want to consider any path to it as better than no path.
				if tentative_g < g_score.get(neighbour, float('inf')):
					came_from[neighbour] = current
					g_score[neighbour] = tentative_g 

					# Heuristic target: if goal is ore, we aim for adjacency (distance 1),
					# so we substract 1 from the chebyshev distance to stay admissible.
					# This is where the magic happens. The heuristic is what differentiates the neighbours. We want to prioritise neighbours that are closer to the target (Chebyshev distance). 
					if goal_is_ore:
						h = max(0, self.chebyshev(neighbour, goal) - 1)
					else:
						h = self.chebyshev(neighbour, goal)

					f_score = tentative_g + h
					counter += 1
					heapq.heappush(open_set, (f_score, counter, neighbour))

		# No path found
		return None


	def reconstruct_path(self, came_from: dict, current: Position):
		"""
		Reconstructs the path from start to current using the came_from map.
		Returns the path as a list of Positions, excluding the start position.
		"""

		path = []
		while current in came_from:
			path.append(current)
			current = came_from[current]
		
		path.reverse()
		return path
	
	def compute_path(self, start: Position, goal: Position):
		"""
		Runs A* and stores the result as noth a position list and a path bitboard.
		"""
		result = self.a_star(start, goal)

		if result is None:
			self.path = []
			self.path_index = 0
			self.path_board = 0
			return False
		
		self.path = result
		self.path_index = 0

		# Build the path bitboard for collision detection later 
		self.path_board = 0
		for pos in self.path:
			self.path_board = self.set_bit(self.path_board, pos)

		return True
	
	def check_path_collisions(self) -> bool:
		"""
		Returns True if any obstacle now overlaps the remaining path.
		"""

		remaining_board = 0
		# The : after self.path_index is string slicing to get the remaining path from the current position to the target
		for pos in self.path[self.path_index:]:
			remaining_board = self.set_bit(remaining_board, pos)

		# AND with walls - non-zero, a wall is blocking the path
		return (remaining_board & self.walls_board) != 0

	def follow_path(self, ct: Controller) -> bool:
		""" Takes one step along the cached path. Returns True if a step was taken."""
		if ct.get_move_cooldown() > 0:
			return False
		
		if self.path_index >= len(self.path):
			return False
		
		next_pos = self.path[self.path_index]
		current_pos = ct.get_position()
		direction = current_pos.direction_to(next_pos)

		# Build a road on the target if needed
		if ct.get_action_cooldown() == 0 and ct.can_build_road(next_pos):
			ct.build_road(next_pos)
			
		# Take the step
		if ct.can_move(direction):
			ct.move(direction)
			self.path_index += 1
			return True
		
		return False
	
	def find_nearest_ore(self, ct: Controller) -> Position | None:
		"""Scans visible tile for the nearest ore deposit."""

		current_pos = ct.get_position()
		best_pos = None 
		best_dist = float('inf')

		for pos in ct.get_nearby_tiles():
			env = ct.get_tile_env(pos)
			if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
				dist = self.chebyshev(current_pos, pos)
				if dist < best_dist:
					best_dist = dist
					best_pos = pos
		
		return best_pos
	
	def turn_start(self, ct: Controller):
		# Update our map with any newly visible terrain
		self.update_terrain_vision(ct)

		current_pos = ct.get_position()

		# If we have no target, look for ore

		if self.target is None:
			ore_pos = self.find_nearest_ore(ct)
			if ore_pos:
				self.target = ore_pos
				self.compute_path(current_pos, self.target)
			else:
				# No ore visible - explore by moving in the bots assigned direction.
				# Buiild a road and step if we can.
				next_pos = current_pos.add(self.move_dir)
				if(0 <= next_pos.x < self.map_width and 0 <= next_pos.y < self.map_height and not self.check_bit(self.walls_board, next_pos)):
					if (ct.get_action_cooldown() == 0 and ct.can_build_road(next_pos)):
						ct.build_road(next_pos)
					if ct.can_move(self.move_dir):
						ct.move(self.move_dir)

				else:
					# Hit a wall or map edge - rotate and try again next turn
					self.move_dir = self.move_dir.rotate_right()
				return
			
		# We have a target, are we adjacent to it?
		if current_pos.distance_squared(self.target) <= 2:
			if ct.get_action_cooldown() == 0 and ct.can_build_harvester(self.target):
				ct.build_harvester(self.target)
				self.target = None # Clear target to look for a new ore next turn
				self.path = [] # Clear path as well
				self.path_board = 0
			return
		
		# Check if the current cached path has been blocked
		if self.path and self.check_path_collisions():
			# Path is blocked, need to recompute
			self.compute_path(current_pos, self.target)

		# If path is valid follow it
		if self.path and self.path_index < len(self.path):
			self.follow_path(ct)
		else:
			# No valid path - try recomputing (maybe we have seen new terrain)
			if self.compute_path(current_pos, self.target):
				self.follow_path(ct)

class Core(Bot):
	def __init__(self, ct: Controller):
		super().__init__(ct)
		self.num_spawned = 0
		self.spawn_d = Direction.NORTH

	def turn_start(self, ct: Controller):
		if self.num_spawned < 4:
			spawn_pos = ct.get_position().add(self.spawn_d)
			# Rotate 90 degrees for the next spaw so that bots fan out
			self.spawn_d=self.spawn_d.rotate_left().rotate_left()
			if ct.can_spawn(spawn_pos):
				ct.spawn_builder(spawn_pos)
				self.num_spawned += 1


