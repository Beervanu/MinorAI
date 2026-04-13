from .Bot import Bot
from cambc import Controller, Direction, EntityType, Position
from .Constants import CONVEYOR_ENTITIES
class Core(Bot):
	def __init__(self, ct: Controller):
		super().__init__(ct, EntityType.CORE)
		self.num_spawned = 0
		self.spawn_d = Direction.NORTH
		self.spawned_defense = 0
		self.spawn_defense = False

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
			spawn_pos = ct.get_position().add(self.spawn_d) 
			if ct.can_spawn(spawn_pos):
				ct.spawn_builder(spawn_pos)
				self.num_spawned += 1
		for ent in ct.get_nearby_entities():
			etype = ct.get_entity_type(ent)
			if  etype == EntityType.MARKER and ct.get_team() == ct.get_team(ent):
				# Compare my internal marker data with the existing marker
				self.read_marker(ct, ent)
			if self.spawned_defense <2:
				if ct.get_team() == ct.get_team(ent):
					if ct.get_hp(ent)!= ct.get_max_hp(ent):
						#emergency defense
						self.spawn_defense = True
						
		if self.spawn_defense:
			if ct.can_spawn(ct.get_position().add(self.spawn_d)) and ct.get_global_resources()[0]-ct.get_builder_bot_cost()[0]>ct.get_gunner_cost()[0]*1.5:
				ct.spawn_builder(ct.get_position().add(self.spawn_d))
				self.spawned_defense +=1

		for x in range(-2, 3):
			for y in range(-2, 3):
				new_pos = Position(ct.get_position().x + x, ct.get_position().y + y)
				if ct.can_place_marker(new_pos):
					ct.place_marker(new_pos, self.central_marker_data.as_int)

