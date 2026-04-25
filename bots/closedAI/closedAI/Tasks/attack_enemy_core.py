# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, ResourceType,EntityType
from ..Constants import DIRECTIONS

task_type = BuilderTask.ATTACK_ENEMY_CORE # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):
	self.change_target(self.enemy_core_pos, 10)
	self.phase+=1
	return True

def find_bridges(self: BuilderBot, ct:Controller, reached_target: bool):
	if reached_target:
		attack_mask = self.core_attack_range_symmetry_masks[self.map_symmetry-1]
		in_range_bridges = self.enemy_conveyors_board&attack_mask
		while (in_range_bridges):
			in_range_bridges, pos = self.pop_lsb(in_range_bridges)
			if not ct.is_in_vision(pos):
				continue
			b_id = ct.get_tile_building_id(pos)
			if b_id and ct.get_stored_resource(b_id) == ResourceType.TITANIUM:
				if ct.get_entity_type(b_id) == EntityType.BRIDGE:
					check_pos = ct.get_bridge_target(b_id)
				else:	
					check_pos = pos.add(ct.get_direction(b_id))
				if self.is_valid_position(check_pos) and self.check_bit(self.walkable_board, check_pos):
					self.add_task(ct,BuilderTask.PLACE_SENTINEL, check_pos, False)
					self.task_complete(ct)
					return True

def is_valid(self:BuilderBot,ct:Controller, task:TaskData):
	if self.enemy_core_pos is None:
		return False
	for d in DIRECTIONS:
		check_pos = self.enemy_core_pos.add(d).add(d)
		if self.check_bit(self.connected_region,check_pos):
			return True
	return False

	

phases = [set_target, find_bridges]
do_once = False