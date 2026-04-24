# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, Position

task_type = None # some BuilderTask

def first_phase(self: BuilderBot, ct:Controller, reached_target: bool):
	pass

#is called before we switch to this task, and can be used to cull the task if it ever becomes invalid
def is_valid(self: BuilderBot,ct:Controller, task:TaskData)->bool:
	return True

phases = [first_phase]
do_once = False