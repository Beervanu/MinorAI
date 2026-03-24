from math import log2, floor
from typing import TypedDict, Any, Callable
import heapq
from enum import Enum, IntEnum
from cambc import Controller, Direction, EntityType, Environment, Position
import time
from ctypes import LittleEndianStructure, Union, c_uint32

# non-centre directions
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
CARDINAL_DIRECTIONS = [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]


class GenericTask(Enum):
	NOTHING = 'Nothing'

class BuilderTask(Enum):
	FIND_ORE = 'FindOre'
	BUILD_BRIDGE = 'BuildBridge'
	FOUND_TI_ORE = 'FoundTiOre'
	FOUND_AX_ORE = 'FoundAxOre'
	FIND_ENEMY_CORE = 'FindEnemyCore'
	GOTO_ENEMY_CORE = 'GotoEnemyCore'
	ATTACK_ENEMY_CORE = 'AttackEnemyCore'
	FOUND_CORE = 'FoundCore'

type Task = BuilderTask | GenericTask
class TaskData(TypedDict):
	type: Task
	data: Any

class MapSymmetry(IntEnum):
	ROTATIONAL = 1
	REFLECTION_X = 2
	REFLECTION_Y = 3
	UNKNOWN = 0

# Ok so the central marker is the one that our core places on its top left at the start of the game
# It will be used to hold key information, it's split into different fields

class CentralMarkerBits(LittleEndianStructure):
    _fields_ = [
		# Bits 0-11
		# date
		# When this information was last updated
		("date", c_uint32, 12),
		# Bits 12-15
		# known_map_symmetry
		# Once we have deduced the symmetry of the map, we put it here.
		# Every bot that sees this will know to stop searching for the enemy core.
		# Then we can coordinate attacks etc.
        ("known_map_symmetry", c_uint32, 4),
		# Bits 16-31
		# Unused so far.
        ("unused", c_uint32, 16)
    ]

