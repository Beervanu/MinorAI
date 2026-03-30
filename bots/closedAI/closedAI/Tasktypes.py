from enum import IntEnum
from typing import TypedDict, Any
class BuilderTask(IntEnum):
	FIND_ORE = 0
	BUILD_BRIDGE = 1
	FOUND_TI_ORE = 2
	FOUND_AX_ORE = 3
	FIND_ENEMY_CORE = 4
	GOTO_ENEMY_CORE = 5
	ATTACK_ENEMY_CORE = 6
	FOUND_CORE = 7
	ATTACK_ENEMY_BRIDGE = 8

type Task = BuilderTask 
class TaskData(TypedDict):
	uid: int
	type: Task
	data: Any
	identifier: int
	interruptable: bool