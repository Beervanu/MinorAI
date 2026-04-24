import importlib

from ..Tasktypes import Task
builder_tasks:dict[Task, dict] = {}
DO_ONCE_TASKS = []
for module_name in ['find_ore', 'found_ti_ore', 'build_bridge', 'attack_enemy_core', 'place_sentinel', 'find_enemy_core', 'cutoff_enemy_turret', 'heal', 'build_core_defense']:
	module = importlib.import_module(f'.{module_name}', 'closedAI.Tasks')
	if not hasattr(module, 'is_valid'):
		is_v = lambda x,y,z: True
	else:
		is_v = module.is_valid

	builder_tasks[module.task_type] = {'phases':module.phases, 'do_once': module.do_once, 'is_valid': is_v}
	if module.do_once:
		DO_ONCE_TASKS.append(module.task_type)
	