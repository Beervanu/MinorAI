from .Turret import Turret
from cambc import Controller, EntityType,Position
from .helper_functions import eprint

class SentinelBot(Turret):
	def __init__(self, ct: Controller):
		super().__init__(ct, EntityType.SENTINEL)

	def turn_start(self, ct:Controller):
		super().turn_start(ct)
		if self.core_at:
			self.attack(ct, self.core_at)
		else:
			for ent in ct.get_nearby_entities():
				pos = ct.get_position(ent)
				if ct.get_team(ent) != self.team:
					if self.check_bit(self.attack_mask, pos): 
						etype = ct.get_entity_type(ent)
						if not etype in [EntityType.HARVESTER, EntityType.MARKER]:
							builder_id = ct.get_tile_builder_bot_id(pos)
							if not builder_id or ct.get_team(builder_id) != self.team:
								if self.attack(ct, pos):
									break
	
	
