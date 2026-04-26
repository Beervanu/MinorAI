# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, Position

task_type = BuilderTask.CUTOFF_ENEMY_LINES # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):
	self.change_target(self.task['data'])
	self.phase+=1
	pass

def attack(self: BuilderBot, ct:Controller, reached_target: bool):
	if not is_valid(self,ct, self.task):
		self.task_complete(ct)
		return True
	if reached_target:
		b_id = ct.get_tile_building_id(self.task['data'])
		if b_id:
			if ct.get_team(b_id) == self.team:
				if ct.can_destroy(self.task['data']):
					ct.destroy(self.task['data'])

					self.task_complete(ct)
					return True
			else:
				self.change_target(self.task['data'], 0)
				if ct.can_fire(self.task['data']):
					ct.fire(self.task['data'])
					return False
		else:
			self.task_complete(ct)
			return True




#is called before we switch to this task, and can be used to cull the task if it ever becomes invalid
def is_valid(self: BuilderBot,ct:Controller, task:TaskData)->bool:
	if ids:=self.conveyor_ids[task['data']]:
		for id in ids:
			if self.conveyor_lines[id]['feeds_team'] is None:
				return False
			return self.conveyor_lines[id]['feeds_team'] != self.team
	return False

	

phases = [set_target, attack]
do_once = True