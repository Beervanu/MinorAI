from .Bot import Bot
from cambc import Controller, Direction, EntityType, Position
class Core(Bot):
	def __init__(self, ct: Controller):
		super().__init__(ct, EntityType.CORE)
		self.num_spawned = 0
		self.spawn_d = Direction.NORTH

	def turn_start(self, ct: Controller):
		super().turn_start(ct)
		round = ct.get_current_round()

		if self.num_spawned < 2 or (self.num_spawned<4 and round>15):

			spawn_pos = ct.get_position().add(self.spawn_d)
			# Rotate 90 degrees for the next spawn so that bots fan out
			self.spawn_d=self.spawn_d.rotate_left().rotate_left()
			if not self.num_spawned%2:
				self.spawn_d=self.spawn_d.rotate_left().rotate_left()
			if ct.can_spawn(spawn_pos):
				ct.spawn_builder(spawn_pos)
				self.num_spawned += 1
		
		if  round>= 50 and self.num_spawned<6:
			# Spawn a bot with the find bot task to start scouting for ore and the enemy core
			spawn_pos = ct.get_position().add(self.spawn_d) 
			if ct.can_spawn(spawn_pos):
				ct.spawn_builder(spawn_pos)
				self.num_spawned += 1
		
		for ent in ct.get_nearby_entities():
			if ct.get_entity_type(ent) == EntityType.MARKER and ct.get_team() == ct.get_team(ent):
				# Compare my internal marker data with the existing marker
				self.read_marker(ct, ent) 

		for x in range(-2, 3):
			for y in range(-2, 3):
				new_pos = Position(ct.get_position().x + x, ct.get_position().y + y)
				if ct.can_place_marker(new_pos):
					ct.place_marker(new_pos, self.central_marker_data.as_int)

