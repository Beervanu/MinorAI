import importlib
import os
builder_tasks = {}
DO_ONCE_TASKS = []
#module_names = []
# for f in os.listdir():
# 	if f.endswith('.py') and not (f in ['__init__.py', 'task_templates.py']):
# 		module_names.append(f[:-3])
for module_name in ['find_ore', 'found_ti_ore', 'build_bridge', 'attack_enemy_core', 'place_sentinel', 'find_enemy_core']:
	module = importlib.import_module(f'.{module_name}', 'closedAI.Tasks')
	builder_tasks[module.task_type] = {'phases':module.phases, 'do_once': module.do_once}
	if module.do_once:
		DO_ONCE_TASKS.append(module.task_type)
	