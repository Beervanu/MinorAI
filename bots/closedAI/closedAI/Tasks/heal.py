# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller
from ..helper_functions import eprint

task_type = BuilderTask.HEAL # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):
	self.change_target(self.task['data'], 2)
	self.phase+=1
	return True

def heal(self: BuilderBot, ct:Controller, reached_target: bool):
	if not is_valid(self,ct, self.task):
		self.task_complete(ct)
		return True
	pos = self.task['data']
	if reached_target:
		
		if ct.can_heal(pos):
			ct.heal(pos)
	if ct.is_in_vision(pos):
		b_id = ct.get_tile_building_id(pos)
		if b_id and ct.get_hp(b_id) > ct.get_max_hp(b_id)-4:
			self.task_complete(ct)
			return True


		

def is_valid(self: BuilderBot,ct:Controller, task:TaskData)->bool:
	# is there a team building on that spot
	return self.check_bit(self.team_buildings_board, task['data'])

phases = [set_target, heal]
do_once = True