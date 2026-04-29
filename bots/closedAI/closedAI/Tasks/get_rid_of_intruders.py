# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING

from ..Constants import DIRECTIONS
from ..helper_functions import eprint
if TYPE_CHECKING:
	from ..DefenderBot import DefenderBot
from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, Direction, EntityType, Position

task_type = BuilderTask.GET_RID_OF_INTRUDERS # some BuilderTask
sent_direction = Direction.WEST

def next_unbuilt_sentinel(self: DefenderBot, ct:Controller, reached_target: bool):
	global sent_direction

	if self.sentinel_defence_positions:
		next_target, sent_direction = self.sentinel_defence_positions.pop()
		self.change_target(next_target)
		self.task['data']['alternative_pos'].clear()
		self.phase+=1
		return True
	self.task_complete(ct)
	self.checking_walls = False
	return True

	
def build_sentinel(self: DefenderBot, ct:Controller, reached_target: bool):
	if ct.is_in_vision(self.target):
		b_id = ct.get_tile_building_id(self.target)
		if b_id and ct.get_entity_type(b_id) == EntityType.SENTINEL and ct.get_team(b_id) == ct.get_team():
			self.phase-=1
			return True
		
	if reached_target:
		target_bitmask = self.get_bitmask(self.target)
		if target_bitmask & self.walls_board:
			if not self.task['data']['alternative_pos']:
				for d in DIRECTIONS:
					alt_pos = self.target.add(d)
					if self.is_valid_position(alt_pos) and self.check_bit(self.walkable_board, alt_pos):
						self.task['data']['alternative_pos'].append(alt_pos)
			if self.task['data']['alternative_pos']:
				self.change_target(self.task['data']['alternative_pos'].pop())
			else:
				# Give up on this position
				self.phase-=1
			return True
		if ct.get_action_cooldown() == 0:
			self_pos = ct.get_position()
			if self.walkable_board&target_bitmask:
				if ct.can_destroy(self.target):
					ct.destroy(self.target)
				if self.enemy_buildings_board & target_bitmask:
					if self.target!= self_pos:
						if ct.get_move_cooldown() == 0:
							move_dir = self_pos.direction_to(self.target)
							if ct.can_move(move_dir):
								ct.move(move_dir)
					if ct.can_fire(self.target):
						ct.fire(self.target)
					return False
				if self.target == self_pos:
					best_dist = float('inf')
					best_dir = Direction.CENTRE
					for d in DIRECTIONS:
						check_pos = self_pos.add(d)
						if self.is_valid_position(check_pos) and self.check_bit(self.walkable_board, check_pos):
							dist = self.chebyshev(self.core_pos, check_pos)
							if dist<best_dist:
								best_dir = d
								best_dist = dist
					b_pos = self_pos.add(best_dir)
					if ct.can_build_road(b_pos):
						ct.build_road(b_pos)

					if ct.can_move(best_dir):
						ct.move(best_dir)
					else:
						#this is bad idk
						eprint('uh oh')
						return False

				if ct.can_build_sentinel(self.target, sent_direction):
					ct.build_sentinel(self.target, sent_direction)
					self.phase-=1
					return True

#is called before we switch to this task, and can be used to cull the task if it ever becomes invalid
def is_valid(self: DefenderBot,ct:Controller, task:TaskData)->bool:
	return True

phases = [next_unbuilt_sentinel, build_sentinel]
do_once = False