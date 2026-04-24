# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot
from ..helper_functions import eprint
from ..Constants import CARDINAL_DIRECTIONS, CONVEYOR_ENTITIES
from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, GameConstants, EntityType
task_type = BuilderTask.FOUND_TI_ORE # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):
	self.change_target(self.task['data'], 2)
	self.phase +=1
	return True

def get_to_ore(self: BuilderBot, ct:Controller, reached_target: bool):
	current_pos = ct.get_position()
	if not self.check_bit(self.connected_region, self.target):
		self.task_complete(ct)
		return True
	if self.check_bit(self.team_buildings_board, self.target) and current_pos.distance_squared(self.target) <= GameConstants.BUILDER_BOT_VISION_RADIUS_SQ:
		b_id = ct.get_tile_building_id(self.target)
		#if it is a (team) harvester some other bot will have built from it
		if ct.get_entity_type(b_id) == EntityType.HARVESTER: # TODO: should be checking surroundings, to see if if outputs to one of our conveyors/ bridges
			self.task_complete(ct)
			return True
	if reached_target:
		self.phase+=1
		return True

def reached_ore(self:BuilderBot, ct:Controller, reached_target:bool):
	if ct.get_action_cooldown() == 0:
		b_id = ct.get_tile_building_id(self.target)
		# if there is a road on top of it
		if b_id and ct.get_entity_type(b_id) in [EntityType.ROAD, EntityType.MARKER, EntityType.BARRIER]:
			#if we are near enough try to destroy it (only works if it is our road)
			if ct.can_destroy(self.target):
				ct.destroy(self.target)
		b_id = ct.get_tile_building_id(self.target)
		#try building a harvester
		if ct.can_build_harvester(self.target):
			ct.build_harvester(self.target)
		# if there is a unit blocking and no enemy building, wait
		elif not self.check_bit(self.enemy_buildings_board, self.target) and self.check_bit(self.units_board, self.target):
			return False
		#there is no harvester on the ore and something is blocking one being built, so abandon this task
		elif b_id and ct.get_entity_type(b_id) != EntityType.HARVESTER:
			# TODO: attack whatever they placed over the ore
			self.task_complete(ct)
			return True
		#there is a harvester on this ore
		elif b_id:
			self.task['timeout'] = 15
			self.invalid_tasks.append(self.task)
			self.task_complete(ct)
			return True
			
def is_valid(self:BuilderBot,ct:Controller, task:TaskData)->bool:
	#TODO change to checking if a team conveyor is leading from this harvester
	
	if self.check_bit(self.connected_region, task['data']):
		p = task['data']
		for d in CARDINAL_DIRECTIONS:
			check_pos = p.add(d)
			if self.is_valid_position(check_pos):
				for id in self.conveyor_ids[check_pos]:
					if self.conveyor_lines[id]['feeds'] ==EntityType.CORE and self.team == self.conveyor_lines[id]['feeds_team']:
						return False
					break
		return True
	return False


phases = [set_target, get_to_ore, reached_ore]
do_once = True


