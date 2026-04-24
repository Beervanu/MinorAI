from cambc import Controller, Direction, Position
from .Tasktypes import BuilderTask
from .BuilderBot import BuilderBot

class DefenderBot(BuilderBot):
    def __init__(self, ct: Controller, core_pos: Position, move_dir: Direction):
        #must generate before calling super()
        #most to least priority
        priority_list = [BuilderTask.BUILD_CORE_DEFENCE, BuilderTask.ATTACK_ENEMY_CORE, BuilderTask.CUTOFF_ENEMY_TURRET, BuilderTask.HEAL, BuilderTask.FOUND_CORE, BuilderTask.FIND_ENEMY_CORE,BuilderTask.BUILD_BRIDGE, BuilderTask.PLACE_SENTINEL, BuilderTask.FOUND_AX_ORE, BuilderTask.FOUND_TI_ORE, BuilderTask.FIND_ORE]
        #generate lookup table for task priorities      
        self.task_priority = {task: i for i, task in enumerate(priority_list)}
                                
        super().__init__(ct, core_pos, move_dir)
        self.defence_walls_board: int = 0
        self.defence_conveyors_board: int = 0

        self.add_task(ct, BuilderTask.BUILD_CORE_DEFENCE, None)
