from enum import IntEnum

class MapSymmetry(IntEnum):
	ROTATIONAL = 1
	REFLECTION_X = 2
	REFLECTION_Y = 3
	UNKNOWN = 0

MAP_SYMMETRY_PLAINTEXT = {MapSymmetry.UNKNOWN:'unknown', MapSymmetry.ROTATIONAL: 'rotational', MapSymmetry.REFLECTION_X: 'reflected in x', MapSymmetry.REFLECTION_Y: 'reflected in y'}
