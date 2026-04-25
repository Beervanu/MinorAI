# Marker type identifiers
class MarkerType:
    CENTRAL = 0
    TASK = 1
    LAUNCHER = 2


class MarkerData:
    def __init__(self):
        self.b = 0

    def get_bits(self, start, num):
        mask = (1 << num) - 1
        return (self.b >> start) & mask

    def set_bits(self, start, num, value):
        """Sets `num` bits starting at `start` to `value`, clearing first."""
        mask = (1 << num) - 1
        # Clear the target bits, then OR in the new value
        self.b = (self.b & ~(mask << start)) | ((value & mask) << start)

    @property
    def as_int(self):
        return self.get_bits(0, 32)

    @as_int.setter
    def as_int(self, val):
        self.set_bits(0, 32, val)

    @property
    def type(self):
        return self.get_bits(0, 2)  # widened to 2 bits

    @type.setter
    def type(self, val):
        self.set_bits(0, 2, val)

    @property
    def date(self):
        return self.get_bits(2, 12)  # shifted up to start at bit 2

    @date.setter
    def date(self, val):
        self.set_bits(2, 12, val)


class TaskMarkerData(MarkerData):
    def __init__(self):
        super().__init__()
        self.type = MarkerType.TASK

    @property
    def task_type(self):
        return self.get_bits(14, 4)

    @task_type.setter
    def task_type(self, val):
        self.set_bits(14, 4, val)

    @property
    def task_identifier(self):
        return self.get_bits(18, 14)

    @task_identifier.setter
    def task_identifier(self, val):
        self.set_bits(18, 14, val)


class CentralMarkerData(MarkerData):
    def __init__(self):
        super().__init__()
        self.type = MarkerType.CENTRAL

    @property
    def known_map_symmetry(self):
        return self.get_bits(14, 2)

    @known_map_symmetry.setter
    def known_map_symmetry(self, val):
        self.set_bits(14, 2, val)


class LauncherMarkerData(MarkerData):
    def __init__(self):
        super().__init__()
        self.type = MarkerType.LAUNCHER

    @property
    def core_x(self):
        return self.get_bits(14, 6)

    @core_x.setter
    def core_x(self, val):
        self.set_bits(14, 6, val)

    @property
    def core_y(self):
        return self.get_bits(20, 6)

    @core_y.setter
    def core_y(self, val):
        self.set_bits(20, 6, val)