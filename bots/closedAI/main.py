from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants
from closedAI.BuilderBot import BuilderBot
from closedAI.Bot import Bot
from closedAI.Core import Core
from closedAI.BuilderBot import BuilderBot
from closedAI.Sentinel import SentinelBot
from closedAI.Gunner import GunnerBot

class Player:
	def __init__(self):
		self.first_turn = True
		self.bot: Bot

	def run(self, ct: Controller) -> None:
		if self.first_turn:
			etype = ct.get_entity_type()
			if etype == EntityType.CORE:
				self.bot = Core(ct)
			elif etype == EntityType.BUILDER_BOT:
				core_pos: Position
				move_dir = Direction.NORTH
				# Find the core to determine starting coordinates and initial movement direction
				for uID in ct.get_nearby_units():
					if ct.get_entity_type(uID) == EntityType.CORE:
						core_pos = ct.get_position(uID)
						move_dir = ct.get_position().direction_to(core_pos).opposite()
						break
				self.bot = BuilderBot(ct, core_pos, move_dir)
			elif etype == EntityType.SENTINEL:
				self.bot = SentinelBot(ct)
			elif etype==EntityType.GUNNER:
				print("hello")
				self.bot = GunnerBot(ct)
			
			self.first_turn = False
        
		self.bot.turn_start(ct)
		self.bot.turn_end(ct)




