from .Bot import Bot
from cambc import Controller, EntityType, Direction,Position
class SentinelBot(Bot):
	def __init__(self, ct: Controller):
		super().__init__(ct, EntityType.SENTINEL)
		self.attack_mask = 0
		self.facing = ct.get_direction()
		self.position = ct.get_position()
		check_pos = self.position.add(self.facing)
		while (check_pos.distance_squared(self.position)<=ct.get_vision_radius_sq()):
			for d in Direction:
				check_pos2 = check_pos.add(d)
				if self.is_valid_position(check_pos2) and check_pos2.distance_squared(self.position)<=ct.get_vision_radius_sq():
					self.attack_mask = self.set_bit(self.attack_mask, check_pos2)
			check_pos = check_pos.add(self.facing)
		self.attack_mask = self.clear_bit(self.attack_mask, self.position)
		self.team = ct.get_team()
		self.core_at = None
		for pos in ct.get_nearby_tiles():
			ent = ct.get_tile_building_id(pos)
			if ent:
				etype = ct.get_entity_type(ent)
				if etype == EntityType.CORE and ct.get_team(ent) != self.team:
					core_pos = ct.get_position(ent)
					if self.check_bit(self.attack_mask, core_pos):
						self.core_at = core_pos
						break

	def turn_start(self, ct:Controller):
		super().turn_start(ct)
		if self.core_at:
			self.attack(ct, self.core_at)
		else:
			for ent in ct.get_nearby_entities():
				pos = ct.get_position(ent)
				if ct.get_team(ent) != self.team and self.check_bit(self.attack_mask, pos) and ct.get_entity_type(ent) !=EntityType.HARVESTER:
					if self.attack(ct, pos):
						break
	
	def attack(self, ct:Controller, pos:Position):
		"""Tries to attack the position"""
		if ct.can_fire(pos):
			ct.fire(pos)
			return True
		return False
