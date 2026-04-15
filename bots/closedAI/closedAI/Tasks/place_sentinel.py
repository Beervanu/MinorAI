# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot
from ..helper_functions import eprint
from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, Direction, EntityType, GameConstants
from ..Constants import DIRECTIONS, CARDINAL_DIRECTIONS

task_type = BuilderTask.PLACE_SENTINEL # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):
	self.change_target(self.task['data'], 0)
	self.phase+=1
	return True

def attack(self: BuilderBot, ct:Controller, reached_target: bool):
	if not is_valid(self,ct, self.task):
		self.task_complete(ct)
		return True
	if reached_target:
		if self.check_bit(self.enemy_buildings_board, self.target):
			if ct.can_fire(self.target):
				ct.fire(self.target)
		elif self.check_bit(self.team_buildings_board, self.target):
			if ct.can_destroy(self.target):
				ct.destroy(self.target)
				self.phase+=1 
				return True
		else:
			self.phase+=1
			return True
	elif not self.check_bit(self.walkable_board, self.target):
		self.task_complete(ct)
		return True

def place_sentinel(self: BuilderBot, ct:Controller, reached_target: bool):
	if not is_valid(self,ct, self.task):
		self.task_complete(ct)
		return True

	#if someone places something under us, go back to attacking it 
	if self.check_bit(self.enemy_buildings_board, self.target):
		self.phase-=1
		return True
	
	if ct.can_destroy(self.target):
		ct.destroy(self.target)
	if ct.get_action_cooldown()==0 and ct.get_move_cooldown()==0 and ct.get_global_resources()>ct.get_sentinel_cost():
		#move out of the way and place a sentinel
		for d in DIRECTIONS:
			if ct.can_move(d):
				ct.move(d)
				break
		source_dir = Direction.CENTRE
		found_source = False
		can_face_any = False
		core_in_range = self.map_symmetry and self.target.distance_squared(self.enemy_core_pos)<=GameConstants.SENTINEL_VISION_RADIUS_SQ
		for d in CARDINAL_DIRECTIONS:
			check_pos = self.target.add(d)
			# TODO: change to add any conveyor
			if self.is_valid_position(check_pos):
				if self.check_bit(self.titanium_ores_board|self.axionite_ores_board, check_pos):
					found_source = True
				elif self.check_bit(self.enemy_buildings_board, check_pos):
					b_id = ct.get_tile_building_id(check_pos)
					if ct.get_entity_type(b_id) in [EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR]:
						#if this conveyor is feeding us
						if ct.get_direction(b_id) == d.opposite():
							found_source = True
			if found_source:
				# this checks if we have already found another source
				# if there is more than one thing feeding this spot, we can face any direction
				if source_dir != Direction.CENTRE:
					can_face_any = True
					break
				source_dir = d
				if not core_in_range:
					break
		if core_in_range:
			build_dir = self.target.direction_to(self.enemy_core_pos)
			for i in range(8):
				if not can_face_any and build_dir == source_dir:
					build_dir = build_dir.rotate_left()
				if ct.can_fire_from(self.target, build_dir, EntityType.SENTINEL, self.enemy_core_pos):
					break
				build_dir.rotate_left()
		else:
			build_dir = source_dir.opposite()
				
		# if we didn't find a source, don't build a sentinel
		if source_dir == Direction.CENTRE:
			self.task_complete(ct)
			return True		
			
		if ct.can_build_sentinel(self.target, build_dir):
			ct.build_sentinel(self.target, build_dir)
			self.task_complete(ct)

def is_valid(self:BuilderBot,ct:Controller, task:TaskData)->bool:
	if not self.check_bit(self.connected_region, task['data']):
		return False
	for p in self.conveyors_pointing_into[task['data']]:
		for id in self.conveyor_ids[p]:
			if self.conveyor_lines[id]['harvesters']:
				return True
			break
	return False

phases = [set_target, attack, place_sentinel]
do_once = True


