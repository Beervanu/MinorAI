# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask
from cambc import Controller

task_type = BuilderTask.ATTACK_ENEMY_CORE # some BuilderTask

def first_phase(self: BuilderBot, ct:Controller, reached_target: bool):
	# TODO: go attack their bridges
	pass
phases = [first_phase]
do_once = False