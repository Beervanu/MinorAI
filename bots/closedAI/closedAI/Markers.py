

class MarkerData:
	def __init__(self):
		self.b = 0
	
	def get_bits(self, start, num):
		mask = (pow(2, num)-1)
		return (self.b>>start)&mask

	def set_bits(self, start, value):
		self.b|=value<<start

	@property
	def as_int(self):
		return self.get_bits(0,32)

	@as_int.setter
	def as_int(self, val):
		self.set_bits(0, val)

	@property
	def type(self):
		return self.get_bits(0,1)

	@type.setter
	def type(self, val):
		self.set_bits(0, val)

	@property
	def date(self):
		return self.get_bits(1,12)
	
	@date.setter
	def date(self, val):
		self.set_bits(1, val)

class TaskMarkerData(MarkerData):

	@property
	def task_type(self):
		return self.get_bits(12,4)

	@task_type.setter
	def task_type(self, val):
		self.set_bits(12, val)
	
	@property
	def task_identifier(self):
		return self.get_bits(16,15)

	@task_identifier.setter
	def task_identifier(self, val):
		self.set_bits(16, val)

class CentralMarkerData(MarkerData):
	@property
	def known_map_symmetry(self):
		return self.get_bits(12,2)

	@known_map_symmetry.setter
	def known_map_symmetry(self, val):
		self.set_bits(12, val)
