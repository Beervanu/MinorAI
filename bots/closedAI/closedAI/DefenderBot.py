from cambc import Controller, Direction, Position
from .Tasktypes import BuilderTask
from .Markers import LauncherMarkerData
from .BuilderBot import BuilderBot

class DefenderBot(BuilderBot):
	def __init__(self, ct: Controller, core_pos: Position, move_dir: Direction):
		#must generate before calling super()
		#most to least priority
		priority_list = [BuilderTask.BUILD_CORE_DEFENCE, BuilderTask.ATTACK_ENEMY_CORE, BuilderTask.CUTOFF_ENEMY_TURRET, BuilderTask.HEAL, BuilderTask.FOUND_CORE, BuilderTask.FIND_ENEMY_CORE,BuilderTask.BUILD_BRIDGE, BuilderTask.PLACE_SENTINEL, BuilderTask.FOUND_AX_ORE, BuilderTask.FOUND_TI_ORE, BuilderTask.FIND_ORE]
		#generate lookup table for task priorities      
		self.task_priority = {task: i for i, task in enumerate(priority_list)}

		self.launcher_gaps_board: int = 0          # tiles that should be left empty (in wall ring)
		self.launcher_positions_board: int = 0     # tiles where launchers should be built
		self.launcher_pocket_board: int = 0        # all tiles around launchers (must stay empty)
								
		super().__init__(ct, core_pos, move_dir)
		self.defence_walls_board: int = 0
		self.defence_conveyors_board: int = 0
		self.marker_info = LauncherMarkerData()
		
		self.marker_info.core_x = self.core_pos.x
		self.marker_info.core_y = self.core_pos.y

		self.add_task(ct, BuilderTask.BUILD_CORE_DEFENCE, 0)
	
	def turn_end(self, ct:Controller):
		super().turn_end(ct)
		self.marker_info.date = ct.get_current_round()
		current_pos = ct.get_position()
		for x in range(-1,2):
			for y in range(-1,2):
				check_pos = Position(current_pos.x+x, current_pos.y+y)
				if ct.can_place_marker(check_pos):
					ct.place_marker(check_pos, self.marker_info.as_int)
