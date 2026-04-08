# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot
from ..MapSymmetry import MapSymmetry
from ..Tasktypes import BuilderTask
from cambc import Controller, Position, GameConstants

task_type = BuilderTask.FIND_ENEMY_CORE # some BuilderTask

def set_target(self: BuilderBot, ct:Controller, reached_target: bool):

	# Check if the enemy core is within visible range first
	enemy_core_pos = self.find_enemy_core(ct)
	if enemy_core_pos:
		self.enemy_core_pos = enemy_core_pos
		# If it witnin visible range, set it as the target and switch to attack task
		self.change_target(self.enemy_core_pos, 9)
		self.add_task(BuilderTask.ATTACK_ENEMY_CORE, self.core_pos)
		self.task_complete(ct)
		return True
	else:
		# No enemy core in sight - move to one of the possible symmetry positions for the enemy core to try to find it
		# This is based on the fact that the map will always be symmetric with respect to the center either by either rotation or reflection, so the enemy core must be in one of the 3 positions that are symmetric to our core position.
		
		if self.map_symmetry != MapSymmetry.UNKNOWN:
			self.add_task(BuilderTask.ATTACK_ENEMY_CORE, self.core_pos)
			self.task_complete(ct)
			return False
						

		# The first position is the one symmetric to our core across x and y, the second is symmetric across the y axis and the third is symmetric across the x axis. We sort these positions by distance from our current position to prioritise the closest one first.
		# Recomputed each time 😔 literally takes microseconds but I should probably move this but I am lazy.
		
		self.change_target(self.symmetry_positions[self.task['data']], GameConstants.BUILDER_BOT_VISION_RADIUS_SQ)
		self.phase+=1
		return True

def go_to_symmetry_point(self: BuilderBot, ct:Controller, reached_target: bool):
	if reached_target:	
		# Getting to point implies that the core is not there, so we can move on to the next possible core position or repeat if we have checked all of them
		if self.map_symmetry == MapSymmetry.UNKNOWN:
			if self.task['data'] < 2:
				self.task['data']+=1
				self.phase-=1
				return True
			else:
				# We have checked all possible symmetry positions and have not found the enemy core - it's not looking good. Look for ore instead.
				self.task_complete(ct)
		# We have reached one of the possible symmetry positions and the core is not there but we have ascertained the symmetry of the map, so we can deduce the position of the enemy core based on our core position and the map symmetry and switch to attack task
		else:

			self.add_task(BuilderTask.ATTACK_ENEMY_CORE, self.core_pos)
			self.task_complete(ct)
	else:
		# Still trying to reach the target to check for the core, keep processing this task but also check for symmetry as we go to potentially speed up the process
		if self.map_symmetry != MapSymmetry.UNKNOWN:
			# We have ascertained the symmetry of the map, so we can deduce the position of the enemy core based on our core position and the map symmetry and switch to attack task
			self.add_task(BuilderTask.ATTACK_ENEMY_CORE, self.enemy_core_pos)
			self.task_complete(ct)
phases = [set_target, go_to_symmetry_point]
do_once = False