class CentralMarkerData(Union):
    _fields_ = [("b", CentralMarkerBits), ("as_int", c_uint32)]

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
		self.task: TaskData = {'type': GenericTask.NOTHING, 'data': None}
		self.task_backlog: list[TaskData] = []
		self.task_priority: dict[Task, int]	
		# Initialisation of bitboards for different map features
		self.seen_board = 0
		self.walls_board = 0
		self.axionite_ores_board = 0
		self.titanium_ores_board = 0
		self.walkable_board = 0
		self.team_buildings_board = 0
		self.enemy_buildings_board = 0
		self.team_bridges_board = 0
		self.units_board = 0
		
		# 1 1 1
		# 1 0 1 mask
		# 1 1 1 
		self.direct_neighbour_mask = self.generate_mask([0b111, 0b101,0b111])
		# 1
		# 1 mask
		# 1
		self.direct_neighbour_vertical_mask = self.generate_mask([0b1]*3)

		# 1 1 1 mask
		self.direct_neighbour_horizontal_mask = 0b111

		self.bridge_neighbour_mask = self.generate_mask([
			0b0001000, 
			0b0111110, 
			0b0111110,
			0b1110111,
			0b0111110,
			0b0111110,
			0b0001000,])
		
		self.bridge_neighbour_vertical_mask = self.generate_mask([0b1]*7)
		self.bridge_neighbour_horizontal_mask = 0b1111111

		self.map_symmetry = MapSymmetry.UNKNOWN

		self.central_marker_data = CentralMarkerData()

		# What's a bitboard you ask? Well look no further Motion has got you covered.
		# Essentially we map every tile on the map to a index on a binary number
		# So if we had a 4 tile map a bitboard would look something like 0110 where tile 1 is assigned the value 0 and tile 3 is assigned 1
		# Why use bit boards? Parallel queries. We can check if a tile is a wall by doing a single logical AND between the walls bitboard and a bitmask with a 1 at the index of the tile we want to query. This is much faster than querying the tile environment through the API every time we want to check if a tile is a wall.

		# Run the map scan upon spawn
		self.update_terrain_vision(ct)
		

	def generate_mask(self, arr: list[int])->int:
		mask = 0
		for i in range(len(arr)):
			mask+=arr[i]<<(self.map_width*i)
		return mask

	def closest_point(self, point:Position, arr:list[Position])->Position:
		best_pos = None 
		best_dist = float('inf')
		for pos in arr:
			dist = point.distance_squared(pos)
			if dist< best_dist:
				best_dist = dist
				best_pos = pos
		if not best_pos:
			raise Exception('no closest point')
		return best_pos

	def pop_lsb(self, bitboard:int)-> tuple[int, Position]:
		"""Gets the 1-lsb from a bitboard and then returns the bitboard with that bit set to 0 and the extracted position."""
		# bitboard & -bitboard to isolate the 1-lsb
		isolated_bit = bitboard & -bitboard
		# gets the index
		index = int(log2(isolated_bit))
		# removes the bit we just processed
		bitboard &= ~isolated_bit
		return (bitboard, Position(index % self.map_width,floor(index/self.map_width)))
	
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
		print("Updating terrain vision")
		self.units_board = 0
		for id in ct.get_nearby_units():
			if ct.get_entity_type(id) == EntityType.BUILDER_BOT or ct.get_team() != ct.get_team(id):
				pos = ct.get_position(id)
				if pos == ct.get_position():
					continue
				self.units_board = self.set_bit(self.units_board, ct.get_position(id))

		for pos in ct.get_nearby_tiles():
			# Skip if we have already mapped this tile as a wall (it cant change to anything else)
			if self.check_bit(self.walls_board,pos):
				continue
			

			# Jose has changed the logic of this function and did not update the corresponding comments btw 💔.
			# The change is we now have a seen board which essentially did what I already did but it a more compact way.
			env = ct.get_tile_env(pos)
			if not self.check_bit(self.seen_board, pos):
				if env == Environment.WALL:
					self.walls_board = self.set_bit(self.walls_board,pos)
				elif env == Environment.EMPTY:
					self.walkable_board = self.set_bit(self.walkable_board, pos)
				elif env == Environment.ORE_TITANIUM:
					self.titanium_ores_board = self.set_bit(self.titanium_ores_board,pos)
					if isinstance(self, BuilderBot):
						self.add_task(BuilderTask.FOUND_TI_ORE, pos)
				elif env == Environment.ORE_AXIONITE:
					self.axionite_ores_board = self.set_bit(self.axionite_ores_board,pos)
					# if isinstance(self, BuilderBot):
					# 	self.add_task(BuilderTask.FOUND_AX_ORE, pos)
				self.seen_board = self.set_bit(self.seen_board, pos)
				
			
			#update buildings on a tile (need to do this for all non wall tiles every time)
			if ct.is_tile_passable(pos):
				self.walkable_board = self.set_bit(self.walkable_board, pos)
			building_id = ct.get_tile_building_id(pos)
			if building_id:
				etype = ct.get_entity_type(building_id)
				is_team: bool = ct.get_team() == ct.get_team(building_id)
				if is_team:
					self.team_buildings_board= self.set_bit(self.team_buildings_board, pos)
					if etype == EntityType.BRIDGE:
						self.team_bridges_board = self.set_bit(self.team_bridges_board,pos)
				else:
					self.enemy_buildings_board= self.set_bit(self.enemy_buildings_board, pos)
					if etype == EntityType.CORE:
						self.walkable_board = self.clear_bit(self.walkable_board, pos)

		if self.map_symmetry == MapSymmetry.UNKNOWN:
			self.check_symmetry()
		print(f'Map Symmetry: {self.map_symmetry}')

		for ent in ct.get_nearby_entities():
			if ct.get_entity_type(ent) == EntityType.MARKER:
				self.read_central_marker(ct, ent)


	def turn_start(self,ct):
		pass

	def turn_end(self, ct):
		pass

	def add_task(self, task: Task, data: object)->bool:
		"""Adds the given task, and decides whether to execute the task based on its priority. Returns True if we are switching to that task, False if not """
		#if no task, switch to that task
		if not self.task:
			self.task = {'type':task, 'data':data}
			return True
		# else add it to backlog
		self.task_backlog.append({"type":task, "data":data})
		self.task_backlog.sort(key=lambda x: self.task_priority[x['type']])
		return False
	
		# # if higher task priority, bench the current task and switch to it
			# if self.task_priority[self.task['type']] < self.task_priority[task]:
			# 	self.task_backlog.insert(0, self.task)
			# 	self.task = {'type':task, 'data':data}
			# 	return True

	def task_complete(self,ct:Controller):
		print(f'Completed Task: {self.task['type']}, Data: {self.task['data']}')
		if self.task_backlog:
			self.task = self.task_backlog.pop(0)
		else:
			self.task = {'type':BuilderTask.FIND_ORE,'data': None}
		print(f'New Task: {self.task['type']}, Data: {self.task['data']}')

	def rotational_flip(self, board:int) -> int:
		total_bits = self.map_width * self.map_height
		# bin(board) converts the bitboard to a binary string,
		# [2:] removes the '0b' prefix,
		# zfill pads it with leading zeros to ensure it has a length equal to the total number of bits, 
		# [::-1] reverses the string to achieve the rotational flip, 
		# and int(..., 2) converts it back to an integer.
		return int(bin(board)[2:].zfill(total_bits)[::-1], 2)
	
	def horizontal_flip(self, board:int) -> int:
		result = 0
		row_mask = (1 << self.map_width) - 1
		for y in range(self.map_height):
			row = (board >> (y * self.map_width)) & row_mask
			reversed_row = int(bin(row)[2:].zfill(self.map_width)[::-1], 2)
			result |= reversed_row << (y * self.map_width)
		return result

	def vertical_flip(self, board:int) -> int:
		result = 0
		row_mask = (1 << self.map_width) - 1
		for y in range(self.map_height):
			row = (board >> (y * self.map_width)) & row_mask
			reversed_row = int(bin(row)[2:].zfill(self.map_width), 2)
			result |= reversed_row << ((self.map_height - 1 - y) * self.map_width)
		return result
	
	def check_symmetry(self) -> None:
		"""Checks the symmetry of the map based on the currently seen terrain. Sets the map_symmetry variable accordingly."""
		features = self.walls_board | self.axionite_ores_board | self.titanium_ores_board
		if features == 0:
			return  # nothing to compare yet

		checks = [
			(MapSymmetry.ROTATIONAL,   self.rotational_flip),
			(MapSymmetry.REFLECTION_Y, self.horizontal_flip),
			(MapSymmetry.REFLECTION_X, self.vertical_flip),
		]
		possible = []
		for sym, flip_fn in checks:
			flipped_seen = flip_fn(self.seen_board)
			both_seen    = self.seen_board & flipped_seen
			wall_diff    = both_seen & (self.walls_board ^ flip_fn(self.walls_board))
			ore_diff     = both_seen & (features ^ flip_fn(features))
			if (wall_diff | ore_diff) == 0:
				possible.append(sym)

		if len(possible) == 1:
			self.map_symmetry = possible[0]

	def apply_symmetry(self, pos: Position) -> Position:
		"""Applies the map symmetry to a given position to get the corresponding position on the other side of the map."""
		if self.map_symmetry == MapSymmetry.ROTATIONAL:
			return Position(self.map_width - 1 - pos.x, self.map_height - 1 - pos.y)
		elif self.map_symmetry == MapSymmetry.REFLECTION_Y:
			return Position(self.map_width - 1 - pos.x, pos.y)
		elif self.map_symmetry == MapSymmetry.REFLECTION_X:
			return Position(pos.x, self.map_height - 1 - pos.y)
		else:
			raise Exception('Map symmetry unknown')	
	
	def read_central_marker(self, ct: Controller, entity):
		read = CentralMarkerData()
		if ct.get_team(entity) == ct.get_team():
			read.as_int = ct.get_marker_value(entity)
			if self.central_marker_data.b.date > read.b.date: 
				# My one is newer - overwrite
				if ct.can_place_marker(ct.get_position(entity)):
					ct.place_marker(ct.get_position(entity), self.central_marker_data.as_int)
			elif self.central_marker_data.b.date < read.b.date:
				# My one is older - replace internal data with this new one
				self.central_marker_data.as_int = read.as_int

				self.map_symmetry = self.central_marker_data.b.known_map_symmetry

