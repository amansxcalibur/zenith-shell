import copy
from config.info import config
import pprint

class SettingsState:
    def __init__(self):
        # config.get_all() does a shallow copy
        self.staged_data = copy.deepcopy(config.get_all())

    def get(self, path: list):
        cursor = self.staged_data
        try:
            for key in path:
                cursor = cursor[key]
            return cursor
        except (KeyError, TypeError):
            return None

    def update(self, path: list, value: any):
        """
        path: ["i3", "gaps", "inner", "props"]
        """
        cursor = self.staged_data
        for key in path[:-1]:
            # pprint.pprint(cursor)
            cursor = cursor.setdefault(key, {})

        cursor[path[-1]] = value
        # print(f"== updating {path} ==")
        # pprint.pprint(cursor)
        # print(value)
        # print()

    def print_all(self):
        pprint.pprint(self.staged_data)

    def save_to_disk(self):
        """Commits only modified changes to config"""
        self._apply_dict(self.staged_data, [])

    def _apply_dict(self, data, path):
        for key, value in data.items():
            current_path = path + [key]
            if isinstance(value, dict):
                # recurse deeper
                self._apply_dict(value, current_path)
            else:
                config.set(current_path, value=value)

state = SettingsState()