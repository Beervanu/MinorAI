# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..DefenderBot import DefenderBot

from ..Tasktypes import BuilderTask, TaskData
from ..Markers import LauncherMarkerData
from cambc import Controller, Position, Direction, EntityType
from ..Constants import DIRECTIONS, CARDINAL_DIRECTIONS
from ..helper_functions import eprint

task_type = BuilderTask.BUILD_CORE_DEFENCE

def next_unbuilt_defence_tile(self: DefenderBot, ct: Controller, template_board: int) -> Position | None:
	"""Returns the closest template tile not yet occupied by any building."""
	unbuilt = template_board & (self.walkable_board | ~self.seen_board) & self.connected_region
	if unbuilt == 0:
		return None

	current = ct.get_position()
	best = None
	best_dist = float('inf')

	temp = unbuilt
	while temp:
		(temp, pos) = self.pop_lsb(temp)
		dist = abs(current.x-pos.x)+abs(current.y-pos.y)
		if dist < best_dist:
			best_dist = dist
			best = pos
	return best

def pick_wall_target(self: DefenderBot, ct: Controller, reached_target: bool):
	"""Find the nearest unbuilt wall tile and target it."""
	target_pos = next_unbuilt_defence_tile(self, ct, self.defence_walls_board)

	if target_pos is None:
		#if we are blocked by a unit
		if self.defence_walls_board & self.units_board:
			return False
		# All walls built and launchers handled - task complete
		self.task_complete(ct)
		return True

	self.change_target(target_pos, 2)
	self.phase = phases.index(build_wall) # type: ignore
	return True


def build_wall(self: DefenderBot, ct: Controller, reached_target: bool):
	if not reached_target:
		target_pos = next_unbuilt_defence_tile(self, ct, self.defence_walls_board)
		if target_pos is None:
			if self.defence_walls_board & self.units_board:
				return False
			# All walls built and launchers handled - task complete
			self.task_complete(ct)
			return True
		curr_pos = ct.get_position()
		new_target_dist = curr_pos.distance_squared(target_pos)
		if new_target_dist<curr_pos.distance_squared(self.target):
			reached_target = new_target_dist<=2
			self.change_target(target_pos, 2)
	 
	if ct.is_in_vision(self.target):
		if not self.check_bit(self.walkable_board, self.target):
			self.phase = phases.index(pick_wall_target)
			return True
	
	# skip if this position is reserved for the launcher pocket
	if self.check_bit(self.launcher_pocket_board, self.target):
		
		# This tile must remain empty - move to next wall
		self.defence_walls_board = self.clear_bit(self.defence_walls_board, self.target)
		self.phase = phases.index(pick_wall_target)
		return True
	
	if reached_target:
		target_bitmask = self.get_bitmask(self.target)
		if ct.get_action_cooldown() == 0: 
			self_pos = ct.get_position()
			if self.walkable_board&target_bitmask:
				if ct.can_destroy(self.target):
					ct.destroy(self.target)
				#if there is a walkable enemy building
				if self.enemy_buildings_board&target_bitmask:
					# if we're not on top of the target then move on top
					if self.target!= self_pos:
						if ct.get_move_cooldown() ==0:
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

			if ct.can_build_barrier(self.target):

				# Region check: simulate placing the wall
				current_region = self.update_region(self.walkable_board, self_pos)
				simulated_walkable = self.walkable_board & ~target_bitmask
				simulated_region = self.update_region(simulated_walkable, self_pos)

				# Tiles that were reachable but now aren't - excluding the target itself
				lost_tiles = current_region & ~simulated_region & ~target_bitmask
				
				if (lost_tiles != 0 or self.task['data']['wall_counter']>=12) and not self.task['data']['build_wall_override']:
					convert_to_launcher_pocket(self, ct)
					return True	
				self.task['data']['wall_counter']+=1
				self.task['data']['build_wall_override'] = False
				ct.build_barrier(self.target)
				self.phase = phases.index(pick_wall_target)
				return False
		return False

def snap_to_cardinal(dx, dy) -> Direction:
    """Snap a diagonal direction to the nearest cardinal."""
    if abs(dx) > abs(dy):
        return Direction.EAST if dx > 0 else Direction.WEST
    else:
        return Direction.SOUTH if dy > 0 else Direction.NORTH

