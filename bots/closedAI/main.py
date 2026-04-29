from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants
from closedAI.Launcher import LauncherBot
from closedAI.Bot import Bot
from closedAI.BuilderBot import BuilderBot
from closedAI.DefenderBot import DefenderBot
from closedAI.ExplorerBot import ExplorerBot
from closedAI.Core import Core
from closedAI.Sentinel import SentinelBot
from closedAI.Gunner import GunnerBot

class Player:
	def __init__(self):
		self.first_turn = True
		self.bot: Bot

	def run(self, ct: Controller) -> None:
		if self.first_turn:
			self.first_turn = False
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
						if core_pos==ct.get_position():
							self.bot = DefenderBot(ct, core_pos, move_dir)
							return
						move_dir = ct.get_position().direction_to(core_pos).opposite()
						break
				self.bot = ExplorerBot(ct, core_pos, move_dir)
			elif etype == EntityType.SENTINEL:
				self.bot = SentinelBot(ct)
			elif etype == EntityType.GUNNER:
				self.bot = GunnerBot(ct)
			elif etype == EntityType.LAUNCHER:
				self.bot = LauncherBot(ct)
			
			
        
		self.bot.turn_start(ct)
		self.bot.turn_end(ct)