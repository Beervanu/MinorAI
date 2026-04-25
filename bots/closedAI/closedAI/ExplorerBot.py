from cambc import Controller, Direction, Position
from .Tasktypes import BuilderTask
from .Markers import TaskMarkerData
from .BuilderBot import BuilderBot

class ExplorerBot(BuilderBot):
	def __init__(self, ct: Controller, core_pos: Position, move_dir: Direction):
		#must generate before calling super()
		#most to least priority
		priority_list = [BuilderTask.ATTACK_ENEMY_CORE, BuilderTask.CUTOFF_ENEMY_TURRET, BuilderTask.HEAL,BuilderTask.CUTOFF_ENEMY_LINES, BuilderTask.FOUND_CORE, BuilderTask.FIND_ENEMY_CORE,BuilderTask.BUILD_BRIDGE, BuilderTask.PLACE_SENTINEL, BuilderTask.FOUND_AX_ORE, BuilderTask.FOUND_TI_ORE, BuilderTask.BUILD_CORE_DEFENCE, BuilderTask.FIND_ORE]
		#generate lookup table for task priorities      
		self.task_priority = {task: i for i, task in enumerate(priority_list)}

		super().__init__(ct, core_pos, move_dir)
	
	def turn_end(self, ct:Controller):
		super().turn_end(ct)
		write = TaskMarkerData()
		write.date = ct.get_current_round()
		write.task_type = self.task['type']
		write.task_identifier = self.task['identifier']
		current_pos = ct.get_position()
		for x in range(-1,2):
			for y in range(-1,2):
				check_pos = Position(current_pos.x+x, current_pos.y+y)
				if ct.can_place_marker(check_pos):
					ct.place_marker(check_pos, write.as_int)