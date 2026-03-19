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

def dir_is_cardinal(dir:Direction):
	return {
		Direction.EAST:True,
		Direction.WEST:True,
		Direction.NORTH: True,
		Direction.SOUTH: True,
		Direction.NORTHEAST:False,
		Direction.SOUTHEAST: False,
		Direction.NORTHWEST: False,
		Direction.SOUTHWEST: False,
		}[dir]

def pos_length(pos:Position):
	return pow(pos.x**2 + pos.y**2, 0.5)

def pos_eq(a, b):
		return a.x==b.x and a.y==b.y
def pos_from(a: Position, b: Position):
		return Position(b.x-a.x, b.y-a.y)

def pos_add(a, b):
	return Position(b.x+a.x, b.y+a.y)

def pos_normalize(pos: Position, radius):
	length = pos_length(pos)
	if length == 0:
		return pos
	return Position(round(radius*pos.x/length), round(radius*pos.y/length))	

def pos_y_direction(dir:Position):
	if dir.y>=0:
		return Direction.SOUTH
	return Direction.NORTH

def pos_x_direction(dir:Position):
	if dir.x>=0:
		return Direction.EAST
	return Direction.WEST

def closest_diagonal(direction):
	if direction.x>=0:
		if direction.y>=0:
			return Direction.SOUTHEAST
		return Direction.NORTHEAST
	if direction.y>=0:
		return Direction.SOUTHWEST
	return Direction.NORTHWEST

def dir_from_pos(pos):
	if pos.x==0:
		if pos.y==1:
			return Direction.SOUTH
		return Direction.NORTH
	if pos.y ==0:
		if pos.x==1:
			return Direction.EAST
		return Direction.WEST
	if pos.x ==1:
		if pos.y==1:
			return Direction.SOUTHEAST
		return Direction.NORTHEAST
	if pos.y==1:
		return Direction.SOUTHWEST
	return Direction.NORTHWEST


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

	def set(self, pos: Position):
		self.map |= 1<< (pos.y * self.width + pos.x)
	
	def clear(self, pos: Position):
		self.map &= ~(1<<(pos.y * self.width + pos.x))
	
	def get(self, pos: Position):
		index = pos.y * self.width + pos.x
		return (self.map >> index) &1

# class Obstruction:
# 	def __init__(self, pos):
# 		self.points = []
# 		self.bottom_right =pos
# 		self.top_right = pos
# 		self.top_left = pos
# 		self.bottom_left = pos
	
# 	def add(self, pos:Position):
		# self.points.append(pos)

class BuilderBot(Bot):
	def __init__(self, ct: Controller, core_pos: Position, move_dir: Direction):
		self.core_pos = core_pos
		self.move_dir = move_dir
		# 0 for passable, 1 for not
		self.map_width = ct.get_map_width()
		self.map_height = ct.get_map_height()
		self.obstruction_map = Bitboard(self.map_width, self.map_height)
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
		self.targets = [ct.get_position().add(move_dir)]
		self.path = [move_dir]

	def turn_start(self, ct: Controller):
		self.draw_path(ct, self.path[0:10],0,0,0)
		self.draw_targets(ct)
		move_dir = self.path.pop(0)
		check_pos = ct.get_position().add(move_dir)
		if ct.can_build_road(check_pos):
			ct.build_road(check_pos)
		if ct.can_move(move_dir):
			ct.move(move_dir)
			if self.targets and pos_eq(check_pos, self.targets[0]):
				self.targets.pop(0)

	def draw_targets(self, ct:Controller):
		for pos in self.targets:
			ct.draw_indicator_dot(pos, 255,0,0)
		ct.draw_indicator_dot(self.long_target, 0,255,0)

	def draw_path(self, ct:Controller, path, r,g,b):
		current_pos = ct.get_position()
		for dir in path:
			next_pos = current_pos.add(dir)
			ct.draw_indicator_line(current_pos, next_pos,r,g,b)
			current_pos = next_pos

	#returns (path, destination)
	#where path: Direction[] and destination: Position
	#is the furthest we can get in the direction of end goal in the naive approach
	def straight_path_to_target(self,start, end):
		path_dir = pos_from(start ,end)
		steps = max(abs(path_dir.x), abs(path_dir.y))
		num_diag = min(abs(path_dir.x), abs(path_dir.y))
		num_non_diag = steps - num_diag
		print(f"straight path ({start.x} {start.y}) ({end.x}, {end.y}) ", num_diag, num_non_diag)
		y_dir = pos_y_direction(path_dir)
		x_dir = pos_x_direction(path_dir)
		non_diag_direction =x_dir if abs(path_dir.x) > abs(path_dir.y) else y_dir
		diag_direction = closest_diagonal(Position(0,0).add(x_dir).add(y_dir))
		path = []
		current_pos = start
		for i in range(steps):
			# try and go diagonal first
			if num_diag:
				num_diag-=1
				check_pos = current_pos.add(diag_direction)
				if not self.obstruction_map.get(check_pos):
					path.append(diag_direction)
					current_pos = check_pos
					continue
			
			#go in the non-diagonal direction
			if not num_non_diag:
				return (path, current_pos)
			check_pos = current_pos.add(non_diag_direction)
			if not self.obstruction_map.get(check_pos):
				path.append(non_diag_direction)
				current_pos = check_pos
				num_non_diag -= 1
			else:
				return (path, current_pos)
		return (path, current_pos)

	def path_find(self, ct:Controller):
		if self.targets:
			start = self.targets[-1]
		else:
			start = ct.get_position()
		end = self.long_target
		ct.draw_indicator_dot(end, 255,255,255)

		[path, destination_reached] = self.straight_path_to_target(start, end)
		self.path += path
		#follow the obstacle around in clockwise manner until we are closer than before
		while not(pos_eq(destination_reached, end)):
			self.targets.append(destination_reached)
			ct.draw_indicator_dot(destination_reached, 0,0,255)
			check_dir = destination_reached.direction_to(end)
			current_pos = destination_reached
			closest_distance = pos_length(pos_from(destination_reached, end))
			while True:
				check_dir = check_dir.rotate_left()
				if dir_is_cardinal(check_dir):
					check_dir = check_dir.rotate_left()
				while self.obstruction_map.get(current_pos.add(check_dir)):
					check_dir = check_dir.rotate_right()
				self.path.append(check_dir)
				
				next_pos = current_pos.add(check_dir)
				current_pos = next_pos
				dist = pos_length(pos_from(current_pos, end))
				print(f'({current_pos.x} {current_pos.y})', round(dist, 4), round(closest_distance,4))
				if dist< closest_distance:
					break

			self.targets.append(current_pos)
			[n_path, destination_reached] = self.straight_path_to_target(current_pos, end)
			self.path += n_path

	def turn_end(self,ct: Controller):
		# change to only update edges based on which direction we last moved
		self.scan_surroundings(ct)
		self.path_find(ct)
	
	def scan_surroundings(self, ct):
		for tile_pos in ct.get_nearby_tiles():
			if self.seen_map.get(tile_pos):
				continue
			self.seen_map.set(tile_pos)
			match ct.get_tile_env(tile_pos):
				case Environment.WALL:
					self.obstruction_map.set(tile_pos)
				case Environment.ORE_TITANIUM:
					self.ore_ti_map.set(tile_pos)
				case Environment.ORE_AXIONITE:
					self.ore_ti_map.set(tile_pos)


						
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


