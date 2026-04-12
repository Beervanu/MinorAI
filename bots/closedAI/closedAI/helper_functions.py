from cambc import Direction
import sys
def closest_diagonal(x_dir:Direction, y_dir:Direction):
	map = {
        (Direction.WEST, Direction.NORTH): Direction.NORTHWEST,
        (Direction.EAST, Direction.NORTH): Direction.NORTHEAST,
        (Direction.EAST, Direction.SOUTH): Direction.SOUTHEAST,
        (Direction.WEST, Direction.SOUTH): Direction.SOUTHWEST
    }
	return map[(x_dir, y_dir)]

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)