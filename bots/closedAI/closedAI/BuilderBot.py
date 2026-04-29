from cambc import Controller, Position, Direction, EntityType, GameConstants
from .Tasktypes import BuilderTask, TaskData
from .Markers import TaskMarkerData
import heapq
from functools import lru_cache
from math import floor, ceil

from .Bot import *
from .Tasks import builder_tasks, DO_ONCE_TASKS
from .helper_functions import *

class BuilderBot(Bot):
	def __init__(self, ct:Controller, core_pos: Position, move_dir: Direction):
		# Initialises the parent class (Bot) to generate the bit boards and inherit the corresponding variables and functions
		
		
		super().__init__(ct, EntityType.BUILDER_BOT)
		self.protected_area = 0
		self.core_pos = core_pos
		for d in Direction:
			self.core_mask = self.set_bit(self.core_mask, self.core_pos.add(d))
		self.core_attack_range_mask = 0
		self.core_attack_range_symmetry_masks = (0,0,0)
		attack_range = ceil((GameConstants.SENTINEL_VISION_RADIUS_SQ)**0.5)
		for x in range(-attack_range, attack_range+1):
			for y in range(-attack_range, attack_range+1):
				check_pos = Position(self.core_pos.x+x, self.core_pos.y+y)
				if self.is_valid_position(check_pos) and check_pos.distance_squared(self.core_pos)<=GameConstants.SENTINEL_VISION_RADIUS_SQ:
					self.core_attack_range_mask, self.core_attack_range_symmetry_masks = self.set_symmetry_bit(self.core_attack_range_mask,self.core_attack_range_symmetry_masks, check_pos)
		self.enemy_core_pos:Position = None
		self.move_dir = move_dir
		self.target:Position = None
		self.target_radius_sq = 2
		self.phase = 0
		self.do_pathfinding = True
		self.pathfinding_interrupted = False
		self.pathfinding_save_state:dict[str, Any] = {'time_out':1}
		self.do_bug_pathfinding=False
		# The ordered list of positions and the corresponding bitboard
		self.bridge_path = []
		self.known_bridges_at_path_construction = 0
		self.bridge_path_index = 0
		self.bridge_path_board = None
		self.path = [] # List[Position] - ordered steps from current position to target
		self.path_index = 0 # How far along the path we are
		self.conveyor_path:list[Position] = []
		self.going_clockwise = True
		self.closest_distance_to_target_reached= float('inf')
		if ct.get_current_round() >= 50:
			self.add_task(ct, BuilderTask.FIND_ENEMY_CORE, 0)
		self.add_task(ct,BuilderTask.FIND_ORE, None, True)
		self.symmetry_positions = [
			Position((self.map_width-1) - self.core_pos.x, (self.map_height-1) - self.core_pos.y), 
			Position(self.map_width-1  - self.core_pos.x, self.core_pos.y),
			Position(self.core_pos.x, self.map_height-1 - self.core_pos.y)]
		
		self.symmetry_positions.sort(key=lambda pos: self.chebyshev(ct.get_position(), pos))
		self.first_bridge_built = False
		self.defence_walls_board = 0

	def compute_defence_walls_board(self) -> int:
		"""
		Builds a bitboard of wall positions 4 tiles out from the core centre.
		Skips tiles that are off-map or are already occupied by environmental walls.
		"""
		board = 0
		cx, cy = self.core_pos.x, self.core_pos.y
		radius = 6

		for dx in range(-radius, radius + 1):
			for dy in range(-radius, radius + 1):
				# Only keep perimeter tiles — skip interior
				if abs(dx) != radius and abs(dy) != radius:
					continue
				nx, ny = cx + dx, cy + dy
				if not (0 <= nx < self.map_width and 0 <= ny < self.map_height):
					continue
				pos = Position(nx, ny)
				if self.check_bit(self.walls_board, pos):
					continue
				board = self.set_bit(board, pos)
		self.protected_area = self.generate_mask([0b11111111111]*11)
		h_shift = self.core_pos.x-5
		if h_shift>0:
			for i in range(h_shift):
				self.protected_area = ((self.protected_area)<<1)&self.inverted_left_mask
		elif h_shift<0:
			for i in range(-h_shift):
				self.protected_area = ((self.protected_area)>>1)&self.inverted_right_mask
		v_shift = self.core_pos.y-5

		if v_shift>0:
			for i in range(v_shift):
				self.protected_area = ((self.protected_area)<<self.map_width)
		elif h_shift<0:
			for i in range(-h_shift):
				self.protected_area = ((self.protected_area)>>self.map_width)
		self.protected_area&=self.max_int
		return board

	def get_task_secondary_priority(self, ct: Controller, task: TaskData):
		prio = float('inf')
		match task['type']:
			case BuilderTask.FOUND_ORE:
				prio = ct.get_position().distance_squared(task['data'])
			case BuilderTask.PLACE_SENTINEL:
				if self.enemy_core_pos:
					prio = self.enemy_core_pos.distance_squared(task['data'])
		return prio

	def read_task_marker(self, ct: Controller, entity):
		read = TaskMarkerData()
		read.as_int = ct.get_marker_value(entity)
		if read.date == ct.get_current_round():
			if self.task:
				if read.task_type == self.task["type"]and self.task["type"] in DO_ONCE_TASKS and read.task_identifier == self.task["identifier"]:
					self.task['timeout'] = ct.get_current_round()+25
					self.invalid_tasks.append(self.task)
					self.task_complete(ct)
			# TODO: right now identifier is always a position this is jank
			# try and not stand on where another bot is trying to do something
			if read.task_type in DO_ONCE_TASKS:
				pos_index = read.task_identifier
				clear_out_pos = Position(pos_index % self.map_width, floor(pos_index/self.map_width))
				if clear_out_pos != ct.get_position():
					self.clear_bit(self.walkable_board, clear_out_pos)

	

	
	
	def get_neighbours(self, pos: Position):
		"""
		Returns walkable neighbour positions (non-wall, in-bounds)
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
		
		neighbours = (self.walkable_board|(~self.seen_board)) & neighbour_bit_mask&self.connected_region
		while neighbours:
			(neighbours, nb) = self.pop_lsb(neighbours)
			yield nb

	@lru_cache(maxsize=2)
	def get_full_lines_board(self, round:int):
		capacity_board = 0
		for i in self.conveyor_lines:
			if len(self.conveyor_lines[i]['harvesters'])>=4:
				capacity_board|=self.conveyor_lines[i]['bitboard']
		return capacity_board

	def get_bridge_neighbours(self, pos: Position, goal_bitmask:int, round:int):
		"""
		Returns bridge-buildable neighbour positions (non-wall, non-ore, in-bounds) (avoid building bridges on ore for now)
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
		
		if pos.y<3:
			remove_mask = 0
			for i in range(3-pos.y):
				remove_mask |= self.bridge_neighbour_horizontal_mask<<(self.map_width*i)
			neighbour_bit_mask &= ~remove_mask
		elif pos.y >= self.map_height-3:
			remove_mask = 0
			for i in range(3-(self.map_width-1-pos.y)):
				remove_mask |= self.bridge_neighbour_horizontal_mask<<(self.map_width*(4+i))
			neighbour_bit_mask &= ~(remove_mask)
		index = pos.y*self.map_width + pos.x
		neighbour_bit_mask<<=index
		# shift to recenter bitmask on index - order is important, else we might delete part of the mask
		neighbour_bit_mask >>= self.map_width*3 + 3


		neighbours = neighbour_bit_mask & (goal_bitmask | ~(self.get_full_lines_board(round)))
		neighbours &= (self.walkable_board|(~self.seen_board))  & ~(self.axionite_ores_board | self.titanium_ores_board | self.defence_walls_board)
		neighbours &= self.connected_region
		if ids:= self.conveyor_ids[pos]:
			for id in ids:
				if len(self.conveyor_lines[id]['harvesters'])<4:
					for i in range(len(self.conveyor_lines[id]['positions'])):
						if self.conveyor_lines[id]['positions'][i] == pos:
							yield from self.conveyor_lines[id]['positions'][i+1:]
							break
				break
			
		while neighbours:
			(neighbours, nb) = self.pop_lsb(neighbours)
			yield nb

	def ara(self,ct:Controller, start: Position, goal: Position, timelimit:int, bridge:bool =False, from_save_state=False):
		starttime = ct.get_cpu_time_elapsed()
		neighbour_function = self.get_neighbours
		round = ct.get_current_round()
		if bridge:
			goal_bitmask = self.get_bitmask(goal)
			neighbour_function = lambda pos: self.get_bridge_neighbours(pos, goal_bitmask, round)
		current = None
		target_radius_sq = 0 if bridge else self.target_radius_sq
		best_goal_score = float('inf')
		best_goal_pos = None
		weight:float = 2.5
		if not from_save_state:
			# can happen occasionally
			if start.distance_squared(goal) <= target_radius_sq:
				print("already at target")
				return None
			counter:int = 0 
			open_set:list[tuple[float, int, Position]] = []
			inconsistent_set = []
			heapq.heappush(open_set, (0, counter, start))
			came_from = {}
			g_score:dict[Position,float] = {start: 0}
			goals = set()
			for pos in self.positions_in_radius(goal, target_radius_sq):
				if self.check_bit(self.walkable_board|(~self.seen_board), pos):
					goals.add(pos)
					g_score[pos] = float('inf')
			
		else:
			print('Pathfinding resumed from last turn')
			counter = self.pathfinding_save_state['counter']
			open_set = self.pathfinding_save_state['open_set']
			inconsistent_set = self.pathfinding_save_state['inconsistent_set']
			came_from = self.pathfinding_save_state['came_from'] 
			g_score = self.pathfinding_save_state['g_score'] 
			weight = self.pathfinding_save_state['weight']
			goals = self.pathfinding_save_state['goals']
			goal = self.pathfinding_save_state['goal']
			start = self.pathfinding_save_state['start']
			

		out_of_time = False
		while weight>=1 and open_set and (not out_of_time):
			if not from_save_state:
				closed_set = set()
			else:
				from_save_state = False
				closed_set = self.pathfinding_save_state['closed_set']
			while open_set:
				# we failed to find a path on this run through: save our state in case we need to keep calculating next turn
				if ct.get_cpu_time_elapsed()-starttime>timelimit or ct.get_cpu_time_elapsed()>1900:
					out_of_time = True
					if not bridge:
						self.pathfinding_save_state['counter'] = counter
						self.pathfinding_save_state['open_set'] = open_set
						self.pathfinding_save_state['inconsistent_set'] = inconsistent_set
						self.pathfinding_save_state['came_from'] = came_from
						self.pathfinding_save_state['g_score'] = g_score
						self.pathfinding_save_state['weight'] = weight
						self.pathfinding_save_state['goals'] = goals
						self.pathfinding_save_state['goal'] = goal
						self.pathfinding_save_state['start'] = start
						self.pathfinding_save_state['closed_set'] = closed_set
					break
				f, _, current = heapq.heappop(open_set)
				#this is our exit condition
				if best_goal_score<=f:
					break

				closed_set.add(current)
				for neighbour in neighbour_function(current):
					
					# Uniform cost of 1 per step for now
					# added a cost to build roads (we don't need to worry about this when generating a bridge path)
					extra_cost = 0
					if not bridge and not self.check_bit(self.team_buildings_board| self.enemy_buildings_board, neighbour):
						extra_cost += 0.5
					if bridge:
						if self.check_bit(self.enemy_buildings_board, neighbour):
							# add a cost if we need to build over enemy buildings
							extra_cost +=1
						#add a cost for building a bridge instead of a conveyor
						if current.distance_squared(neighbour)>1:
							extra_cost +=10
					
					# if self.check_bit(self.units_adjacent_board, neighbour):
					# 	extra_cost+=1
					tentative_g = g_score[current] + 1 +extra_cost
					
					# Checks if this path to the neighbour is better than any previously recorded path (or if there is no recorded path)
					# The second argument is the default value if neighbour is not in g_score, which is infinity as we want to consider any path to it as better than no path.
					if tentative_g < g_score.get(neighbour, float('inf')):
						came_from[neighbour] = current
						g_score[neighbour] = tentative_g
						if tentative_g< best_goal_score and neighbour in goals:
							best_goal_score = tentative_g
							best_goal_pos = neighbour
							
						# Heuristic target: if goal is ore, we aim for adjacency (distance 1),
						# so we substract 1 from the chebyshev distance to stay admissible.
						# This is where the magic happens. The heuristic is what differentiates the neighbours. We want to prioritise neighbours that are closer to the target (Chebyshev distance). 
						if bridge:
							h = self.chebyshev(neighbour, goal)
						else:
							# this has been changed so that we are now aiming for any tile within a radius
							# the floor part here is always guaranteed to underestimate the chebychev distance of a target so that we remain admissable
							h = max(0, self.chebyshev(neighbour, goal) - floor(pow(self.target_radius_sq, 0.5)))
						
						#here is where the weighted part comes in (we overestimate the score to decrease the number of nodes we need to expand before we reach the end)
						f_score = tentative_g +weight* h
						counter += 1
						
						if neighbour in closed_set:
							heapq.heappush(inconsistent_set, (f_score, counter, neighbour))
						else:
							heapq.heappush(open_set, (f_score, counter, neighbour))
			open_set = open_set + inconsistent_set
			heapq.heapify(open_set)
			weight-=0.5

			#open_set[0][0] is the least f score in the heap
			# path_rating = min(weight, g_score[goal]/open_set[0][0])
		
		if best_goal_pos:
			print(f'Chose to pathfind to: {best_goal_pos.x} {best_goal_pos.y}')
			return self.reconstruct_path(came_from, best_goal_pos)
		
		# No path found, set the pathfinding interrupted flag:
		if not bridge:
			if out_of_time:
				print('Pathfinding was interrupted, will resume next turn')
				self.pathfinding_interrupted = True
			else:
				#there is just no path to that point
				print("No path exists")
				self.task_complete(ct)
		return None

	def positions_in_radius(self, pos:Position,radius_sq:float):
		max_diff = floor(radius_sq**0.5)
		max_y = min(max_diff, self.map_height-1-pos.y)
		min_y = max(-pos.y, -max_diff)
		max_x = min(max_diff, self.map_width-1-pos.x)
		min_x = max(-pos.x, -max_diff)
		for y in range(min_y, max_y+1):
			for x in range(min_x, max_x+1):
				if x**2+y**2 <= radius_sq:
					yield Position(pos.x+x, pos.y+y)

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
	
	def compute_path(self,ct:Controller, start: Position, goal: Position):
		"""
		Runs A* and stores the result as noth a position list and a path bitboard.
		"""
		#check if there are actually any points we can pathfind to
		is_free_space = False
		valid_pathfinding_spots = (self.walkable_board|(~self.seen_board)) & self.connected_region
		for pos in self.positions_in_radius(goal, self.target_radius_sq):
			if self.check_bit(valid_pathfinding_spots, pos):
				is_free_space = True
				break
				

		if not is_free_space:
			print('start collided')
			self.reset_path()
			return False
		self.closest_distance_to_target_reached=float('inf')
		if self.do_bug_pathfinding:
			print("Doing bug pathfinding")
			t = ct.get_cpu_time_elapsed()
			result = self.bug_path_find(ct,start,goal, self.target_radius_sq)
			print(f'Took {ct.get_cpu_time_elapsed()-t}')
		else:
			result = self.ara(ct, start, goal, 1300, False)
			if result is None:
				self.reset_path()
				return False
		
		self.path = result
		self.path_index = 0

		return True
	
	def compute_bridge_path(self, ct:Controller, start:Position, goal:Position):
		"""
		Runs A* and stores the result as noth a position list and a path bitboard.
		"""
		#check if there are actually any points we can pathfind to
		if not self.check_bit(self.walkable_board|(~self.seen_board)|self.units_board, goal):
			print('start collided bridge', goal)
			self.reset_path()
			return False
		result = self.ara(ct, start, goal, 900, True)
		if result is None:
			self.reset_bridge_path()
			return False
		
		self.bridge_path =[start]+ result
		self.bridge_path_index = 0
		self.known_bridges_at_path_construction = self.team_conveyors_board|self.enemy_conveyors_board
		# Build the path bitboard for collision detection later 
		self.bridge_path_board = 0
		for pos in self.bridge_path:
			self.bridge_path_board = self.set_bit(self.bridge_path_board, pos)

		return True



	def check_path_collisions(self, path, index, bridge=False) -> int:
		"""
		Returns the bitboard of collisions if any obstacle now overlaps the remaining path.
		"""
		#TODO this is slow, we should create the path bitboard at creation of the path, then remove bits from the remaining board as we go through the path.
		remaining_board = 0
		# The : after self.path_index is string slicing to get the remaining path from the current position to the target
		for pos in path[index:]:
			remaining_board = self.set_bit(remaining_board, pos)

		# mask away walls
		mask = ~self.walkable_board & self.seen_board
		# if we are building a bridge, avoid enemy roads and the core
		if bridge:
			# since the last point in the bridge is our target, this could be the core or another bridge, we don't want to consider it for collisions
			remaining_board = self.clear_bit(remaining_board, path[-1])
			# don't want to build a bridge over ore
			mask |= self.titanium_ores_board | self.axionite_ores_board | self.defence_walls_board
			#don't want to build onto our own conveyors, that we didn't know about at path construction
			mask |= self.team_conveyors_board & (~self.known_bridges_at_path_construction)
			#eprint(remaining_board&self.team_conveyors_board, remaining_board&(self.titanium_ores_board | self.axionite_ores_board), remaining_board&(~self.walkable_board & self.seen_board))
		return (remaining_board & mask)

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
			dist_to_target = next_pos.distance_squared(self.target)
			if self.closest_distance_to_target_reached>dist_to_target:
				self.closest_distance_to_target_reached = dist_to_target
			return True
		
		return False
	
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
	
	def check_symmetry(self) -> None:
		super().check_symmetry()
		if self.map_symmetry:
			self.enemy_core_pos = self.apply_symmetry(self.core_pos)
	
	def turn_start(self, ct: Controller):
		super().turn_start(ct)
		self.count=0
		self.debug = False
		for i in range(len(self.task_backlog)):
			t= self.task_backlog[i]
			print(f'Qd Task no. {i+1}: {t['type']}, Data: {t['data']}')
		# Update our map with any newly visible terrain
		self.update_terrain_vision(ct)
		if not self.defence_walls_board:
			self.defence_walls_board = self.compute_defence_walls_board()
		#check for symmetry
		if self.map_symmetry == MapSymmetry.UNKNOWN:
			self.check_symmetry()
		print(f'Map Symmetry: {MAP_SYMMETRY_PLAINTEXT[self.map_symmetry]}')
		print(f'Before processing tasks {ct.get_cpu_time_elapsed()} micros')
		if self.pathfinding_interrupted:
			self.pathfinding_interrupted = False
			
			
			self.pathfinding_save_state['time_out']-=1
			if self.pathfinding_save_state['time_out'] == 0:
				print("A star failed to find a path in time, do bug pathfinding")
				self.do_bug_pathfinding=True
			else:
				#doesn't matter what arguments we put in for goal and start, as we are recovering the state from the saved one anyway
				result = self.ara(ct, Position(0,0), Position(0,0), 1000, from_save_state=True)
				if result:
					self.path = result
					self.path_index = 0
			
		task_time = ct.get_cpu_time_elapsed()
		keep_processing_tasks = True
		count = 0
		while (keep_processing_tasks and not self.pathfinding_interrupted):
			count+=1
			if count>20:
				print('cancelled processing')
				break
			current_pos = ct.get_position()
			task_time = ct.get_cpu_time_elapsed()
			keep_processing_tasks = self.process_tasks(ct)
			print (f'Task took {ct.get_cpu_time_elapsed()-task_time}μs')
			pathfind_time = ct.get_cpu_time_elapsed()
			# if we don't want to pathfind
			if self.target is None or not self.do_pathfinding:
				print('No target/pathfinding off')
				continue
			# if we have a target but no path, compute a path
			elif not self.path:
				self.compute_path(ct, current_pos, self.target)
			# Check if cached path from the previous turn has been blocked
			elif (collisions:=self.check_path_collisions(self.path, self.path_index)):
				# Path is blocked, need to recompute
				if self.do_bug_pathfinding:
					#ignore the collision unless it is directly in front of us to save on computation
					next_pos = self.path[self.path_index]
					if self.check_bit(collisions, next_pos):
						#if we collide with a unit just recompute
						if self.check_bit(self.units_board, next_pos):
							self.compute_path(ct, current_pos, self.target)
							break
						pos_before_collision = ([current_pos]+self.path)[self.path_index]
						dir_facing = pos_before_collision.direction_to(next_pos)
						new_path = self.bug_path_find(ct, pos_before_collision, self.target, self.target_radius_sq, dir_facing, self.closest_distance_to_target_reached)
						self.path =self.path[:self.path_index]+new_path
				else:
					self.compute_path(ct, current_pos, self.target)

			# If path is valid follow it
			if self.path:
				if self.path_index>0 and self.path_index<=len(self.path):
					if self.path[self.path_index-1] != current_pos:
						print('got launched')
						self.compute_path(ct, current_pos, self.target)
				self.follow_path(ct)
			else:
				print('No path to follow.')
			
			print (f'Pathfinding took {ct.get_cpu_time_elapsed()-pathfind_time}μs')
			print(f'Current Target: {self.target}, RadiusSq: {self.target_radius_sq}')
			print(f"Path: {self.path_string(self.path)}")
			print(f'Bridge Path: {self.path_string(self.bridge_path)}')
			print(f'Conveyor Path: {self.path_string(self.conveyor_path)}')
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
		# if there are some tasks in the back log and our current task is interruptable
		original_task = None
		self.cull_task_backlog(ct)
		if self.task and self.task['interruptable'] and self.task_backlog:
			self.task_backlog.append(self.task)
			original_task = self.task
			self.task = None
		if not self.task:
			self.sort_task_backlog(ct)
			if self.task_backlog:
				self.task = self.task_backlog.pop(0)
				if not original_task == self.task:
					if original_task:
						print(f'Original task interrupted\nOrig: {original_task['type']}, Data: {original_task['data']}, I: {int(original_task["interruptable"])}')
					self.end_task()
				else:
					print('Task was not interrupted')
		if self.task['type'] not in ESSENTIAL_TASKS and ct.get_global_resources()[0]<ct.get_gunner_cost()[0]*1.5:
			print('Task processing paused: not enough money to defend')
			return False
		print(f'Task: {self.task['type']}, Data: {self.task['data']}, P: {self.phase}')
		current_pos = ct.get_position()
		reached_target = not self.target is None and current_pos.distance_squared(self.target) <=self.target_radius_sq
		self.target: Position
		return builder_tasks[self.task['type']]['phases'][self.phase](self, ct, reached_target)

	def task_complete(self, ct:Controller):
		self.end_task()
		if not self.first_bridge_built and self.task['type'] == BuilderTask.BUILD_BRIDGE:
			self.first_bridge_built = True
			ESSENTIAL_TASKS.remove(BuilderTask.BUILD_BRIDGE)
		super().task_complete(ct)
		self.add_task(ct,BuilderTask.FIND_ORE, None, True)

	
	def end_task(self):
		"""Clears all the pathfinding and general shenanigans to prep for a new task - different to task_complete in that it does not edit the task"""
		#reset the paths upon task completion
		self.target = None
		self.reset_bridge_path()
		self.reset_path()
		self.conveyor_path = []
		self.phase = 0
		self.do_pathfinding = True
		self.pathfinding_interrupted = False
		self.pathfinding_save_state = {'time_out':1}
		

	def reset_path(self):
		self.path = []
		self.path_index = 0
		self.do_bug_pathfinding=False
		self.closest_distance_to_target_reached = float('inf')
	
	def reset_bridge_path(self):
		self.bridge_path = []
		self.bridge_path_index =0
		self.bridge_path_board =0
		self.known_bridges_at_path_construction = 0
	
	def change_target(self, target:Position, radius_sq=2):
		"""
		Changes the target to this point resetting the current path, where we stop if we reach any point in the radius.
		Default behaviour is to aim at an adjacent tile.
		Note: be careful as we are using radius squared.
		Use radius_sq=0 if you want to only stop once we are on top of the target and 2 to aim for any adjacent tile.
		"""
		self.reset_path()
		self.target = target
		self.target_radius_sq = radius_sq
	
	#if we are fixing a path, specify the direction we were facing before the collision and closest distance squared we have been to the goal, in order to prevent backtracking
	def bug_path_find(self,ct:Controller, start:Position, goal:Position, goal_radius_sq:int, facing:(Direction|None)=None, closest_distance_sq:float=0):
		path = [start]
		if not facing:
			path += self.straight_path_to_target(ct, start, goal, goal_radius_sq)
		#follow the obstacle around in clockwise manner until we are closer than before
		obstacle_board = (~self.walkable_board)&self.seen_board
		change_direction = False
		change_direction_consecutive_counter = 0
		while path[-1].distance_squared(goal) > goal_radius_sq:
			if change_direction:
				change_direction_consecutive_counter+=1
			else:
				change_direction_consecutive_counter=0
			if change_direction_consecutive_counter==2:
				# something definitely went wrong
				return[]
			change_direction = False
			current_pos = path[-1]
			if facing:
				check_dir = facing
				facing = None				
			else:
				check_dir = path[-1].direction_to(goal)
				closest_distance_sq = current_pos.distance_squared(goal)
			path_around_obstacle = []
			visited = set()
			visited_twice = set()
			while current_pos.distance_squared(goal)>= closest_distance_sq:
				if current_pos in visited:
					if current_pos in visited_twice:
						#some weird shenanigans has happened, we have collided with a unit somewhere so now we are going in circles,
						# I think if I return an empty path, the bot might eventually recover
						return[]
					visited_twice.add(current_pos)
				visited.add(current_pos)
				check_pos = current_pos.add(check_dir)
				#if we run off the edge of the map, change the way we are going around the obstacle
				if not self.is_valid_position(check_pos):
					change_direction = True
				while (not change_direction) and self.check_bit(obstacle_board,check_pos):
					check_dir = check_dir.rotate_left() if self.going_clockwise else check_dir.rotate_right()
					check_pos = current_pos.add(check_dir)
					#if we run off the edge of the map, change the way we are going around the obstacle
					if not self.is_valid_position(check_pos):
						change_direction = True

				if change_direction:
					self.going_clockwise= not self.going_clockwise
					path_around_obstacle = []
					current_pos = path[-1]
					break

				current_pos = check_pos
				path_around_obstacle.append(current_pos)			
				check_dir = check_dir.rotate_right() if self.going_clockwise else check_dir.rotate_left()
				if check_dir in CARDINAL_DIRECTIONS:
					check_dir = check_dir.rotate_right() if self.going_clockwise else check_dir.rotate_left()
			path+=path_around_obstacle
			path += self.straight_path_to_target(ct, current_pos, goal, goal_radius_sq)
		return path[1:]



	#returns (path, destination)
	#where path: Direction[] and destination: Position
	#returns the path to the furthest we can get in the direction of end goal in the naive approach
	def straight_path_to_target(self,ct:Controller, start:Position, end:Position, end_radius_sq:int):
		path_dir = Position(end.x-start.x, end.y-start.y)
		steps = max(abs(path_dir.x), abs(path_dir.y))
		num_diag = min(abs(path_dir.x), abs(path_dir.y))
		num_non_diag = steps - num_diag
		
		y_dir = Direction.SOUTH if path_dir.y>=0 else Direction.NORTH
		x_dir = Direction.EAST if path_dir.x>=0 else Direction.WEST
		non_diag_direction =x_dir if abs(path_dir.x) > abs(path_dir.y) else y_dir
		diag_direction = closest_diagonal(x_dir, y_dir)
		current_pos = start
		path = []
		for i in range(steps):
			if current_pos.distance_squared(end) < end_radius_sq:
				return path
			# try and go diagonal first
			if num_diag:
				check_pos = current_pos.add(diag_direction)
				if self.check_bit(self.walkable_board|(~self.seen_board),check_pos):
					num_diag-=1
					path.append(check_pos)
					current_pos = check_pos
					continue
			
			#go in the non-diagonal direction
			if not num_non_diag:
				return path
			check_pos = current_pos.add(non_diag_direction)
			if self.check_bit(self.walkable_board|(~self.seen_board),check_pos):
				path.append(check_pos)
				current_pos = check_pos
				num_non_diag -= 1
			else:
				return path
		return path


