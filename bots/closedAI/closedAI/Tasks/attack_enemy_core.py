# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask
from cambc import Controller, ResourceType

task_type = BuilderTask.ATTACK_ENEMY_CORE # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):
	self.change_target(self.enemy_core_pos, 10)
	self.phase+=1
	print("Orig", self.board_string(self.walls_board))
	print("rotat", self.board_string(self.walls_symmetry_boards[0]))
	print("reflect y", self.board_string(self.walls_symmetry_boards[1]))
	print("reflect x", self.board_string(self.walls_symmetry_boards[2])) 
	return True

def find_bridges(self: BuilderBot, ct:Controller, reached_target: bool):
	if reached_target:
		attack_mask = self.core_attack_range_symmetry_masks[self.map_symmetry-1]
		in_range_bridges = self.enemy_conveyor_board&attack_mask
		while (in_range_bridges):
			in_range_bridges, pos = self.pop_lsb(in_range_bridges)
			if not ct.is_in_vision(pos):
				continue
			b_id = ct.get_tile_building_id(pos)
			if ct.get_stored_resource(b_id) == ResourceType.TITANIUM:
				check_pos = pos.add(ct.get_direction(b_id))
				if self.is_valid_position(check_pos) and self.check_bit(self.walkable_board, check_pos):
					self.add_task(BuilderTask.PLACE_SENTINEL, pos, False)
					self.task_complete(ct)
					return True


phases = [set_target, find_bridges]
do_once = False