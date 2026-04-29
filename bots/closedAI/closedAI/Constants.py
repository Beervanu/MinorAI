from cambc import Direction, EntityType
from .Tasktypes import BuilderTask
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
CARDINAL_DIRECTIONS = [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
CONVEYOR_ENTITIES = [EntityType.CONVEYOR, EntityType.BRIDGE, EntityType.ARMOURED_CONVEYOR]
TURRET_ENTITIES = [EntityType.SENTINEL, EntityType.GUNNER, EntityType.BREACH]
ESSENTIAL_TASKS = [BuilderTask.CUTOFF_ENEMY_TURRET, BuilderTask.HEAL, BuilderTask.BUILD_CORE_DEFENCE]