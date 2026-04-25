from .Bot import Bot
from cambc import Controller, EntityType,Position
class Turret(Bot):
	def __init__(self, ct: Controller, entity_type:EntityType):
		super().__init__(ct, entity_type)
		self.attack_mask = 0
		self.position = ct.get_position()
		self.recalculate_attack_mask(ct)
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
	
	def recalculate_attack_mask(self, ct:Controller):
		self.attack_mask = 0
		for pos in ct.get_attackable_tiles():
			self.attack_mask = self.set_bit(self.attack_mask, pos)
	
	def attack(self, ct:Controller, pos:Position):
		"""Tries to attack the position"""
		if ct.can_fire(pos) :
			ct.fire(pos)
			return True
		return False
			