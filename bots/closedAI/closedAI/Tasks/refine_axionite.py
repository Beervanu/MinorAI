# bunch of stuff to avoid circular imports but keep static typing
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from ..BuilderBot import BuilderBot
from ..Constants import CARDINAL_DIRECTIONS, DIRECTIONS
from ..Tasktypes import BuilderTask, TaskData
from cambc import Controller, Position, Direction
from ..helper_functions import eprint
task_type = BuilderTask.REFINE_AXIONITE # some BuilderTask

def choose_foundry_pos(self: BuilderBot, ct:Controller, reached_target: bool):
	
	ax_pos = self.task['data']['ax_in']
	downstream_ax = []
	ti_connected = False
	for id in self.conveyor_ids[ax_pos]:

		for i in range(len(self.conveyor_lines[id]['positions'])):
			if ax_pos == self.conveyor_lines[id]['positions'][i]:
				downstream_ax = self.conveyor_lines[id]['positions'][i:]
				
				break
		ti_connected = len(self.conveyor_lines[id]['ti_harvesters'])>0
		break
	
	for splitter_pos in reversed(downstream_ax):
		fed_by_set = self.conveyors_pointing_into[splitter_pos].intersection(downstream_ax)
		fed_by:Position
		if fed_by_set:
			fed_by = fed_by_set.pop()
		else:
			for id in self.conveyor_ids[splitter_pos]:
				for harv in self.conveyor_lines[id]['ax_harvesters']:
					if harv.distance_squared(splitter_pos)==1:
						fed_by = harv
						break
				break
		
		if not fed_by:
			continue

		free_dirs:list[Position] = []
		for d in CARDINAL_DIRECTIONS:
			check_pos = splitter_pos.add(d)
			if fed_by == check_pos:
				continue
			if self.check_bit(self.walkable_board, check_pos):
				free_dirs.append(check_pos)
		# splitter needs 2 output directions
		if len(free_dirs)<2:
			continue
		
		for foundry_pos in free_dirs:
			for d in CARDINAL_DIRECTIONS:
				
				foundry_out = foundry_pos.add(d)
				if foundry_out == splitter_pos:
					continue
				if self.check_bit(self.walkable_board, foundry_out):
					#connect ti line to splitter
					if not ti_connected:
						bitb = 0
						for i in self.conveyor_lines:
							if self.conveyor_lines[i]['ti_harvesters']:
								bitb|= self.conveyor_lines[i]['bitboard']
						if not bitb:
							continue
						
						
						self.add_task(ct, BuilderTask.BUILD_BRIDGE, {
							'start':self.closest_in_board(bitb, splitter_pos),
							'to_feed': splitter_pos
						})

					self.task['data']['splitter_pos'] = splitter_pos
					self.task['data']['foundry_pos'] = foundry_pos
					#connect foundry to core
					if not self.check_bit(self.core_mask, foundry_out):
						self.add_task(ct, BuilderTask.BUILD_BRIDGE, {'start':foundry_out, 'to_feed':None})
					destroyed_conveyor_points_to =self.conveyor_pointing_to[splitter_pos]
					# connect splitter to core 
					if destroyed_conveyor_points_to== foundry_pos or destroyed_conveyor_points_to.distance_squared(splitter_pos) > 1: # type: ignore
						for i in free_dirs:
							if i ==foundry_pos:
								continue
							splitter_out = i
							break
						self.add_task(ct, BuilderTask.BUILD_BRIDGE, {'start':splitter_out, 'to_feed':None})
					
					
						

					#figure out which direction to point the splitter
					if fed_by.distance_squared(splitter_pos)==1:
						self.task['data']['splitter_output'] = splitter_pos.add(fed_by.direction_to(splitter_pos))
					else:
						splitter_out_dir = splitter_pos.direction_to(splitter_out)
						foundry_dir = splitter_pos.direction_to(foundry_pos)
						if foundry_dir== splitter_out_dir.opposite():
							self.task['data']['splitter_output'] = splitter_pos.add(foundry_dir.rotate_left())
						else:
							self.task['data']['splitter_output'] = foundry_pos
					self.phase+=1
					# go to the splitter position
					self.change_target(splitter_pos)
					return True
			
def build_splitter(self: BuilderBot, ct:Controller, reached_target: bool):
	if ct.is_in_vision(self.target):
		if not self.check_bit(self.walkable_board, self.target):
			self.phase-=1
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
					return False
			splitter_dir = self.target.direction_to(self.task['data']['splitter_output'])
			if ct.can_build_splitter(self.target, splitter_dir):
				ct.build_splitter(self.target, splitter_dir)
				self.phase+=1
				self.change_target(self.task['data']['foundry_pos'])
				return True
		return False

def build_foundry(self: BuilderBot, ct:Controller, reached_target: bool):
	if ct.is_in_vision(self.target):
		if not self.check_bit(self.walkable_board, self.target):
			self.phase-=1
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
					return False
			if ct.can_build_foundry(self.target):
				ct.build_foundry(self.target)
				self.task_complete(ct)
				return True
		return False				

#is called before we switch to this task, and can be used to cull the task if it ever becomes invalid
def is_valid(self: BuilderBot,ct:Controller, task:TaskData)->bool:
	return True

phases = [choose_foundry_pos, build_splitter, build_foundry]
do_once = True