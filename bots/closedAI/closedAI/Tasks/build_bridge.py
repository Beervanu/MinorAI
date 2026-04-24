# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot
from ..Constants import DIRECTIONS, CONVEYOR_ENTITIES
from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, Position, EntityType, Direction
from ..helper_functions import eprint
task_type = BuilderTask.BUILD_BRIDGE # some BuilderTask

def generate_path(self: BuilderBot, ct:Controller, reached_target: bool):
	# eprint('gen')
	current_pos = ct.get_position()	
	#if this is the start of us building a bridge (i.e. first placement)
	bridge_start = None
	if not self.bridge_path:
		bridge_start: Position = self.task['data']
	elif self.target:
		
		#if we are mid building the bridge and we had a collision
		bridge_start = self.bridge_path[self.bridge_path_index]
	else:
		eprint('This happens?')

	#if we had a collision while building a bridge (or while walking over to the start of some bridge)
	if bridge_start:
		if self.check_bit(self.units_board, bridge_start):
			#wait it out
			self.do_pathfinding = False
			return False
		elif not self.check_bit(self.walkable_board, bridge_start) or self.check_bit(self.team_conveyors_board, bridge_start):
			# if we have a collision directly in front of us and its not a unit, panic and complete task
			# TODO: destroy the previously made path and reconstruct around obstacle
			self.task_complete(ct)
			return True
		
	#if we are mid building conveyors and we had a collision
	else:
		# TODO: need logic to stop an error if we build a bridge that points initially to an empty space, then gets built over by an enemy bot
		
		if ct.can_destroy(current_pos):
			ct.destroy(current_pos)
		#I cba deal with this case
		if self.check_bit(self.axionite_ores_board|self.titanium_ores_board, current_pos):
			self.task_complete(ct)
			return True
		bridge_start = current_pos
	
	capacity_board = 0
	for i in self.conveyor_lines:
		if len(self.conveyor_lines[i]['harvesters'])<4 and self.conveyor_lines[i]['feeds_team']==ct.get_team():
			capacity_board|=self.conveyor_lines[i]['bitboard']
	capacity_board|=self.core_mask

	region_bitboard = self.set_bit(0, bridge_start)
	while not region_bitboard&capacity_board:
		region_bitboard |= (region_bitboard<<1)&self.inverted_left_mask
		region_bitboard |= (region_bitboard>>1)&self.inverted_right_mask
		region_bitboard |= (region_bitboard>>self.map_width)
		region_bitboard |= (region_bitboard<<self.map_width)
	
	(_, goal) = self.pop_lsb(region_bitboard&capacity_board)
	self.compute_bridge_path(ct, bridge_start, goal)
	#if there is no path from this start we just abandon this harvester
	if not self.bridge_path:
		self.task_complete(ct)
		return True
	self.change_target(self.bridge_path[0], 2)
	self.phase+=1
	self.do_pathfinding = True
	return True

def choose_bridge_type(self:BuilderBot, ct:Controller, reached_target:bool):
	# eprint('choose')
	#if we have a collision go back to generating a path
	if self.check_path_collisions(self.bridge_path, self.bridge_path_index, True):
		self.phase-=1
		self.do_pathfinding = False
		return True
	self.do_pathfinding = True
	if reached_target:
		#get rid of roads/markers in the way
		building_id = ct.get_tile_building_id(self.target)
		if building_id:
			etype = ct.get_entity_type(building_id)
			if etype in [EntityType.ROAD, EntityType.MARKER] and ct.can_destroy(self.target):
				ct.destroy(self.target)
			# if we accidentally build on a team bridge or the core we did good
			elif(etype in CONVEYOR_ENTITIES or etype==EntityType.CORE) and ct.get_team(building_id) == ct.get_team():
				self.task_complete(ct)
				return True
			elif etype == EntityType.CORE:
				#enemy core
				self.task_complete(ct)
				return True
			elif ct.get_team(building_id) != self.team and etype != EntityType.MARKER:
				#attack the building
				self.phase =3
				return True

		#try to build a bridge or a conveyor		
		if ct.get_action_cooldown() == 0:
			
			next_bridge_point = self.bridge_path[self.bridge_path_index+1]
			x_diff =next_bridge_point.x-self.target.x
			if x_diff:
				x_dir = None
				match int(x_diff/abs(x_diff)):
					case 1:
						x_dir=Direction.EAST
					case -1:
						x_dir =Direction.WEST

			y_diff = next_bridge_point.y-self.target.y
			if y_diff:
				y_dir = None
				match int(y_diff/abs(y_diff)):
					case 1:
						y_dir = Direction.SOUTH
					case -1:
						y_dir = Direction.NORTH
			#if we are going diagonal, skip building conveyors and just use a bridge
			buildable_board = self.walkable_board & ~(self.axionite_ores_board|self.titanium_ores_board|self.team_conveyors_board) 
			buildable_board |= self.get_bitmask(next_bridge_point)
			current_pos = self.target
			self.conveyor_path = [self.target]
			for i in range(self.chebyshev(next_bridge_point, self.target)):
				check_directions = []
				if next_bridge_point.y-self.target.y:
					check_directions.append(y_dir)
				if next_bridge_point.x-self.target.x:
					check_directions.append(x_dir)
				
				for dir in check_directions:
					check_pos =current_pos.add(dir)
					if not self.is_valid_position(check_pos):
						continue

					if self.check_bit(buildable_board, check_pos):
						self.conveyor_path.append(check_pos)
						current_pos = check_pos
						#if we are able to build a full conveyor to the next point
						if current_pos == next_bridge_point:
							#turn off normal path finding
							self.do_pathfinding = False
							self.phase+=1
							return True
			self.conveyor_path = []

			#if we failed building conveyors, try to build a bridge instead
			if ct.can_build_bridge(self.target, next_bridge_point):
				
				ct.build_bridge(self.target, next_bridge_point)
				self.bridge_path_index+=1
				

				#if we have finished building the bridge
				if self.bridge_path_index == len(self.bridge_path)-1:
					
					#TODO: spawn a protector bot?
					self.task_complete(ct)
					return True
				self.change_target(self.bridge_path[self.bridge_path_index], 2)



