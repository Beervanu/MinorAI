from cambc import Controller
from .Markers import *
from .Tasktypes import *
from cambc import Position,EntityType,Environment
from .Constants import *
from .Tasks import DO_ONCE_TASKS, builder_tasks
from .MapSymmetry import *
from math import log2, floor
from .helper_functions import eprint


class Bot:
	def __init__(self, ct: Controller, entity_type:EntityType):
		self.entity_type = entity_type
		self.task_num = 0
		self.count = 0

		# Cache map dimensions gloabally for this unit
		self.map_width = ct.get_map_width()
		self.map_height = ct.get_map_height()
		self.task: TaskData = None
		self.task_backlog: list[TaskData] = []
		self.task_priority: dict[Task, int]
		self.done_tasks: list[TaskData] = []
		# Initialisation of bitboards for different map features
		self.seen_board = 0
		self.seen_symmetry_boards = (0,0,0)
		self.walls_board = 0
		self.walls_symmetry_boards = (0,0,0)
		self.axionite_ores_board = 0
		self.axionite_ores_symmetry_boards = (0,0,0)
		self.titanium_ores_board = 0
		self.titanium_ores_symmetry_boards = (0,0,0)
		self.walkable_board = 0
		self.team_buildings_board = 0
		self.enemy_buildings_board = 0
		self.team_bridges_board = 0
		self.units_board = 0
		self.ore_adjacent_board = 0
		self.seen_this_round_board = 0
		self.team_harvesters_board = 0
		self.enemy_conveyor_board = 0
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
		self.max_int = (1<<self.map_width*self.map_height)-1
		self.inverted_right_mask = self.max_int-self.generate_mask([0b1]*self.map_height)
		self.inverted_left_mask = self.inverted_right_mask<<1
		self.connected_region = self.max_int-1
		self.map_symmetry = MapSymmetry.UNKNOWN

		self.central_marker_data = CentralMarkerData()
		self.possible_map_symmetries = [MapSymmetry.REFLECTION_Y, MapSymmetry.REFLECTION_X]
		if self.map_height == self.map_width:
			self.possible_map_symmetries.append(MapSymmetry.ROTATIONAL)
		# What's a bitboard you ask? Well look no further Motion has got you covered.
		# Essentially we map every tile on the map to a index on a binary number
		# So if we had a 4 tile map a bitboard would look something like 0110 where tile 1 is assigned the value 0 and tile 3 is assigned 1
		# Why use bit boards? Parallel queries. We can check if a tile is a wall by doing a single logical AND between the walls bitboard and a bitmask with a 1 at the index of the tile we want to query. This is much faster than querying the tile environment through the API every time we want to check if a tile is a wall.
		
	def board_string(self, board:int)->str:
		"""Returns the string of all positions with a 1 in the board. Used for debugging"""
		
		board = board&self.max_int
		pos_list = []
		while (board):
			(board, pos) = self.pop_lsb(board)
			pos_list.append(pos)
		return self.path_string(pos_list)

	def path_string(self, path: list[Position]):
		s = ''
		for pos in path:
			s+=f'({pos.x}, {pos.y}) '
		return s

	def generate_mask(self, arr: list[int])->int:
		mask = 0
		for i in range(len(arr)):
			mask+=arr[i]<<(self.map_width*i)
		return mask

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
	
	def get_bitmask(self, pos:Position) -> int:
		index = pos.y * self.map_width + pos.x
		bitmask = 1 << index
		return bitmask

	def set_bit(self, bitboard: int, pos: Position) -> int:
		"""Turns the bit ON at a given Position and returns the new board."""
		# Still maps the input position to the correct index for the bitboard. Nothing has changed here.
		index = pos.y * self.map_width + pos.x
		bitmask = 1 << index
		# Alright so here we are peforming a logical OR on the bitboard at the index of the tile given.
		# Two things here. As it is an OR it preserves the preserves the other indices in the board (1 OR 0 = 1, 0 OR 0 = 0).
		# The second thing is that if the bit at the index provided is already on (is 1) it remains 1 as 1 OR 1 = 1 (Kind of inferred from the first point but idc).
		return bitboard | bitmask
	
	def set_symmetry_bit(self, bitboard:int, symmetry_bitboards:tuple[int,int,int], pos:Position) ->tuple[int, tuple[int,int,int]]:
		"""Turns the bit ON at a given Position and all its symmetry positions and returns the new boards in the order: (original, rotated, reflect_x, reflect_y)."""
		# Still maps the input position to the correct index for the bitboard. Nothing has changed here.
		rotated_bitboard, reflect_x_bitboard , reflect_y_bitboard = symmetry_bitboards
		index = pos.y * self.map_width + pos.x
		bitmask = 1 << index
		# want (map_height-pos.y-1) * self.map_width + (map_width - pos.x-1) - the expression on the next line is equivalent
		rotated_index = self.map_height*self.map_width - index -1 
		rotated_bitmask = 1 << rotated_index

		reflect_y_index = pos.y*self.map_width + (self.map_width-pos.x-1)
		reflect_y_bitmask = 1 << reflect_y_index

		reflect_x_index = (self.map_height - pos.y - 1)*self.map_width + pos.x
		reflect_x_bitmask = 1 << reflect_x_index
		# Alright so here we are peforming a logical OR on the bitboard at the index of the tile given.
		# Two things here. As it is an OR it preserves the preserves the other indices in the board (1 OR 0 = 1, 0 OR 0 = 0).
		# The second thing is that if the bit at the index provided is already on (is 1) it remains 1 as 1 OR 1 = 1 (Kind of inferred from the first point but idc).
		return bitboard | bitmask, (rotated_bitboard | rotated_bitmask, reflect_x_bitboard | reflect_x_bitmask, reflect_y_bitboard | reflect_y_bitmask)

	def clear_bit(self, bitboard: int, pos: Position) -> int:
		"""Turns the bit OFF at the given Postion and returns the new board."""
		# Need I say anymore?
		index = pos.y * self.map_width + pos.x
		bitmask = 1 << index 
		# And with the NOT of the bitmask so everything is flipped.
		# This means that the index of input tile is set to 0 and everything is set to 1. And well 0 AND anything is 0.
		return bitboard & ~(bitmask)

	def is_valid_position(self, pos:Position)->bool:
		"""Returns true if in map bounds"""
		return 0<=pos.x<self.map_width and 0<=pos.y<self.map_height

	def update_terrain_vision(self, ct:Controller):
		"""Called after moving to map newly revealed terrain.""" 
		# This acts as a way to fill in the dark areas of map memory.
		print("Updating terrain vision")
		old_walkable_board = self.walkable_board
		self.units_board = 0
		self.units_adjacent_board = 0
		current_pos = ct.get_position()
		for id in ct.get_nearby_units():
			if ct.get_entity_type(id) == EntityType.BUILDER_BOT:
				pos = ct.get_position(id)
				if pos == current_pos:
					continue
				self.units_board = self.set_bit(self.units_board, pos)
				
				mask = 0
				neighbours = map(lambda dir: pos.add(dir), DIRECTIONS)
				for nbr in filter(lambda n: self.is_valid_position(n), neighbours):
					mask = self.set_bit(mask, nbr)
				self.units_adjacent_board |=mask

		is_builder_bot = self.entity_type == EntityType.BUILDER_BOT
		#first update environment
		for pos in ct.get_nearby_tiles():
			pos_bitmask = self.get_bitmask(pos)
			inverted_pos_bitmask = self.max_int-pos_bitmask
			# Skip if we have already mapped this tile as a wall (the environment can't change to anything else)
			if self.seen_board & pos_bitmask:
				continue
			

			# Jose has changed the logic of this function and did not update the corresponding comments btw 💔.
			# The change is we now have a seen board which essentially did what I already did but it a more compact way.
			env = ct.get_tile_env(pos)
			if env == Environment.WALL:

				self.walls_board, self.walls_symmetry_boards = self.set_symmetry_bit(self.walls_board, self.walls_symmetry_boards,pos)
			elif env == Environment.ORE_TITANIUM:
				self.titanium_ores_board, self.titanium_ores_symmetry_boards = self.set_symmetry_bit(self.titanium_ores_board, self.titanium_ores_symmetry_boards,pos)
				if is_builder_bot:
					self.add_task(ct,BuilderTask.FOUND_TI_ORE, pos, True)
			elif env == Environment.ORE_AXIONITE:
				self.axionite_ores_board, self.axionite_ores_symmetry_boards = self.set_symmetry_bit(self.axionite_ores_board,self.axionite_ores_symmetry_boards,pos)
			
			if env == Environment.ORE_AXIONITE or env == Environment.ORE_TITANIUM:
				for d in CARDINAL_DIRECTIONS:
					check_pos = pos.add(d)
					if self.is_valid_position(check_pos):
						self.ore_adjacent_board = self.set_bit(self.ore_adjacent_board, check_pos)
			self.seen_board,self.seen_symmetry_boards = self.set_symmetry_bit(self.seen_board,self.seen_symmetry_boards, pos)
		print(f'Updating environment took {ct.get_cpu_time_elapsed()}μs')
		#then update buildings
		for pos in ct.get_nearby_tiles():
			pos_bitmask = self.get_bitmask(pos)
			inverted_pos_bitmask = self.max_int-pos_bitmask
			# Skip if we have already mapped this tile as a wall (it cant change to anything else) or we already mapped this tile this round
			if self.walls_board&pos_bitmask or self.seen_this_round_board&pos_bitmask:
				continue

			self.seen_this_round_board = self.set_bit(self.seen_this_round_board, pos)
			
			#update buildings on a tile (need to do this for all non wall tiles every time)
			#is it already passable or is it empty and there is no unit on it
			if ct.is_tile_passable(pos) or (ct.is_tile_empty(pos) and not self.units_board&pos_bitmask):
				if not self.walkable_board& pos_bitmask:
					self.walkable_board |= pos_bitmask
			else:
				if self.walkable_board& pos_bitmask:
					self.walkable_board &= inverted_pos_bitmask
			#add our own position to the walkable board so pathfinding isnt confused
			self.walkable_board = self.set_bit(self.walkable_board, ct.get_position())
			# update boards
			self.team_buildings_board &= inverted_pos_bitmask
			self.enemy_buildings_board&= inverted_pos_bitmask
			self.team_bridges_board &= inverted_pos_bitmask
			self.team_harvesters_board &= inverted_pos_bitmask
			self.enemy_conveyor_board&= inverted_pos_bitmask
			building_id = ct.get_tile_building_id(pos)
			if building_id:
				etype = ct.get_entity_type(building_id)
				is_team: bool = ct.get_team() == ct.get_team(building_id)
				if etype == EntityType.MARKER:
					self.walkable_board |= pos_bitmask
					if is_team:
						self.read_marker(ct, building_id)
				else:
					if is_team:
						self.team_buildings_board|= pos_bitmask
						if etype == EntityType.BRIDGE:
							self.team_bridges_board |= pos_bitmask
						elif etype == EntityType.HARVESTER:
							self.team_harvesters_board |= pos_bitmask
					else:
						self.enemy_buildings_board= self.set_bit(self.enemy_buildings_board, pos)
						if etype in CONVEYOR_ENTITIES:
							if self.ore_adjacent_board&pos_bitmask and is_builder_bot:
								self.add_task(ct,BuilderTask.PLACE_SENTINEL, pos)
							if etype != EntityType.BRIDGE:
								self.enemy_conveyor_board |= pos_bitmask
						elif etype in TURRET_ENTITIES:
							self.add_task(ct,BuilderTask.CUTOFF_ENEMY_TURRET, pos)


		print(f'Updating buildings took {ct.get_cpu_time_elapsed()}μs')
		if old_walkable_board!=self.walkable_board:
			self.connected_region = self.update_region(self.walkable_board|(self.max_int-self.seen_board),current_pos)
			print(f'Updating connected region took {ct.get_cpu_time_elapsed()}μs')


	def turn_start(self,ct):
		self.seen_this_round_board = 0

	def update_region(self, empty_bitboard:int, start_pos:Position):
		region_bitboard = self.set_bit(0, start_pos)
		old = 0
		while old!=region_bitboard:
			old = region_bitboard
			region_bitboard |= (region_bitboard<<1)&self.inverted_left_mask
			region_bitboard |= (region_bitboard>>1)&self.inverted_right_mask
			region_bitboard |= (region_bitboard>>self.map_width)
			region_bitboard |= (region_bitboard<<self.map_width)
			region_bitboard&=empty_bitboard
		return region_bitboard


	def turn_end(self, ct:Controller):
		
		if ct.get_cpu_time_elapsed()>2000:
			eprint('Lagging, Round:', ct.get_current_round(), 'Bot:', ct.get_entity_type())

	def get_task_identifier(self, task:Task, data:Any):
		identifier = 0
		match task:
			case BuilderTask.FOUND_AX_ORE | BuilderTask.FOUND_TI_ORE | BuilderTask.BUILD_BRIDGE | BuilderTask.PLACE_SENTINEL:
				identifier = data.y*self.map_width + data.x

		return identifier

	def add_task(self, ct:Controller, task: Task, data: Any, interruptable=False)->bool:
		"""Adds the given task, while checking whether it is valid, or already done"""

		identifier = self.get_task_identifier(task, data)
		taskdata:TaskData = {"type":task, "data":data, "identifier": identifier, "interruptable": interruptable, "uid":self.task_num}
		if not builder_tasks[task]['is_valid'](self,ct,taskdata):
			return False
		if task in DO_ONCE_TASKS:
			check_tasks = self.done_tasks+self.task_backlog
			if self.task:
				check_tasks.append(self.task)
			for t in check_tasks:
				if t['identifier'] == identifier:
					print('Task already done or added: ', task)
					return False
		
		# else add it to backlog
		self.task_backlog.append(taskdata)
		self.task_num+=1
		return False
	
		# # if higher task priority, bench the current task and switch to it
			# if self.task_priority[self.task['type']] < self.task_priority[task]:
			# 	self.task_backlog.insert(0, self.task)
			# 	self.task = {'type':task, 'data':data}
			# 	return True

	def get_task_secondary_priority(self, ct:Controller, task:TaskData):
		prio = float('inf')

		return prio

	def sort_task_backlog(self, ct):
		if self.task_backlog:
			self.task_backlog.sort(key=lambda x: (self.task_priority[x['type']], self.get_task_secondary_priority(ct,x), x['uid']))

	def cull_task_backlog(self, ct:Controller):
		new_backlog = []
		for task in self.task_backlog:
			if builder_tasks[task['type']]['is_valid'](self,ct,task):
				new_backlog.append(task)
			elif task['type'] in DO_ONCE_TASKS:
				self.done_tasks.append(task)
		self.task_backlog = new_backlog
		


	def task_complete(self,ct:Controller):
		if self.task['type'] in DO_ONCE_TASKS:
			self.done_tasks.append(self.task)
		if self.task_backlog:
			self.cull_task_backlog(ct)
			self.sort_task_backlog(ct)
			self.task = self.task_backlog.pop(0)
			print(f'New Task: {self.task['type']}, Data: {self.task['data']}, I: {int(self.task["interruptable"])}')
		else:
			eprint("No new task - this is bad tell Jose")
			print("no new task")

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
		possible = []
		for sym in self.possible_map_symmetries:
			# the index in the symmetry boards that corresponds to this symmetry
			i = sym-1
			both_seen    = self.seen_board & self.seen_symmetry_boards[i]
			wall_diff    = both_seen & (self.walls_board ^ self.walls_symmetry_boards[i])
			ti_ore_diff     = both_seen & (self.titanium_ores_board ^ self.titanium_ores_symmetry_boards[i])
			ax_ore_diff     = both_seen & (self.axionite_ores_board ^ self.axionite_ores_symmetry_boards[i])

			if (wall_diff | ti_ore_diff | ax_ore_diff) == 0:
				possible.append(sym)
		self.possible_map_symmetries = possible
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
	
	def read_marker(self, ct:Controller, marker):
		read = MarkerData()
		read.as_int =ct.get_marker_value(marker)
		if read.type == 0:	
			self.read_central_marker(ct, marker)
		elif read.type == 1:
			self.read_task_marker(ct, marker)

	def read_central_marker(self, ct: Controller, marker):
		read = CentralMarkerData()
		read.as_int = ct.get_marker_value(marker)
		if self.central_marker_data.date > read.date: 
			# My one is newer - overwrite
			# better to destroy rather than overwrite since we can destroy unlimited amounts per turn
			# and there should be a marker near us that we have placed anyway
			if ct.can_destroy(ct.get_position(marker)):
				ct.destroy(ct.get_position(marker))
		elif self.central_marker_data.date < read.date:
			# My one is older - replace internal data with this new one
			self.central_marker_data.as_int = read.as_int

			self.map_symmetry = self.central_marker_data.known_map_symmetry
	
	def read_task_marker(self, ct: Controller, entity):
		pass
