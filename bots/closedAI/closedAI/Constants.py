from cambc import Direction, EntityType
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
CARDINAL_DIRECTIONS = [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
CONVEYOR_ENTITIES = [EntityType.CONVEYOR, EntityType.BRIDGE, EntityType.ARMOURED_CONVEYOR]