class BuilderBot(Bot):
	def __init__(self, ct:Controller, core_pos: Position, move_dir: Direction):
		# Initialises the parent class (Bot) to generate the bit boards and inherit the corresponding variables and functions
		
		#must generate before calling super()
		#most to least priority
		priority_list = [BuilderTask.ATTACK_ENEMY_CORE, BuilderTask.GOTO_ENEMY_CORE, BuilderTask.FOUND_CORE, BuilderTask.FIND_ENEMY_CORE,BuilderTask.BUILD_BRIDGE, BuilderTask.FOUND_AX_ORE, BuilderTask.FOUND_TI_ORE, BuilderTask.FIND_ORE]
		#generate lookup table for task priorities
		self.task_priority = {}
		for i in range(len(priority_list)):
			self.task_priority[priority_list[i]] = i
		
		super().__init__(ct)
		self.core_pos = core_pos
		self.enemy_core_pos = None
		self.move_dir = move_dir
		self.target = None
		self.target_radius = 2
		self.conveying = False 
		self.returning = False
		#task 
		
		# The ordered list of positions and the corresponding bitboard
		self.bridge_path = []
		self.bridge_path_index = 0
		self.bridge_path_board = None
		self.path = [] # List[Position] - ordered steps from current position to target
		self.path_index = 0 # How far along the path we are
		self.path_board = None # Bitboard representation of the path for parallel collision detection

		
		#which tasks should aim adjacent to their target when path-finding
		adjacent_tasks = [BuilderTask.GOTO_ENEMY_CORE, BuilderTask.FOUND_CORE, BuilderTask.FIND_ENEMY_CORE, BuilderTask.FOUND_AX_ORE, BuilderTask.FOUND_TI_ORE, BuilderTask.BUILD_BRIDGE]
		#generate aim adjacent lookup table
		self.tasks_adjacent_aim = {}
		for t in BuilderTask:
			self.tasks_adjacent_aim[t] = t in adjacent_tasks
		if ct.get_current_round() >= 50:
			self.add_task(BuilderTask.FIND_ENEMY_CORE, 0)
			
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
		neighbour_bit_mask = self.direct_neighbour_mask
		
		#if we are on the edge, remove the mask that extends beyond that edge
		if pos.x == 0:
			neighbour_bit_mask &= ~self.direct_neighbour_vertical_mask
		elif pos.x == self.map_width-1:
			neighbour_bit_mask &= ~(self.direct_neighbour_vertical_mask<<2)
		
		if pos.y==0:
			neighbour_bit_mask &= ~self.direct_neighbour_horizontal_mask
		elif pos.y == self.map_height-1:
			neighbour_bit_mask &= ~(self.direct_neighbour_horizontal_mask<<(self.map_width*2))

		index = pos.y*self.map_width + pos.x
		neighbour_bit_mask<<=index
		# shift to recenter bitmask on index - order is important, else we might delete part of the mask
		neighbour_bit_mask >>= self.map_width + 1
		
		neighbours = (self.walkable_board|(~self.seen_board)) & neighbour_bit_mask & (~self.units_board)
		while neighbours:
			(neighbours, nb) = self.pop_lsb(neighbours)
			yield nb

	def get_bridge_neighbours(self, pos: Position):
		"""
		Returns bridge-buildable neighbour positions (non-wall, non-ore, in-bounds)
		Ore is excluded as the bots can not walk on ore.
		"""
		neighbour_bit_mask = self.bridge_neighbour_mask

		#if we are on the edge, remove the mask that extends beyond that edge
		if pos.x <3:
			remove_mask = 0
			for i in range(3-pos.x):
				remove_mask |= self.bridge_neighbour_vertical_mask<<i
			neighbour_bit_mask &= ~remove_mask
		elif pos.x >= self.map_width-3:
			remove_mask = 0
			for i in range(3-(self.map_width-1-pos.x)):
				remove_mask |= self.bridge_neighbour_vertical_mask<<(4+i)
			neighbour_bit_mask &= ~(remove_mask)
		
		if pos.y==0:
			remove_mask = 0
			for i in range(3-pos.y):
				remove_mask |= self.bridge_neighbour_horizontal_mask<<(self.map_width*i)
			neighbour_bit_mask &= ~remove_mask
		elif pos.y == self.map_height-1:
			remove_mask = 0
			for i in range(3-(self.map_width-1-pos.y)):
				remove_mask |= self.bridge_neighbour_horizontal_mask<<(self.map_width*(4+i))
			neighbour_bit_mask &= ~(self.bridge_neighbour_mask)
		index = pos.y*self.map_width + pos.x
		neighbour_bit_mask<<=index
		# shift to recenter bitmask on index - order is important, else we might delete part of the mask
		neighbour_bit_mask >>= self.map_width*3 + 3
		neighbours = (self.walkable_board|self.team_bridges_board|(~self.seen_board)) & neighbour_bit_mask & (~self.enemy_buildings_board)
		while neighbours:
			(neighbours, nb) = self.pop_lsb(neighbours)
			yield nb

	def a_star(self, start: Position, goal: Position, bridge:bool =False):
		"""
		A* search from start to goal.
		
		Returns a list of Positions representing the path (excluding start, including the final walkable tile adjacent to the goal)
		Or None if no path is found
		"""

		neighbour_function = self.get_neighbours
		if bridge:
			neighbour_function = self.get_bridge_neighbours

		# If we want to aim adjacent to our target
		aim_adjacent = self.tasks_adjacent_aim[self.task['type']] and not bridge

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

			# Goal check: if we are aiming adjacent to our target, we stop when we are adjacent to it.
			# Otherwise we stop when we reach the goal itself.
			if aim_adjacent:
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
			for neighbour in neighbour_function(current):
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
					if aim_adjacent:
						h = max(0, self.chebyshev(neighbour, goal) - 1)
					else:
						h = self.chebyshev(neighbour, goal)
					
					#not a bridge building path and there is no road there
					# if not bridge and not self.check_bit(self.team_buildings_board| self.enemy_buildings_board, neighbour):
					# 	h+=0.5
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
		result = self.a_star(start, goal, False)
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
	
	def compute_bridge_path(self, start:Position, goal:Position):
		"""
		Runs A* and stores the result as noth a position list and a path bitboard.
		"""
		result = self.a_star(start, goal, True)
		if result is None:
			self.bridge_path = []
			self.bridge_path_index = 0
			self.bridge_path_board = 0
			return False
		
		self.bridge_path =[start]+ result
		self.path_index = 0

		# Build the path bitboard for collision detection later 
		self.bridge_path_board = 0
		for pos in self.bridge_path:
			self.bridge_path_board = self.set_bit(self.bridge_path_board, pos)

		return True

	def check_path_collisions(self, path, index, bridge=False) -> bool:
		"""
		Returns True if any obstacle now overlaps the remaining path.
		"""

		remaining_board = 0
		# The : after self.path_index is string slicing to get the remaining path from the current position to the target
		for pos in path[index:]:
			remaining_board = self.set_bit(remaining_board, pos)

		# AND with walls - non-zero, a wall is blocking the path
		mask = self.walls_board
		# if we are building a bridge, avoid enemy roads
		if bridge:
			mask |= self.enemy_buildings_board
		#otherwise avoid our own units
		else:
			mask |= self.units_board
		return (remaining_board & mask) != 0

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
			self.update_terrain_vision(ct)
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
				building_id = ct.get_tile_building_id(pos)
				if building_id:
					if ct.get_team(building_id) == ct.get_team():
						continue
					else:
						continue
						#TODO what do we do when we encounter enemy harvesters
				dist = self.chebyshev(current_pos, pos)
				if dist < best_dist:
					best_dist = dist
					best_pos = pos
		return best_pos
	
	def find_enemy_core(self, ct: Controller) -> Position | None:
		"""
		Scans visible tiles for the enemy core.
		If found returns the postion of the enemy core.
		"""
		enemy_core_pos = None

		for pos in ct.get_nearby_tiles():
			building_id = ct.get_tile_building_id(pos)
			if building_id and ct.get_entity_type(building_id) == EntityType.CORE and ct.get_team(building_id) != ct.get_team():
				enemy_core_pos = pos
				break	
		
		return enemy_core_pos
	
	def turn_start(self, ct: Controller):
		print(f'Task: {self.task['type']}, Data: {self.task['data']}, Backlog: {self.task_backlog}')
		# Update our map with any newly visible terrain
		self.update_terrain_vision(ct)

		keep_processing_tasks = True
		while (keep_processing_tasks):
			current_pos = ct.get_position()
			if self.target is None:
				keep_processing_tasks = self.process_tasks(ct)
				continue
			elif not self.path:
				self.compute_path(current_pos, self.target)
			# Check if the current cached path has been blocked
			if self.path and self.check_path_collisions(self.path, self.path_index):
				# Path is blocked, need to recompute
				self.compute_path(current_pos, self.target)

			# If path is valid follow it
			if self.path and self.path_index < len(self.path):
				self.follow_path(ct)
			else:
				# No valid path - try recomputing (maybe we have seen new terrain)
				if self.compute_path(current_pos, self.target):
					self.follow_path(ct)
			
			keep_processing_tasks = self.process_tasks(ct)
		print(f"Path: {self.path}")
		if self.path:
			self.draw_path(ct, self.path, self.path_index)
			

	def draw_path(self, ct:Controller, path, path_index, ):
		increase = 50
		col=255
		for pos in path[path_index:]:
			col-=increase
			col = max(col, 0)
			ct.draw_indicator_dot(pos, col,col,col)

	def process_tasks(self, ct:Controller):
		"""Processes the current task, returning True if we should continue processing"""
		self.target: Position
		current_pos = ct.get_position()
		reached_target = not self.target is None and current_pos.distance_squared(self.target) <=self.target_radius
		match self.task['type']:
			case GenericTask.NOTHING:
				self.add_task(BuilderTask.FIND_ORE, None)
				self.task_complete(ct)
				return True
			# TODO: SEARCH for ORE - better search pattern
			case BuilderTask.FIND_ORE:
				if self.task_backlog:
					self.task_complete(ct)
					return True
				# No ore visible - explore by moving in the bots assigned direction.
				# Build a road and step if we can.

				next_pos = current_pos.add(self.move_dir)
				if(0 <= next_pos.x < self.map_width and 0 <= next_pos.y < self.map_height and not self.check_bit(self.walls_board, next_pos)):
					if (ct.get_action_cooldown() == 0 and ct.can_build_road(next_pos)):
						ct.build_road(next_pos)
					if ct.can_move(self.move_dir):
						ct.move(self.move_dir)

				else:
					# this is dog
					# Hit a wall or map edge - rotate and try again next turn
					self.move_dir = self.move_dir.rotate_right()
			case BuilderTask.FOUND_AX_ORE | BuilderTask.FOUND_TI_ORE:
				if self.target is None:
					self.change_target(self.task['data'])
				if self.check_bit(self.team_buildings_board, self.target):
					self.task_complete(ct)
					return True
				elif self.check_bit(self.enemy_buildings_board, self.target):
					#TODO: if an ore is occupied by opposite team destroy it or something - need a team buildings board
					self.task_complete(ct)
					return True
				if reached_target:
					if ct.get_action_cooldown() == 0 and ct.can_build_harvester(self.target):
						ct.build_harvester(self.target)
						# TODO: Choose a direction from which to build a bridge from properly - this will error when we try to build from an ore on the top of the map
						# TODO: build to nearest bridge instead of core - (check if bridge gets congested) - second task to decongest bridges ?
						# TODO: protect harvesters with walls around
						# TODO: symmetry stuff
						# TODO: patrol bots for conveyors - have a report time to core - if they are late send another patrol
						# TODO: add path-finding around bots (probably need to place a marker)
						all_dir = [self.target.add(d) for d in CARDINAL_DIRECTIONS]
						all_dir.sort(key=lambda dir: self.chebyshev(self.core_pos, dir))
						for pos in all_dir:
							if 0<=(pos.x)<self.map_width and 0<=pos.y<self.map_height and self.check_bit(self.walkable_board, pos):

								self.add_task(BuilderTask.BUILD_BRIDGE, pos)
								break
						self.task_complete(ct)
						return True
			case BuilderTask.BUILD_BRIDGE:
				
				if not self.bridge_path or self.check_path_collisions(self.bridge_path, self.bridge_path_index, True):
					#if this is our fi
					if not self.bridge_path:
						bridge_start: Position = self.task['data']
					else:
						# TODO: need logic to stop an error if we build a bridge that points initially to an empty space, then gets built over by an enemy bot
						bridge_start = self.bridge_path[self.bridge_path_index]
					core_dirs= [self.core_pos.add(d) for d in DIRECTIONS]
					closest = self.closest_point(bridge_start, core_dirs)
					# TODO: need to make sure bridges dont get congested
					# team_bridges = self.team_bridges_board
					
					# while (team_bridges):
					# 	(team_bridges, pos) = self.pop_lsb(team_bridges)
					# 	dist = bridge_start.distance_squared(pos)
					# 	if dist<best_dist:
					# 		best_dist=dist
					# 		best_pos=pos
					self.compute_bridge_path(bridge_start, closest)
				
					self.change_target(self.bridge_path[0])
				if reached_target:
					#get rid of roads in the way
					building_id = ct.get_tile_building_id(self.target)
					if building_id:
						etype = ct.get_entity_type(building_id)
						if etype == EntityType.ROAD and ct.can_destroy(self.target):
							ct.destroy(self.target)
						# if we accidentally build on a team bridge we did good
						elif etype == EntityType.BRIDGE and ct.get_team(building_id) == ct.get_team():
							self.task_complete(ct)
							return True
						elif etype == EntityType.CORE:
							self.task_complete(ct)
							return True

					#try to build the bridge		
					if ct.get_action_cooldown() == 0 and ct.can_build_bridge(self.target, self.bridge_path[self.bridge_path_index+1]):
						ct.build_bridge(self.target, self.bridge_path[self.bridge_path_index+1])
						self.bridge_path_index+=1
						if self.bridge_path_index == len(self.bridge_path)-1:
							#TODO: spawn a protector bot?

							self.task_complete(ct)
							return True
						self.change_target(self.bridge_path[self.bridge_path_index])
			case BuilderTask.FIND_ENEMY_CORE:
				if self.target is None:
					# Check if the enemy core is within visible range first
					self.enemy_core_pos = self.find_enemy_core(ct)
					if self.enemy_core_pos:
						# If it witnin visible range, set it as the target and switch to report back to base
						self.change_target(self.enemy_core_pos)
						self.add_task(BuilderTask.FOUND_CORE, self.core_pos)
						self.task_complete(ct)
						return True
					else:
						# No enemy core in sight - move to one of the possible symmetry positions for the enemy core to try to find it
						# This is based on the fact that the map will always be symmetric with respect to the center either by either rotation or reflection, so the enemy core must be in one of the 3 positions that are symmetric to our core position.
						
						if self.map_symmetry != MapSymmetry.UNKNOWN:
							self.enemy_core_pos = self.apply_symmetry(self.core_pos)
							self.change_target(self.enemy_core_pos)
							self.add_task(BuilderTask.GOTO_ENEMY_CORE, self.core_pos)
							self.task_complete(ct)
							return False
						

						# The first position is the one symmetric to our core across x and y, the second is symmetric across the y axis and the third is symmetric across the x axis. We sort these positions by distance from our current position to prioritise the closest one first.
						# Recomputed each time 😔 literally takes microseconds but I should probably move this but I am lazy.
						symmetry_positions = [
							Position((self.map_width-1) - self.core_pos.x, (self.map_height-1) - self.core_pos.y), 
							Position(self.map_width-1  - self.core_pos.x, self.core_pos.y),
							Position(self.core_pos.x, self.map_height-1 - self.core_pos.y)]
						
						symmetry_positions.sort(key=lambda pos: self.chebyshev(current_pos, pos))
						self.change_target(symmetry_positions[self.task['data']])
						return True
				elif reached_target:	
					# Getting to point implies that the core is not there, so we can move on to the next possible core position or repeat if we have checked all of them
					if self.map_symmetry == MapSymmetry.UNKNOWN:
						if self.task['data'] < 2:
							self.task['data']+=1
							self.change_target(None)
							return True
						else:
							# We have checked all possible symmetry positions and have not found the enemy core - it's not looking good. Look for ore instead.
							self.task_complete(ct)
					# We have reached one of the possible symmetry positions and the core is not there but we have ascertained the symmetry of the map, so we can deduce the position of the enemy core based on our core position and the map symmetry and switch to attack task
					else:
						self.enemy_core_pos = self.apply_symmetry(self.core_pos)
						self.add_task(BuilderTask.FOUND_CORE, self.core_pos)
						self.task_complete(ct)
				else:
					# Still trying to reach the target to check for the core, keep processing this task but also check for symmetry as we go to potentially speed up the process
					if self.map_symmetry != MapSymmetry.UNKNOWN:
						# We have ascertained the symmetry of the map, so we can deduce the position of the enemy core based on our core position and the map symmetry and switch to attack task
						self.enemy_core_pos = self.apply_symmetry(self.core_pos)
						self.add_task(BuilderTask.FOUND_CORE, None)

						# This updates my internal memory of the map symmetry, attached to the round I discovered it
						# Will be able to overwrite the core's marker system

						self.central_marker_data.b.date = ct.get_current_round()
						self.central_marker_data.b.known_map_symmetry = self.map_symmetry

						self.task_complete(ct)
			case BuilderTask.FOUND_CORE:
				# FOUND_CORE is now the task which tells the bot to go back and update central markers
				# The task for going to the enemy core to attack it is now GOTO_ENEMY_CORE and retains its functionality
				if self.target is None:
					self.change_target(self.core_pos, 9)
					return True
				if reached_target:
					self.add_task(BuilderTask.GOTO_ENEMY_CORE, None)
					self.task_complete(ct)
					return True
			case BuilderTask.GOTO_ENEMY_CORE:
				if self.target is None:
					self.change_target(self.enemy_core_pos, 3)
					return True
				if reached_target:
					self.add_task(BuilderTask.ATTACK_ENEMY_CORE, None)
					self.task_complete(ct)
					return True
			case BuilderTask.ATTACK_ENEMY_CORE:
				if self.target is None:
					for id in ct.get_nearby_buildings():
						etype = ct.get_entity_type(id)
						if etype == EntityType.BRIDGE and ct.get_team(id) != ct.get_team():
							self.change_target(ct.get_position(id), 0)
							return True
				if reached_target:
					ct.self_destruct()
				
				# Need to add logic to start destroying the core with turrets and stuff.
		return False
	
		

	def task_complete(self, ct:Controller):
		#reset the paths upon task completion
		self.target = None
		self.reset_bridge_path()
		self.reset_path()
		super().task_complete(ct)
	
	def reset_path(self):
		self.path = []
		self.path_index = 0
		self.path_board = 0
	
	def reset_bridge_path(self):
		self.bridge_path = []
		self.bridge_path_index =0
		self.bridge_path_board =0
	
	def change_target(self, target:Position, radius=2):
		self.reset_path()
		self.target = target
		self.target_radius = radius
		
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
		round = ct.get_current_round()
		if  round >= 50 and not round %500:
			# Spawn a bot with the find bot task to start scouting for ore and the enemy core
			spawn_pos = ct.get_position().add(self.spawn_d)
			if ct.can_spawn(spawn_pos):
				ct.spawn_builder(spawn_pos)
				self.num_spawned += 1

		for x in range(-2, 3):
			for y in range(-2, 3):
				new_pos = Position(ct.get_position().x + x, ct.get_position().y + y)
				if ct.can_place_marker(new_pos):
					# First check if there's an existing marker
					entity = ct.get_tile_building_id(new_pos)
					if entity == None:
						# Just put a blank one
						ct.place_marker(new_pos, self.central_marker_data.as_int)
					elif ct.get_entity_type(entity) == EntityType.MARKER:
						# Compare my internal central marker data with the existing marker
						self.read_central_marker(ct, entity)