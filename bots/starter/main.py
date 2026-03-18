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
			match ct.get_entity_type():
				case EntityType.CORE:
					self.bot = Core()
				case EntityType.BUILDER_BOT:
					for uID in ct.get_nearby_units():
						if ct.get_entity_type(uID)==EntityType.CORE:
							core_pos = ct.get_position(uID)
							move_dir = ct.get_position().direction_to(core_pos).opposite()
							break
					self.bot = BuilderBot(ct, core_pos, move_dir)
			self.first_turn=False
		
		self.bot.turn_start(ct)
		self.bot.turn_end(ct)

def pos_eq(a, b):
		return a.x==b.x and a.y==b.y
def pos_from(a: Position, b: Position):
		return Position(b.x-a.x, b.y-a.y)

def pos_add(a, b):
	return Position(b.x+a.x, b.y+a.y)

def pos_normalize(pos: Position, radius):
	length = pow(pos.x**2 + pos.y**2, 0.5)
	if length == 0:
		return pos
	return Position(round(radius*pos.x/length), round(radius*pos.y/length))	

class Bot:
	def turn_start(self,ct):
		pass

	def turn_end(self, ct):
		pass

class Bitboard:
	def __init__(self, width, height):
		self.height = height
		self.width = width
		self.map = 0

	def set(self, pos: Position, value):
		index = pos.y * self.width + pos.x
		mask = 1<< index
		if value:
			self.map |= mask
		else:
			self.map &= ~mask
	
	def get(self, pos: Position):
		index = pos.y * self.width + pos.x
		return (self.map >> index) &1



class BuilderBot(Bot):
	def __init__(self, ct: Controller, core_pos: Position, move_dir: Direction):
		self.core_pos = core_pos
		self.move_dir = move_dir
		# 0 for passable, 1 for not
		self.map_width = ct.get_map_width()
		self.map_height = ct.get_map_height()
		self.passable_map = Bitboard(self.map_width, self.map_height)
		self.seen_map = Bitboard(self.map_width, self.map_height)
		self.ore_ti_map = Bitboard(self.map_width, self.map_height)
		self.ores = []
		self.ore_ax_map = Bitboard(self.map_width, self.map_height)
		self.scan_surroundings(ct)

		self.long_target = core_pos
		match self.move_dir:
			case Direction.NORTH:
				self.long_target = Position(core_pos.x, 0)
			case Direction.SOUTH:
				self.long_target = Position(core_pos.x, self.map_height)
			case Direction.WEST:
				self.long_target = Position(0, core_pos.y)
			case Direction.EAST:
				self.long_target = Position(self.map_width, core_pos.y)
		path_dir = pos_normalize(pos_from(core_pos, self.long_target), 20**0.5)
		self.target = pos_add(core_pos, path_dir)
		for i in range(4):
			self.target = self.target.add(move_dir)
		#self.heuristic_map = [[0 for i in range(self.map_width)] for i in range(self.map_height)]
		#self.path = []

	def turn_start(self, ct: Controller):
		move_dir = self.fastest_path_dir(ct)
		check_pos = ct.get_position().add(move_dir)
		if ct.can_build_road(check_pos):
			ct.build_road(check_pos)
		if ct.can_move(move_dir):
			ct.move(move_dir)

	def turn_end(self,ct: Controller):
		# change to only update edges based on which direction we last moved
		self.scan_surroundings(ct)

	def fastest_path_dir(self, ct: Controller):
		path_dir = pos_normalize(pos_from(ct.get_position(), self.long_target), 20**0.5)
		self.target = pos_add(ct.get_position(), path_dir)
		path = [ct.get_position()]
		check_dir = path[-1].direction_to(self.target)
		check_pos = path[-1].add(check_dir)
		while not pos_eq(check_pos, self.target):
			if not self.passable_map.get(check_pos):
				return check_dir
				path.append(check_pos)
				check_dir = path[-1].direction_to(self.target)
			else:
				check_dir = check_dir.rotate_left()
			check_pos = path[-1].add(check_dir)
		return Direction.NORTH
	
	def scan_surroundings(self, ct):
		for tile_pos in ct.get_nearby_tiles():
			self.seen_map.set(tile_pos,True)
			match ct.get_tile_env(tile_pos):
				case Environment.WALL:
					self.passable_map.set(tile_pos, True)
				case Environment.ORE_TITANIUM:
					self.ore_ti_map.set(tile_pos, True)
				case Environment.ORE_AXIONITE:
					self.ore_ti_map.set(tile_pos, True)


						
class Core(Bot):
	def __init__(self):
		self.num_spawned = 0
		self.spawn_d = Direction.NORTH

	def turn_start(self, ct: Controller):
		core_pos = ct.get_position()
		if self.num_spawned < 4:
			spawn_pos = ct.get_position().add(self.spawn_d)
			#if ct.get_map_width()-core_pos.x<:

			self.spawn_d=self.spawn_d.rotate_left().rotate_left()

			if ct.can_spawn(spawn_pos):
				ct.spawn_builder(spawn_pos)
				self.num_spawned += 1


