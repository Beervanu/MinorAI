from enum import IntEnum
from typing import TypedDict, Any
# least to highest priority
class BuilderTask(IntEnum):
	FIND_ORE = 0
	BUILD_BRIDGE = 1
	FOUND_TI_ORE = 2
	FOUND_AX_ORE = 3
	FIND_ENEMY_CORE = 4
	ATTACK_ENEMY_CORE = 5
	FOUND_CORE = 6
	PLACE_SENTINEL = 7
	CUTOFF_ENEMY_TURRET = 8
	HEAL = 9
	CUTOFF_ENEMY_LINES=10
	BUILD_CORE_DEFENCE = 11


type Task = BuilderTask 
class TaskData(TypedDict):
	uid: int
	type: Task
	data: Any
	identifier: int
	interruptable: bool
	timeout: int