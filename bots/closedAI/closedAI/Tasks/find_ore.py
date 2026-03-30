# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
import sys, os
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot

from ..Tasktypes import BuilderTask
from cambc import Controller, Position
from random import randint
task_type = BuilderTask.FIND_ORE

def first_phase(self: BuilderBot, ct:Controller, reached_target: bool):
	current_pos = ct.get_position()
	if reached_target or self.target is None:
		# try and move in our original move direction
		x = current_pos.x + self.move_dir.delta()[0]*8
		y = current_pos.y + self.move_dir.delta()[1]*8
		# if we hit a wall /edge of the map, turn 90 deg
		if not self.is_valid_position(Position(x,y)):
			self.move_dir = self.move_dir.rotate_left().rotate_left()
		x+=randint(-4,4)
		y+=randint(-4,4)	
		x = max(0, min(x, self.map_width-1))
		y= max(0, min(y, self.map_height-1))
		self.change_target(Position(x,y), 9)
phases = [first_phase]
do_once = False