def build_conveyors(self:BuilderBot, ct:Controller, reached_target:bool):
	# eprint('conv')
	current_pos = ct.get_position()
	if self.check_path_collisions(self.conveyor_path, 0, True):
		# we should be standing on a conveyor so destroy it and try building a bridge from here
		if ct.can_destroy(current_pos):
			ct.destroy(current_pos)
		if current_pos not in self.bridge_path:
			self.bridge_path.insert(self.bridge_path_index, current_pos)
		
		#go back to choosing whether to build a bridge or conveyor
		self.change_target(current_pos,2)
		self.phase-=1
		return True
	
	#continue building conveyors
	build_at:Position = self.conveyor_path[0]
	build_to = build_at.direction_to(self.conveyor_path[1])
	building_id = ct.get_tile_building_id(build_at)
	#building will be of our team since we already checked earlier that there are no path collisions
	#if we accidentally path find on to one of our own bridges or conveyors or the core
	if building_id:
		etype = ct.get_entity_type(building_id)
		if etype == EntityType.CORE:
			self.task_complete(ct)
			return True
		elif ct.get_team(building_id) != self.team and etype!= EntityType.MARKER:
			# attack the building
			self.change_target(build_at, 0)
			self.phase=3
			return True
	if ct.get_action_cooldown() == 0 and ct.get_move_cooldown()==0:
		
		etype = ct.get_entity_type(building_id)
		if ct.can_destroy(build_at) and etype in [EntityType.ROAD, EntityType.MARKER]:
			ct.destroy(build_at)
		
		if ct.can_build_conveyor(build_at, build_to):
			ct.build_conveyor(build_at, build_to)
			#move onto where we just built
			if current_pos != build_at:
				m_dir = current_pos.direction_to(build_at)
				if ct.can_move(m_dir):
					ct.move(m_dir)
			self.conveyor_path.pop(0)
			if len(self.conveyor_path) == 1:
				self.bridge_path_index+=1
				#if we are done building the bridge
				if self.bridge_path_index == len(self.bridge_path)-1:
						
					self.task_complete(ct)
					return True
				#else continue building the bridge
				#and turn normal pathfinding back on
				self.do_pathfinding = True
				self.conveyor_path = []
				self.change_target(self.bridge_path[self.bridge_path_index],2)
				self.phase-=1
				return False
			
def attack(self:BuilderBot, ct:Controller, reached_target:bool):
	self.change_target(self.target, 0)
	if not self.do_pathfinding:
		self.do_pathfinding=True
		return True
	if reached_target:
		b_id = ct.get_tile_building_id(self.target)
		if b_id:
			etype = ct.get_entity_type(b_id)
			is_team = self.team == ct.get_team(b_id)
			if is_team:
				if etype in [EntityType.ROAD, EntityType.MARKER] + CONVEYOR_ENTITIES and ct.can_destroy(self.target):
					ct.destroy(self.target)
				else:
					#TODO build around
					self.task_complete(ct)
					return True
			else:
				if ct.can_fire(self.target):
					ct.fire(self.target)
				if ct.can_destroy(self.target):
					ct.destroy(self.target)
				 
		else:
			if self.conveyor_path:
				self.phase=2
				self.do_pathfinding=False
			else:
				self.phase = 1
			return True


def is_valid(self:BuilderBot,ct:Controller, task:TaskData)->bool:
	return bool(self.check_bit(self.connected_region, task['data']))

phases = [generate_path, choose_bridge_type, build_conveyors, attack]
do_once = True