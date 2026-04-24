from cambc import Controller, Direction, Position
from .BuilderBot import BuilderBot

class DefenderBot(BuilderBot):
	def __init__(self, ct: Controller, core_pos: Position, move_dir: Direction):
		super().__init__(ct, core_pos, move_dir)