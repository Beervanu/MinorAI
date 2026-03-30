# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask
from cambc import Controller, Direction
from .. Constants import DIRECTIONS, CARDINAL_DIRECTIONS

task_type = BuilderTask.ATTACK_ENEMY_BRIDGE # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):
	self.change_target(self.task['data'], 0)
	self.phase+=1
	return True

def attack(self: BuilderBot, ct:Controller, reached_target: bool):
	if reached_target:
		if self.check_bit(self.enemy_buildings_board, self.target):
			if ct.can_fire(self.target):
				ct.fire(self.target)
		else:
			self.phase+=1
			return True

def place_sentinel(self: BuilderBot, ct:Controller, reached_target: bool):
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
		ore_dir = Direction.CENTRE
		for d in CARDINAL_DIRECTIONS:
			check_pos = self.target.add(d)
			# TODO: change to add any conveyor
			if self.is_valid_position(check_pos) and self.check_bit(self.titanium_ores_board|self.axionite_ores_board, check_pos):
				ore_dir = d
				break
		ore_dir = ore_dir.opposite()
		if ct.can_build_sentinel(self.target, ore_dir):
			ct.build_sentinel(self.target, ore_dir)
			self.task_complete(ct)
phases = [set_target, attack, place_sentinel]
do_once = True


