# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..DefenderBot import DefenderBot

from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, Position

task_type = BuilderTask.BUILD_CORE_DEFENCE


def compute_defence_walls_board(self: DefenderBot) -> int:
	"""
	Builds a bitboard of wall positions 4 tiles out from the core centre.
	Skips tiles that are off-map or are already occupied by environmental walls.
	"""
	board = 0
	cx, cy = self.core_pos.x, self.core_pos.y
	radius = 6

	for dx in range(-radius, radius + 1):
		for dy in range(-radius, radius + 1):
			# Only keep perimeter tiles — skip interior
			if abs(dx) != radius and abs(dy) != radius:
				continue
			nx, ny = cx + dx, cy + dy
			if not (0 <= nx < self.map_width and 0 <= ny < self.map_height):
				continue
			pos = Position(nx, ny)
			if self.check_bit(self.walls_board, pos):
				continue
			board = self.set_bit(board, pos)
	return board


def compute_defence_conveyors_board(self: DefenderBot) -> int:
	"""
	Builds a bitboard of conveyor positions — four radial lanes from core
	to the inside of the wall ring. Skips tiles off-map or blocked by environmental walls.
	"""
	board = 0
	cx, cy = self.core_pos.x, self.core_pos.y
	wall_radius = 4
	core_half = 1 # core is 3x3, so occupies radius 1 from center
	lane_half_width = 1 # 2-wide lanes, so half-width is 1

	# Lane offsets along each cardinal direction.
	# Skip tiles inside the core itself (distance <= core_half) and outside the walls (distance >= wall_radius).
	for step in range(core_half + 1, wall_radius):
		# North and south lanes (varying dy, dx within lane width)
		for offset in range(-lane_half_width, lane_half_width + 1):
			for dy in (step, -step): # north and south
				nx, ny = cx + offset, cy + dy
				if 0 <= nx < self.map_width and 0 <= ny < self.map_height:
					pos = Position(nx, ny)
					if not self.check_bit(self.walls_board, pos):
						board = self.set_bit(board, pos)

			for dx in (step, -step): # east and west
				nx, ny = cx + dx, cy + offset
				if 0 <= nx < self.map_width and 0 <= ny < self.map_height:
					pos = Position(nx, ny)
					if not self.check_bit(self.walls_board, pos):
						board = self.set_bit(board, pos)
	return board


def next_unbuilt_defence_tile(self: DefenderBot, ct: Controller, template_board: int) -> Position | None:
	"""Returns the closest template tile not yet occupied by any building."""
	unbuilt = template_board & (self.walkable_board | ~self.seen_board)
	print(f"Unbuilt: {self.board_string(unbuilt)}")
	print(f"Walkable: {self.board_string(self.walkable_board)}")
	print(f"Seen: {self.board_string(self.seen_board)}")
	print(f"Template: {self.board_string(template_board)}")
	if unbuilt == 0:
		return None

	current = ct.get_position()
	best = None
	best_dist = float('inf')

	temp = unbuilt
	while temp:
		(temp, pos) = self.pop_lsb(temp)
		dist = self.chebyshev(current, pos)
		if dist < best_dist:
			best_dist = dist
			best = pos
	return best


def init_templates(self: DefenderBot, ct: Controller, reached_target: bool):
	"""Compute and cache the wall and conveyor bitboards on first run."""
	if not self.defence_walls_board:
		self.defence_walls_board = compute_defence_walls_board(self)
	if not self.defence_conveyors_board:
		self.defence_conveyors_board = compute_defence_conveyors_board(self)
	self.phase += 1
	return True


def pick_wall_target(self: DefenderBot, ct: Controller, reached_target: bool):
	"""Find the nearest unbuilt wall tile and target it."""
	target_pos = next_unbuilt_defence_tile(self, ct, self.defence_walls_board)

	if target_pos is None:
		# All walls built — advance to conveyor phase
		self.phase += 1
		return True

	self.change_target(target_pos, 2)
	self.phase += 1
	return True


def build_wall(self: DefenderBot, ct: Controller, reached_target: bool):
	if reached_target:
		if ct.get_action_cooldown() == 0: 
			if self.check_bit(self.walkable_board, self.target):
				if ct.can_destroy(self.target):
					ct.destroy(self.target)
				if self.check_bit(self.enemy_buildings_board, self.target):
					
					
			if ct.can_build_barrier(self.target):
				ct.build_barrier(self.target)
				# Loop back to pick the next wall
				self.phase -= 1
				return False
		return False


def pick_conveyor_target(self: DefenderBot, ct: Controller, reached_target: bool):
	target_pos = next_unbuilt_defence_tile(self, ct, self.defence_conveyors_board)

	if target_pos is None:
		self.task_complete(ct)
		return True

	self.change_target(target_pos, 2)
	self.phase += 1
	return True


def build_conveyor(self: DefenderBot, ct: Controller, reached_target: bool):
	if reached_target:
		if ct.get_action_cooldown() == 0:
			# Conveyors face inward toward the core
			direction = self.target.direction_to(self.core_pos)
			self.phase -= 1
			return True
		return False


def is_valid(self: DefenderBot, ct: Controller, task: TaskData) -> bool:
	return True


phases = [init_templates, pick_wall_target, build_wall, pick_conveyor_target, build_conveyor]
do_once = True