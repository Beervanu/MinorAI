from enum import IntEnum
from typing import TypedDict, Any
# least to highest priority
class BuilderTask(IntEnum):
	FIND_ORE = 0
	BUILD_BRIDGE = 1
	FOUND_ORE = 2
	FIND_ENEMY_CORE = 3
	ATTACK_ENEMY_CORE = 4
	PLACE_SENTINEL = 5
	CUTOFF_ENEMY_TURRET = 6
	HEAL =7
	REFINE_AXIONITE = 8
	CUTOFF_ENEMY_LINES=9
	BUILD_CORE_DEFENCE = 10
	GET_RID_OF_INTRUDERS = 11


type Task = BuilderTask 
class TaskData(TypedDict):
	uid: int
	type: Task
	data: Any
	identifier: int
	interruptable: bool
	timeout: int