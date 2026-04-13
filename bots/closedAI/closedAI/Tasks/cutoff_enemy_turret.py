from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask, TaskData
from ..Constants import CARDINAL_DIRECTIONS, DIRECTIONS
from cambc import Controller, EntityType
from ..helper_functions import eprint
task_type = BuilderTask.CUTOFF_ENEMY_TURRET # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):
	turret_pos = self.task['data']
	for dir in CARDINAL_DIRECTIONS:
		check_pos = turret_pos.add(dir)
		if self.is_valid_position(check_pos) and ct.is_in_vision(check_pos):
			b_id= ct.get_tile_building_id(check_pos)		
			if b_id:
				if ct.get_entity_type(b_id)in[EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR]:
					if ct.get_direction(b_id)==dir.opposite():
						self.change_target(check_pos)
						self.phase=1
						return True
				elif ct.get_entity_type(b_id)==EntityType.HARVESTER:
					for d2 in CARDINAL_DIRECTIONS:
						# want to build a gunner on a diagonal to the sentinel
						# probably should check if we are in range of the sentinel
						if d2 in [dir, dir.opposite()]:
							continue

						check_pos2 = check_pos.add(d2)
						if self.is_valid_position(check_pos2) and ct.is_in_vision(check_pos2):
							b_id = ct.get_tile_building_id(check_pos2)
							if b_id and ct.get_entity_type(b_id)==EntityType.GUNNER and ct.get_team(b_id)==ct.get_team():
								self.task_complete(ct)
								return True
							self.change_target(check_pos2, 2)
							self.phase=2
							return True
	#successfully cutoff
	self.task_complete(ct)
	return True

def remove_feeding_conveyor(self:BuilderBot, ct:Controller, reached_target:bool):
	if reached_target:
		b_id = ct.get_tile_building_id(self.target)
		if b_id and ct.get_entity_type(b_id) == EntityType.CONVEYOR:
			if ct.can_destroy(self.target):
				ct.destroy(self.target)
			if ct.can_fire(self.target):
				ct.fire(self.target)
			return False
		else:
			self.phase = 0
			return True
		

def destroy_turret(self:BuilderBot, ct:Controller, reached_target:bool):
	if reached_target:
		if ct.can_destroy(self.target):
			ct.destroy(self.target)
		if ct.can_fire(self.target):
			ct.fire(self.target)
		# try and move on top of the spot
		b_id = ct.get_tile_building_id(self.target)
		if not b_id:
			if ct.get_action_cooldown()==0 and ct.get_move_cooldown()==0 and ct.get_global_resources()>ct.get_gunner_cost():
				#move out of the way and place a gunner
				for d in DIRECTIONS:
					if ct.can_move(d):
						ct.move(d)
						break
				build_dir = self.target.direction_to(self.task['data'])
				if ct.can_build_gunner(self.target, build_dir):
					ct.build_gunner(self.target, build_dir)
					self.task_complete(ct)
					return True
		if ct.can_move(dir:=ct.get_position().direction_to(self.target)):
			ct.move(dir)
			self.change_target(self.target, 0)

#is called before we switch to this task, and can be used to cull the task if it ever becomes invalid
def is_valid(self: BuilderBot, ct:Controller, task:TaskData)->bool:
	conveyor_spotted = False
	if ct.is_in_vision(task['data']):
		for d in DIRECTIONS:
			check_pos = task['data'].add(d)
			if self.is_valid_position(check_pos) and ct.is_in_vision(check_pos):
				b_id= ct.get_tile_building_id(check_pos)		
				if b_id:
					etype = ct.get_entity_type(b_id)
					if etype in[EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR]:
						if ct.get_direction(b_id)==d.opposite():
							conveyor_spotted=True
					elif etype == EntityType.HARVESTER:
						conveyor_spotted=True
					elif etype == EntityType.GUNNER:
						return False	
		return conveyor_spotted
	else:
		return True
	return False

phases = [set_target, remove_feeding_conveyor, destroy_turret]
#TODO change this
do_once = True