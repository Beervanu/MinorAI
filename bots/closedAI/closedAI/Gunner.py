from .Turret import Turret
from cambc import Controller, EntityType, Direction,Position
class GunnerBot(Turret):
	def __init__(self, ct: Controller):
		super().__init__(ct, EntityType.GUNNER)

	def turn_start(self, ct:Controller):
		attack_pos = ct.get_gunner_target()
		if attack_pos is None:
			return
		b_id = ct.get_tile_building_id(attack_pos)
		if b_id and ct.get_team(b_id) != self.team:
			self.attack(ct, attack_pos)
			print('Tried to attack, ', attack_pos)
		bb_id = ct.get_tile_builder_bot_id(attack_pos)
		if bb_id and ct.get_team(bb_id)!=self.team:
			self.attack(ct, attack_pos)

