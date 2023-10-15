import time
from dataclasses import dataclass
from typing import Callable, Any
import threading

import mido
import obsws_python as obs
import win32api, win32con
import keyboard

obs_client = obs.ReqClient(host='localhost', port=4455, password='2QPfqqJFFMHIBOYa', timeout=3)

current_character_index = 0
target_character_index = 0

class OBSInterfaceException(Exception):
    pass

@dataclass
class NoteBinding:
    note: int
    on_down: bool
    on_up: bool
    operation: Callable
    
    def __call__(self) -> None:
        try:
            self.operation()
        except Exception as e:
            print(e)

@dataclass
class KeyBinding:
    key: str
    character_index: int

def get_source(scene_name: str, source_name: str) -> Any:
    scene_items = obs_client.get_scene_item_list(name=scene_name).scene_items
    for scene in scene_items:
        if scene['sourceName'] == source_name:
            return scene
    raise OBSInterfaceException(f'Could not find source {source_name} in scene {scene_name}.')

def set_source_visibility(scene_name: str, source_name: str, visible: bool) -> None:
    source = get_source(scene_name, source_name)
    obs_client.set_scene_item_enabled(scene_name=scene_name, item_id=source['sceneItemId'], enabled=visible)

def get_source_visibility(scene_name: str, source_name: str) -> bool:
    source = get_source(scene_name, source_name)
    return source['sceneItemEnabled']

# yes, it does have to happen this way
def create_set_character_index_callback(index: int) -> None:
    def set_character_index_callback(_) -> None:
        global target_character_index
        target_character_index = index
    return set_character_index_callback

def move_to_target_loop() -> None:
    global current_character_index
    global target_character_index
    while True:
        if current_character_index < target_character_index:
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            current_character_index += 1
        elif current_character_index > target_character_index:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            current_character_index -= 1
        time.sleep(0.1)

note_bindings = [
    # trigger transition
    NoteBinding(36, True, False, lambda: obs_client.trigger_studio_mode_transition()),

    # audio
    NoteBinding(38, True, False, lambda: obs_client.toggle_input_mute('Desktop Audio')),
    NoteBinding(39, True, False, lambda: obs_client.toggle_input_mute('Mic/Aux')),

    # scenes
    NoteBinding(40, True, False, lambda: obs_client.set_current_preview_scene('Waiting')),
    NoteBinding(41, True, False, lambda: obs_client.set_current_preview_scene('Game Only')),
    NoteBinding(42, True, False, lambda: obs_client.set_current_preview_scene('Casters')),
    NoteBinding(43, True, False, lambda: obs_client.set_current_preview_scene('Casters 2')),

    # transitions
    NoteBinding(44, True, False, lambda: obs_client.set_current_scene_transition('Base Stinger')),
    NoteBinding(45, True, False, lambda: obs_client.set_current_scene_transition('Fade')),
    NoteBinding(46, True, False, lambda: obs_client.set_current_scene_transition('Cut')),

    # waiting text
    NoteBinding(50, True, False, lambda: set_source_visibility('Waiting', 'Starting In', True)),
    NoteBinding(50, True, False, lambda: set_source_visibility('Waiting', 'Resuming In', False)),
    NoteBinding(51, True, False, lambda: set_source_visibility('Waiting', 'Starting In', False)),
    NoteBinding(51, True, False, lambda: set_source_visibility('Waiting', 'Resuming In', True)),
]

keyboard_bindings = [
    KeyBinding('f1', 0),
    KeyBinding('f2', 1),
    KeyBinding('f3', 2),
    KeyBinding('f4', 3),
    KeyBinding('f5', 4),
]

def on_message(message: mido.Message) -> None:
    if message.type not in {'note_on', 'note_off'}:
        return
    print(message)
    for binding in note_bindings:
        if binding.note != message.note:
            continue
        if message.type == 'note_on' and binding.on_down:
            binding()
        elif message.type == 'note_off' and binding.on_up:
            binding()

def main() -> None:
    controller = None
    controllers = mido.get_input_names()

    if len(controllers) == 0:
        print('No available controllers found. Exiting...')
    elif len(controllers) == 1:
        controller = controllers[0]

    if controller is None:
        print('Choose an available controller (type the number):')
        for i, option in enumerate(controllers, start=1):
            print(f'\t{i}: {option}')
        print()

    while controller is None:
        user_input = input('Selected controller: ')
        try:
            controller = controllers[int(user_input) - 1]
        except ValueError:
            print('Error: Selection must be a valid integer.')
        except IndexError:
            print(f'Error: Selection must be between 1 and {len(controllers)}')
    
    for binding in keyboard_bindings:
        keyboard.on_press_key(binding.key, create_set_character_index_callback(binding.character_index))
    character_switch_thread = threading.Thread(target=move_to_target_loop)
    character_switch_thread.daemon = True
    character_switch_thread.start()

    try:
        inport = mido.open_input(name=controller, callback=on_message)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        inport.close()
        keyboard.unhook_all()


if __name__ == '__main__':
    main()