def convert_to_launcher_pocket(self: DefenderBot, ct: Controller):
	"""
	Marks a laucher pocket and queues the launcher build at this position.
	"""
	# Direction from the gap toward the core (snapped to cardinal so the bots can still get back even if the gap is diagonal (corner))
	inward = snap_to_cardinal(self.core_pos.x-self.target.x, self.core_pos.y-self.target.y)
	launcher_pos = self.target.add(inward)
	self.defence_walls_board = self.clear_bit(self.defence_walls_board, self.target)
	if not self.check_bit(self.walkable_board, launcher_pos):
		launcher_pos = self.target.add(inward.opposite())
		if not self.check_bit(self.walkable_board, launcher_pos):
			self.task['data']['build_wall_override']=True
			return False
			
	# Reserve the gap, the launcher tile, and the two flanking tiles
	new_launcher_board = self.launcher_pocket_board
	flank_free = False
	# Flanks are perpendicular to the inward axis (90 degree rotations)
	for flank_dir in (inward.rotate_left().rotate_left(), inward.rotate_right().rotate_right()):
		flank_pos = launcher_pos.add(flank_dir)
		if self.is_valid_position(flank_pos) and self.check_bit(self.walkable_board, flank_pos):
			flank_free = True
			new_launcher_board = self.set_bit(new_launcher_board, flank_pos)
			self.defence_walls_board = self.clear_bit(self.defence_walls_board, flank_pos)
	if not flank_free:
		#retry with a different launcher position
		if launcher_pos == self.target.add(inward.opposite()):
			self.task['data']['build_wall_override']=True
			return False
		launcher_pos = self.target.add(inward.opposite())
		for flank_dir in (inward.rotate_left().rotate_left(), inward.rotate_right().rotate_right()):
			flank_pos = launcher_pos.add(flank_dir)
			if self.is_valid_position(flank_pos) and self.check_bit(self.walkable_board, flank_pos):
				flank_free = True
				new_launcher_board = self.set_bit(new_launcher_board, flank_pos)
				self.defence_walls_board = self.clear_bit(self.defence_walls_board, flank_pos)
		#if its still not free just build a wall
		if not flank_free:
			self.task['data']['build_wall_override']=True
			return False
	new_launcher_board = self.set_bit(new_launcher_board, self.target)
	new_launcher_board = self.set_bit(new_launcher_board, launcher_pos)
	self.launcher_pocket_board = new_launcher_board


	# Queue the launcher build immediately - switch target to the launcher tile
	self.change_target(launcher_pos, 2)
	self.phase = phases.index(build_launcher) # type: ignore
	return True

def build_launcher(self: DefenderBot, ct: Controller, reached_target: bool):
	if reached_target:
		target_bitmask = self.get_bitmask(self.target)
		if ct.get_action_cooldown() == 0:
			
			self_pos = ct.get_position()
			if self.walkable_board&target_bitmask:
				if ct.can_destroy(self.target):
					ct.destroy(self.target)
				#if there is a walkable enemy building
				if self.enemy_buildings_board&target_bitmask:
					# if we're not on top of the target then move on top
					if self.target!= self_pos:
						if ct.get_move_cooldown() ==0:
							move_dir = self_pos.direction_to(self.target)
							if ct.can_move(move_dir):
								ct.move(move_dir)
					if ct.can_fire(self.target):
						ct.fire(self.target)
					return False
				
			
			if ct.get_global_resources()[0] >= ct.get_launcher_cost()[0]:
				if self_pos == self.target:
					for d in DIRECTIONS:
						check_pos = self_pos.add(d)
						if self.is_valid_position(check_pos) and self.check_bit(self.walkable_board, check_pos):

							if ct.can_move(d):
								ct.move(d)
								break


			if ct.can_build_launcher(self.target):
				self_pos = ct.get_position()
					# Move ut of the way if standing on the launcher tile
				
				for d in DIRECTIONS:
					check_pos = self_pos.add(d)
					if self.is_valid_position(check_pos) and check_pos != self.target:
						if self.check_bit(self.team_buildings_board, check_pos):
							if b_id:=ct.get_tile_building_id(check_pos):
								if ct.get_entity_type(b_id) in [EntityType.ROAD, EntityType.MARKER]:
									if ct.can_destroy(check_pos):
										ct.destroy(check_pos)

						if ct.can_place_marker(check_pos):
							write = LauncherMarkerData()
							write.date = ct.get_current_round()
							write.core_x = self.core_pos.x
							write.core_y = self.core_pos.y
							ct.place_marker(check_pos, write.as_int)
							break
				ct.build_launcher(self.target)
				self.task['data']['wall_counter'] = 0
				# Back to wall-building loop
				self.phase = phases.index(pick_wall_target)
				return True
			
	return False



def is_valid(self: DefenderBot, ct: Controller, task: TaskData) -> bool:
	return True


phases = [
    pick_wall_target, 
	build_wall,
	build_launcher,
]
do_once = True