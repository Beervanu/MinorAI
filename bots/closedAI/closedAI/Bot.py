from cambc import Controller
from .Markers import *
from .Tasktypes import *
from cambc import Position,EntityType,Environment, Team
from .Constants import *
from .Tasks import DO_ONCE_TASKS, builder_tasks
from .MapSymmetry import *
from math import log2, floor
from .helper_functions import eprint
from collections import defaultdict

class ConveyorInfo(TypedDict):
	bitboard: int
	positions: list[Position]
	harvesters: set[Position]
	feeds: EntityType| None
	feeds_team: Team| None

class Bot:
	def __init__(self, ct: Controller, entity_type:EntityType):
		self.id = ct.get_current_round()
		self.core_pos = Position(0,0)
		self.entity_type = entity_type
		self.task_num = 0
		self.count = 0
		self.core_mask = 0
		self.enemy_core_mask = 0
		self.team = ct.get_team()
		# Cache map dimensions globally for this unit
		self.map_width = ct.get_map_width()
		self.map_height = ct.get_map_height()
		self.task: TaskData = None
		self.task_backlog: list[TaskData] = []
		self.task_priority: dict[Task, int]
		self.invalid_tasks: list[TaskData] = []
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
		self.units_board = 0
		self.ore_adjacent_board = 0
		self.seen_this_round_board = 0
		self.team_harvesters_board = 0
		self.harvesters_board = 0
		self.enemy_conveyors_board = 0
		self.team_conveyors_board = 0

		self.conveyor_id = 0
		self.conveyor_ids:defaultdict[Position, set[int]] = defaultdict(set)
		self.conveyor_pointing_to:defaultdict[Position, Position|None] = defaultdict(lambda: None)
		self.conveyors_pointing_into:defaultdict[Position, set[Position]] = defaultdict(set)
		self.dormant_conveyor_pointing_to:defaultdict[Position, Position|None] = defaultdict(lambda: None)
		# each conveyor line has a unique id and has a bitboard, number of harvesters that feed it, and a list of positions (in order)
		self.conveyor_lines:dict[int, ConveyorInfo] = {}
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

	def closest_in_board(self, board:int, pos:Position):
		check_board = self.get_bitmask(pos)
		while not check_board&board:
			orig_check_board = check_board
			check_board |= (orig_check_board<<1)&self.inverted_left_mask
			check_board |= (orig_check_board>>1)&self.inverted_right_mask
			check_board |= (orig_check_board>>self.map_width)
			check_board |= (orig_check_board<<self.map_width)
		return self.pop_lsb(check_board&board)[1]

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

	def get_cardinal_bitmask(self, pos:Position)-> int:
		bitb = 0
		for d in CARDINAL_DIRECTIONS:
			check_pos=pos.add(d)
			if self.is_valid_position(check_pos):
				bitb = self.set_bit(bitb, check_pos)
		return bitb

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

	# Static so it can be alled through the class without needing to pass in self
	@staticmethod
	def chebyshev(a: Position, b: Position) -> int:
		"""
		Chebyshev distance - admissible heuristic (Never overestimates the true path length) for 8-directional movement.
		"""
		return max(abs(a.x - b.x), abs(a.y - b.y))

	def add_conveyor(self, pos:Position, points_to:Position|None):
		"""Adds a conveyor/bridge to our data structure, at position pos, pointing to points_to
		points_to must be a valid position, or None if it points off the map"""
		bitmask = self.get_bitmask(pos)

		# checking for neighbouring harvesters
		neighbouring_harvesters= set()
		for d in CARDINAL_DIRECTIONS:
			check_pos = pos.add(d)
			if self.is_valid_position(check_pos):
				if self.check_bit(self.harvesters_board, check_pos):
					neighbouring_harvesters.add(check_pos)

		# if there are lines pointing into this position
		if self.conveyors_pointing_into[pos]:

			for p in self.conveyors_pointing_into[pos]:
				# add the ids of those lines to our position
				ids = self.conveyor_ids[p]
				self.conveyor_ids[pos].update(ids)
				# add this position to each of those lines
				for id in ids:
					self.conveyor_lines[id]['bitboard'] |= bitmask
					self.conveyor_lines[id]['positions'].append(pos)
					self.conveyor_lines[id]['harvesters'] |= neighbouring_harvesters
		else:
			# if there are no lines pointing into this position, make a new line
			self.conveyor_ids[pos].add(self.conveyor_id)
			self.conveyor_lines[self.conveyor_id] = {
				'bitboard': bitmask,
				'harvesters':neighbouring_harvesters,
				'positions': [pos],
				'feeds': None,
				'feeds_team': None
			}
			self.conveyor_id +=1
		
		#if we dont point off the board
		if points_to:
			#if we are making a loop (then we are pointing to somewhere upstream), so don't expose where we are pointing to 
			# in order to keep everything running smoothly we do something similar as if we are pointing off the board.
			if self.conveyor_ids[pos] & self.conveyor_ids[points_to]:
				self.dormant_conveyor_pointing_to[pos] = points_to
			else: 
				self.conveyors_pointing_into[points_to].add(pos)
				#if it points to another conveyor
				if self.conveyor_ids[points_to]:
					remove_ids = set()
					add_ids = self.conveyor_ids[pos]
					bitb=0
					line = []
					found_bitboard = 0
					found_list = []
					connected_harvesters =set()
					feeds = feeds_team = None
					for id in self.conveyor_ids[points_to]:
						bitb = self.conveyor_lines[id]['bitboard']
						line = self.conveyor_lines[id]['positions']
						connected_harvesters |=self.conveyor_lines[id]['harvesters']
						feeds = self.conveyor_lines[id]['feeds']
						feeds_team = self.conveyor_lines[id]['feeds_team']
						# if we are adding to the end of the line - there will only be one id
						if line[0] == points_to:
							(found_bitboard,found_list) = (bitb, line)
							remove_id = id
							remove_ids = set([remove_id])
							break
					
					#if we are adding to the middle of a line
					if not found_bitboard:
						remove_bitboard =self.max_int
						for i in range(len(line)):
							if line[i] == points_to:
								found_list = line[i:]
								found_bitboard = bitb&remove_bitboard
								break
							remove_bitboard = self.clear_bit(remove_bitboard, line[i])

					#in the special case where we are only joining two line ends, choose the shorter one to update ids
					# (remove ids only has non zero length if we are subsuming a line)
					if len(self.conveyor_ids[pos])==1 and remove_ids:
						incoming_id = 0
						outgoing_id = remove_id
						for id in self.conveyor_ids[pos]:
							incoming_id = id
							break
						
						incoming_bitb=self.conveyor_lines[incoming_id]['bitboard']
						incoming_harvesters=self.conveyor_lines[incoming_id]['harvesters']
						incoming_line=self.conveyor_lines[incoming_id]['positions']

						outgoing_bitb=self.conveyor_lines[outgoing_id]['bitboard']
						outgoing_harvesters=self.conveyor_lines[outgoing_id]['harvesters']
						outgoing_line=self.conveyor_lines[outgoing_id]['positions']
						if len(incoming_line) < len(outgoing_line):
							keep_id = outgoing_id
							remove_id = incoming_id
							update_pos_list = incoming_line
						else:
							keep_id=incoming_id
							remove_id = outgoing_id
							update_pos_list = outgoing_line
						
						self.conveyor_lines[keep_id].update({
							'bitboard': incoming_bitb|outgoing_bitb,
							'harvesters': incoming_harvesters|outgoing_harvesters,
							'positions': incoming_line+outgoing_line,
							'feeds': self.conveyor_lines[outgoing_id]['feeds'],
							'feeds_team': self.conveyor_lines[outgoing_id]['feeds_team']

						})
						del self.conveyor_lines[remove_id]
						for p in update_pos_list:
							self.conveyor_ids[p].remove(remove_id)
							self.conveyor_ids[p].add(keep_id)
					else:
						if remove_ids:
							del self.conveyor_lines[remove_id]
						#update the incoming conveyor lines
						for id in self.conveyor_ids[pos]:
							self.conveyor_lines[id]['bitboard']|=found_bitboard
							self.conveyor_lines[id]['harvesters'] |=connected_harvesters
							self.conveyor_lines[id]['positions'] += found_list
							self.conveyor_lines[id]['feeds'] = feeds	
							self.conveyor_lines[id]['feeds_team'] = feeds_team				
						for p in found_list:
							self.conveyor_ids[p].difference_update(remove_ids)
							self.conveyor_ids[p].update(add_ids)
				self.conveyor_pointing_to[pos] = points_to
	
	def update_downstream_ids(self, pos:Position, remove_ids:set[int]=set(), add_ids:set[int]=set()):
		points_to = pos
		visited = set()
		while self.conveyor_ids[points_to]:
			self.conveyor_ids[points_to].difference_update(remove_ids)
			self.conveyor_ids[points_to].update(add_ids)
			points_to= self.conveyor_pointing_to[points_to]
			if points_to is None or (points_to in visited):
				break

			visited.add(points_to)

	def conveyor_broken(self, ct:Controller, pos:Position):
		# if there are conveyors pointing into us
		if self.conveyors_pointing_into[pos]:
			made_new_line = False
			ids = self.conveyor_ids.pop(pos)
			# first update lines
			index = 0
			removal_bitboard =0
			inverse_removal_bitboard = 0
			#for every line that runs through this position
			harvester_info= []
			remaining_harvesters = set()
			for id in ids:
				#finding the downstream positions from here
				for j in range(len(self.conveyor_lines[id]['positions'])):
					remove_pos = self.conveyor_lines[id]['positions'][-1-j]
					removal_bitboard = self.set_bit(removal_bitboard, remove_pos)
					if remove_pos == pos:
						index =j
						break
				
				inverse_removal_bitboard = self.max_int-removal_bitboard
				#make our new conveyor line, don't want to include the position of the conveyor that has just been broken
				removal_bitboard = self.clear_bit(removal_bitboard, pos)
				# all the conveyors being cutoff
				cutting_conveyors = self.conveyor_lines[id]['positions'][-index:]
				connected_harvesters = self.conveyor_lines[id]['harvesters']
				for harvester_pos in connected_harvesters:
					harvester_info.append((harvester_pos, self.get_cardinal_bitmask(harvester_pos)))

				# if there is a part being cutoff downstream, and that part isn't already in some other line
				# make a new line
				made_new_line = index and not (self.conveyor_ids[cutting_conveyors[0]]-ids)
				if made_new_line:
					harvesters = set()
					for p, bitb in harvester_info:
						if bitb&removal_bitboard:
							harvesters.add(p)
					self.conveyor_lines[self.conveyor_id]= {
						'bitboard':removal_bitboard,
						'harvesters':harvesters,
						'positions':cutting_conveyors,
						'feeds':None,
						'feeds_team': None
					}
				break
			upstream_lines_bitboard = 0
			for id in ids:
				line_bitboard = self.conveyor_lines[id]['bitboard']& (inverse_removal_bitboard)
				self.conveyor_lines[id]['bitboard'] = line_bitboard
				upstream_lines_bitboard|=line_bitboard
			
			upstream_harvesters = set()
			for (p,bitb) in harvester_info:
				if bitb&upstream_lines_bitboard:
					upstream_harvesters.add(p)
			for id in ids:
				self.conveyor_lines[id].update({
					'harvesters': upstream_harvesters,
					'positions': self.conveyor_lines[id]['positions'][:-1-index],
					'feeds': None,
					'feeds_team': None
				})
			if upstream_harvesters and self.entity_type == EntityType.BUILDER_BOT:
				self.add_task(ct, BuilderTask.BUILD_BRIDGE, pos, False)
			
			
			# then update id board
			# updates pointing_to board
			points_to = None
			if self.conveyor_pointing_to[pos]:
				points_to = self.conveyor_pointing_to.pop(pos)
			self.dormant_conveyor_pointing_to[pos] = None
			if points_to:
				#updates pointing_into_board
				self.conveyors_pointing_into[points_to].remove(pos)
				# want to remove ids of the lines that just broke, and add the new id of the new branch if it was made
				add_ids = set([self.conveyor_id]) if made_new_line else set()
				update_lines_ids = set()
				pos_list = []
				bitb = 0
				old_pos = points_to
				while self.conveyor_ids[points_to]:
					#used to keep track of the points downstream of a dormant point, to later update the lines
					pos_list.append(points_to)
					bitb = self.set_bit(bitb, points_to)

					self.conveyor_ids[points_to].difference_update(ids)
					self.conveyor_ids[points_to].update(add_ids)
					old_pos = points_to
					points_to= self.conveyor_pointing_to[points_to]
					if points_to is None:
						dormant_points_to = self.dormant_conveyor_pointing_to[old_pos]
						# if we have broken a loop
						# self.conveyor_ids[dormant_points_to] is always a subset of ids if we have broken a loop 
						if dormant_points_to and (shared_ids:=self.conveyor_ids[dormant_points_to] & ids):
							# eprint('broke a loop, round: ', ct.get_current_round(), self.conveyor_ids[old_pos])
							#ids of lines through dormant pointer
							update_lines_ids = self.conveyor_ids[old_pos]
							pos_list = []
							bitb = 0							
							# if the place the dormant was pointing to was not an end, we would like to keep those ids on the following points,
							# if it was an end we are deleting those lines
							if self.conveyors_pointing_into[dormant_points_to]:
								ids.difference_update(shared_ids)
							else:
								#this should only be one id
								if len(self.conveyor_ids[dormant_points_to]) != 1:
									raise Exception()
								for id in self.conveyor_ids[dormant_points_to]:
									del self.conveyor_lines[id]
							#remove the dormant point
							self.conveyor_pointing_to[old_pos] = dormant_points_to
							self.dormant_conveyor_pointing_to[old_pos] = None
							self.conveyors_pointing_into[dormant_points_to].add(old_pos)
									

							add_ids.update(self.conveyor_ids[old_pos])
							points_to = dormant_points_to
						else:
							break
				last_feeds = None
				last_feeds_team = None
				last_connected_harvesters = set()
				for id in self.conveyor_ids[old_pos]:
					last_feeds = self.conveyor_lines[id]['feeds']
					last_feeds_team = self.conveyor_lines[id]['feeds_team']
					last_connected_harvesters = self.conveyor_lines[id]['harvesters']
					break

				for id in update_lines_ids:
					self.conveyor_lines[id]['positions'] += pos_list
					self.conveyor_lines[id]['bitboard'] |= bitb
					self.conveyor_lines[id].update({
						'feeds': last_feeds,
						'feeds_team': last_feeds_team,
						'harvesters': last_connected_harvesters
					})
			#we may have made a new conveyor line, increment to keep ids unique
			if made_new_line:
				self.conveyor_id +=1
		else:
			#if nothing points into us, we are an end, so should only have one id, so dont need to update id board, apart from at our position
			# and update the line we were in accordingly
			id = self.conveyor_ids[pos].pop()
			points_to = self.conveyor_pointing_to.pop(pos)
			if points_to:
				self.conveyors_pointing_into[points_to].remove(pos)
			bitboard = self.conveyor_lines[id]['bitboard']
			harvesters = self.conveyor_lines[id]['harvesters']
			pos_list = self.conveyor_lines[id]['positions']
			if pos_list[1:]:
				#if its already part of another line get rid of this line
				if self.conveyor_ids[pos_list[1]] - set([id]):
					self.update_downstream_ids(pos_list[1], set([id]))
					del self.conveyor_lines[id]				
				else:
					n_harvesters = set()
					bitboard = self.clear_bit(bitboard, pos)
					for harvester_pos in harvesters:
						for d in CARDINAL_DIRECTIONS:
							check_pos=harvester_pos.add(d)
							if self.is_valid_position(check_pos) and self.check_bit(bitboard, check_pos):
								n_harvesters.add(harvester_pos)
								break
					self.conveyor_lines[id].update({'bitboard': bitboard, 'harvesters':n_harvesters, 'positions': pos_list[1:]})
			else:
				#if this was the only thing in the line
				del self.conveyor_lines[id]

	def update_terrain_vision(self, ct:Controller):
		"""Called after moving to map newly revealed terrain."""
		t = ct.get_cpu_time_elapsed()
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
				self.ore_adjacent_board |= self.get_cardinal_bitmask(current_pos)
			self.seen_board,self.seen_symmetry_boards = self.set_symmetry_bit(self.seen_board,self.seen_symmetry_boards, pos)
		print(f'Updating environment took {ct.get_cpu_time_elapsed()-t}μs')
		t= ct.get_cpu_time_elapsed()
		harvester_positions:list[Position] = []
		conveyors_added = False
		#then update buildings
		for pos in ct.get_nearby_tiles():
			pos_bitmask = self.get_bitmask(pos)
			inverted_pos_bitmask = self.max_int-pos_bitmask
			# Skip if we have already mapped this tile as a wall (it cant change to anything else) or we already mapped this tile this round
			if self.walls_board&pos_bitmask or self.seen_this_round_board&pos_bitmask:
				continue

			self.seen_this_round_board |= pos_bitmask
			
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
			self.team_harvesters_board &= inverted_pos_bitmask
			self.enemy_conveyors_board&= inverted_pos_bitmask
			self.team_conveyors_board &= inverted_pos_bitmask
			old_harvesters = self.harvesters_board
			self.harvesters_board&= inverted_pos_bitmask
			building_id = ct.get_tile_building_id(pos)
			if building_id:
				etype = ct.get_entity_type(building_id)
				team = ct.get_team(building_id)
				is_team: bool = ct.get_team() == team
				if etype in [EntityType.CORE]+TURRET_ENTITIES:
					for p in self.conveyors_pointing_into[pos]:
						ids = self.conveyor_ids[p]
						for id in ids:
							#if they have already been updated
							if self.conveyor_lines[id]['feeds'] == etype:
								break
							self.conveyor_lines[id].update({
								'feeds': etype,
								'feeds_team': team
							})
				if etype in CONVEYOR_ENTITIES:
					if etype==EntityType.BRIDGE:
						points_to = ct.get_bridge_target(building_id)
					else:
						points_to = pos.add(ct.get_direction(building_id))
					if not self.is_valid_position(points_to):
						points_to = None
					# if there was a conveyor but it was pointing somewhere else
					if self.conveyor_ids[pos] and self.conveyor_pointing_to[pos]!=points_to:
						self.conveyor_broken(ct, pos)

					if not self.conveyor_ids[pos]:
						conveyors_added=True
						self.add_conveyor(pos, points_to)

				#if there used to be a conveyor but it has been broken now
				elif self.conveyor_ids[pos]:
					self.conveyor_broken(ct, pos)
				if etype == EntityType.HARVESTER:
					harvester_positions.append(pos)
					if not self.check_bit(old_harvesters, pos):
						# add harvesters to conveyor lines
						bitb = self.get_cardinal_bitmask(pos)
						add_to = set()
						for i in self.conveyor_lines:
							if self.conveyor_lines[i]['bitboard']&bitb:
								add_to.update(self.conveyor_ids[self.conveyor_lines[i]['positions'][-1]])
						for i in add_to:
							self.conveyor_lines[i]['harvesters'].add(pos)
						self.harvesters_board |= pos_bitmask
					

				if etype == EntityType.MARKER:
					self.walkable_board |= pos_bitmask
					if is_team:
						self.read_marker(ct, building_id)
				else:
					if is_team:
						
						self.team_buildings_board|= pos_bitmask
						#order of this is VERY important - team buildings board must be updated before we add heal task
						#heal damaged stuff
						if is_builder_bot and etype not in [EntityType.ROAD, EntityType.MARKER] :
							
							if ct.get_hp(building_id) <= ct.get_max_hp(building_id)-4:
								self.add_task(ct, BuilderTask.HEAL, pos, True)
						if etype == EntityType.HARVESTER:
							self.team_harvesters_board |= pos_bitmask
						elif etype in CONVEYOR_ENTITIES:
							self.team_conveyors_board |= pos_bitmask
					else:
						self.enemy_buildings_board|= pos_bitmask
						if etype in CONVEYOR_ENTITIES:
							if self.ore_adjacent_board&pos_bitmask and is_builder_bot:
								self.add_task(ct,BuilderTask.PLACE_SENTINEL, pos, True)
							self.enemy_conveyors_board |= pos_bitmask
						elif etype in TURRET_ENTITIES:
							self.add_task(ct,BuilderTask.CUTOFF_ENEMY_TURRET, pos)
			elif self.conveyor_ids[pos]:
				self.conveyor_broken(ct, pos)

		if is_builder_bot:
			#build conveyors from harvesters
			for p in harvester_positions:
				# check no one else has already built a conveyor from this ore
				valid_pos = []

				for dir in CARDINAL_DIRECTIONS:
					check_pos = p.add(dir)
					if not self.is_valid_position(check_pos):
						continue
					if self.check_bit(self.team_conveyors_board, check_pos):
						valid_pos = []
						break
					valid_pos.append(check_pos)
				valid_pos.sort(key=lambda po: self.chebyshev(self.core_pos, po))
				for pos in valid_pos:
					if self.check_bit(self.walkable_board, pos) and not self.check_bit(self.axionite_ores_board|self.titanium_ores_board|self.defence_walls_board, pos): # type: ignore
						self.add_task(ct,BuilderTask.BUILD_BRIDGE, (pos), False)
						break
		print(f'Updating buildings took {ct.get_cpu_time_elapsed()-t}μs')
		t=ct.get_cpu_time_elapsed()
		# we want to cutoff enemy lines that feed enemy buildings
		if conveyors_added and is_builder_bot:
			found_ids:set[int] = set()
			for id in self.conveyor_lines:
				if id in found_ids:
					continue
				found_ids.add(id)
				conveyor_info = self.conveyor_lines[id]
				if conveyor_info['feeds_team'] != self.team and conveyor_info['harvesters']:
					#get ids of last position, then cutoff all of those lines simultaneously
					cutoff_line_ids = self.conveyor_ids[conveyor_info['positions'][-1]]
					found_ids.update(cutoff_line_ids)
					bitb = conveyor_info['bitboard']
					for _id in cutoff_line_ids:
						bitb&= self.conveyor_lines[_id]['bitboard']
					self.add_task(ct, BuilderTask.CUTOFF_ENEMY_LINES, self.closest_in_board(bitb, ct.get_position()), True)


		print(f'Calculating enemy line cutoff points took {ct.get_cpu_time_elapsed()-t}μs')
		t=ct.get_cpu_time_elapsed()
		if old_walkable_board!=self.walkable_board:
			self.connected_region = self.update_region(self.walkable_board|(self.max_int-self.seen_board),current_pos)
			print(f'Updating connected region took {ct.get_cpu_time_elapsed()-t}μs')


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

	def draw_conveyor(self, ct:Controller, id:int, colour: tuple[int,int,int]):
		try:
			for p in self.conveyor_lines[id]['positions']:
				ct.draw_indicator_dot(p, colour[0],colour[1], colour[2])
				if points_to:=self.conveyor_pointing_to[p]:
					ct.draw_indicator_line(p, points_to, colour[0],colour[1], colour[2])
		except KeyError:
			eprint('failed to draw')

	def turn_end(self, ct:Controller):

		# print('Conveyor Lines')
		# first = True
		# colour_ind = 0
		# colours = [(0,0,255), (0,255,0), (0,0,255), (255,0,255), (0,255,255), (255,255,0), (0,0,127), (0,127,0), (127,0,0), (0,0,0), (255,255,255)]
		# for i in self.conveyor_lines:
		# 	print(i,', '.join ([f'({p.x} {p.y})' for p in self.conveyor_lines[i]['positions']]), self.conveyor_lines[i]['harvesters'])
		# 	self.draw_conveyor(ct, i, colours[colour_ind])
		# 	colour_ind +=1
		# 	colour_ind%= len(colours)
		# for i in self.conveyor_ids:
		# 	if self.conveyor_ids[i]:
		# 		print(i.x, i.y, self.conveyor_ids[i])
		if ct.get_cpu_time_elapsed()>2000:
			eprint('Lagging, Round:', ct.get_current_round(), 'Team: ', self.team,'ID: ', self.id)

	def get_task_identifier(self, task:Task, data:Any):
		identifier = 0
		match task:
			case BuilderTask.FOUND_AX_ORE | BuilderTask.FOUND_TI_ORE | BuilderTask.BUILD_BRIDGE | BuilderTask.PLACE_SENTINEL | BuilderTask.CUTOFF_ENEMY_TURRET:
				identifier = data.y*self.map_width + data.x

		return identifier

	def add_task(self, ct:Controller, task: Task, data: Any, interruptable=False)->bool:
		"""Adds the given task, while checking whether it is valid, or already done"""

		identifier = self.get_task_identifier(task, data)
		taskdata:TaskData = {"type":task, "data":data, "identifier": identifier, "interruptable": interruptable, "uid":self.task_num, "timeout":0}
		if not builder_tasks[task]['is_valid'](self,ct,taskdata):
			return False
		round = ct.get_current_round()
		invalid_tasks = []
		for t in self.invalid_tasks:
			if t['timeout']>=round:
				invalid_tasks.append(t)
		self.invalid_tasks = invalid_tasks
		check_tasks = self.invalid_tasks+self.task_backlog
		if self.task:
			check_tasks.append(self.task)
		

		for t in check_tasks:
			
			if t['type'] == task and t['identifier'] == identifier:
				print('Task already done or added: ', task)
				return False
		
		# else add it to backlog
		self.task_backlog.append(taskdata)
		self.task_num+=1
		return False

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
				task['timeout'] = ct.get_current_round()+10
				self.invalid_tasks.append(task)
		self.task_backlog = new_backlog
		


	def task_complete(self,ct:Controller):
		
		if self.task_backlog:
			self.cull_task_backlog(ct)
			self.sort_task_backlog(ct)
			self.task = self.task_backlog.pop(0)
			print(f'New Task: {self.task['type']}, Data: {self.task['data']}, I: {int(self.task["interruptable"])}')
		else:
			eprint("No new task: Round", ct.get_current_round() , self.entity_type)
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
		if read.type == MarkerType.CENTRAL:	
			self.read_central_marker(ct, marker)
		elif read.type == MarkerType.TASK:
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
