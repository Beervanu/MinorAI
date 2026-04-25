from .Turret import Turret
from cambc import Controller, EntityType, GameConstants, Position
from .Constants import DIRECTIONS
from .Markers import *

class LauncherBot(Turret):
    def __init__(self, ct: Controller):
        super().__init__(ct, EntityType.LAUNCHER)
        self.position = ct.get_position()
        self.our_core_pos: Position | None = None
        # Find the core to find what direction to yeet niggas
        # Look for a launcher marker nearby
        for pos in ct.get_nearby_tiles():
            b_id = ct.get_tile_building_id(pos)
            if b_id and ct.get_entity_type(b_id) == EntityType.MARKER and ct.get_team(b_id) == self.team:
                # Read the marker
                raw = ct.get_marker_value(b_id)
                m = MarkerData()
                m.as_int = raw
                if m.type == MarkerType.LAUNCHER:
                    lm = LauncherMarkerData()
                    lm.as_int = raw
                    self.our_core_pos = Position(lm.core_x, lm.core_y)
                    return


    def turn_start(self, ct: Controller):
        super().turn_start(ct)
        if self.our_core_pos is None:
            return
        
        # Check all 8 adjacent tiles for enemy bots
        for d in DIRECTIONS:
            adjacent = self.position.add(d)
            if not self.is_valid_position(adjacent):
                continue
            
            bot_id = ct.get_tile_builder_bot_id(adjacent)
            if not bot_id:
                continue
            if ct.get_team(bot_id) == self.team:
                continue  # don't launch our own bots
            
            target = self.pick_throw_target(ct, adjacent)
            if target and ct.can_launch(adjacent, target):
                ct.launch(adjacent, target)
                break  # one launch per turn

    def pick_throw_target(self, ct: Controller, bot_pos):
        """Pick the furthest passable tile within launch range, away from our core."""
        if self.our_core_pos is None:
            return None
        
        # Direction from core through us — i.e., outward
        away_dir = self.our_core_pos.direction_to(self.position)
        
        # Launch range² is 26, so Chebyshev ~5
        for dist in range(5, 0, -1):
            dx, dy = away_dir.delta()
            target_x = self.position.x + dx * dist
            target_y = self.position.y + dy * dist
            from cambc import Position
            target = Position(target_x, target_y)
            if not self.is_valid_position(target):
                continue
            if not ct.is_tile_passable(target):
                continue
            if self.position.distance_squared(target) > 26:
                continue
            return target
        return None