"""Starter bot - a simple example to demonstrate usage of the Controller API.

Each unit gets its own Player instance; the engine calls run() once per round.
Use Controller.get_entity_type() to branch on what kind of unit you are.

This bot:
- Core: spawns up to 3 builder bots on random adjacent tiles
- Builder bot: builds a harvester on any adjacent ore tile, then moves in a
random direction (laying a road first so the tile is passable), and places
a marker recording the current round number
"""

import random

from cambc import Controller, Direction, EntityType, Environment, Position

# non-centre directions
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

class Player:
	def __init__(self):
		self.first_turn = True
		self.bot: Bot		

	def run(self, ct: Controller) -> None:
		if self.first_turn:
			etype = ct.get_entity_type()
			if etype == EntityType.CORE:
				self.bot = Core()
			elif etype == EntityType.BUILDER_BOT:
				for uID in ct.get_nearby_units():
					if ct.get_entity_type(uID)==EntityType.CORE:
						core_pos = ct.get_position(uID)
						move_dir = ct.get_position().direction_to(core_pos).opposite()
						break
				self.bot = BuilderBot(core_pos, move_dir)
			self.first_turn=False
		
		self.bot.turn_start(ct)
		self.bot.turn_end(ct)

		

class Bot:
	def turn_start(self,ct):
		pass

	def turn_end(self, ct):
		pass


class BuilderBot(Bot):
	def __init__(self, core_pos, move_dir):
		self.core_pos = core_pos
		self.move_dir = move_dir
		self.ores = []
		self.target = None
		self.conveying = False
		self.returning = False
		self.map = []

	def turn_start(self, ct):
		for tile_pos in ct.get_nearby_tiles():
			if ct.get_tile_env(tile_pos) == Environment.ORE_TITANIUM:
				if not self.ores[tile_pos]:
					self.ores[tile_pos]

		if self.ores and not self.target:
			self.target = self.ores.pop()
		
		move_dir = self.move_dir
		if self.target:
			if ct.get_position().distance_squared(self.target) <=1:
				self.conveying = True
				if ct.can_build_harvester(self.target):
					ct.build_harvester(self.target)
			
			if self.ores:
				self.target = self.ores.pop()
				move_dir=ct.get_position().direction_to(self.target)
			else:
				if self.returning == False:
					self.returning = True
					self.target = self.core_pos
				else:
					self.returning = False
					self.target = None


		move_pos = ct.get_position().add(move_dir)
		for i in range(8):
			if self.conveying:
				building_id = ct.get_tile_building_id(move_pos)
				if building_id  and ct.get_entity_type(building_id) == EntityType.ROAD and ct.get_team() == ct.get_team(building_id):
					ct.destroy(move_pos)
				if ct.can_build_conveyor(move_pos, move_dir.opposite()):
					ct.build_conveyor(move_pos, move_dir.opposite())
					if ct.can_move(move_dir):
						ct.move(move_dir)
					break
			else:
				if ct.can_build_road(move_pos):
					ct.build_road(move_pos)
					if ct.can_move(move_dir):
						ct.move(move_dir)
					break
			move_dir = move_dir.rotate_left()
			move_pos = ct.get_position().add(move_dir)
						
class Core(Bot):
	def __init__(self):
		self.num_spawned = 0
		self.spawn_d = Direction.NORTH

	def turn_start(self, ct: Controller):
		if self.num_spawned < 4:
			spawn_pos = ct.get_position().add(self.spawn_d)
			self.spawn_d=self.spawn_d.rotate_left().rotate_left()
			if ct.can_spawn(spawn_pos):
				ct.spawn_builder(spawn_pos)
				self.num_spawned += 1


