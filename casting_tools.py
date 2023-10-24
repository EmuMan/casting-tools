import time
from dataclasses import dataclass
from typing import Callable, Any
import threading
import json
import functools

import mido
import obsws_python as obs
import win32api, win32con
import keyboard


current_character_index = 0
target_character_index = 0


class OBSInterfaceException(Exception):
    pass

def get_source(obs_client: obs.ReqClient, scene_name: str, source_name: str) -> Any:
    scene_items = obs_client.get_scene_item_list(name=scene_name).scene_items
    for scene in scene_items:
        if scene['sourceName'] == source_name:
            return scene
    raise OBSInterfaceException(f'Could not find source {source_name} in scene {scene_name}.')

def set_source_visibility(obs_client: obs.ReqClient, scene_name: str, source_name: str, visible: bool) -> None:
    source = get_source(obs_client, scene_name, source_name)
    obs_client.set_scene_item_enabled(scene_name=scene_name, item_id=source['sceneItemId'], enabled=visible)

def get_source_visibility(obs_client: obs.ReqClient, scene_name: str, source_name: str) -> bool:
    source = get_source(obs_client, scene_name, source_name)
    return source['sceneItemEnabled']

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

def create_on_message(obs_client: obs.ReqClient, midi_bindings: list[dict]) -> Callable:
    def on_message(message: mido.Message) -> None:
        if message.type != 'note_on':
            return
        print(f'MIDI note pressed: {message.note}')
        for binding in midi_bindings:
            if binding['note'] == message.note:
                perform_actions(obs_client, binding['actions'])
    return on_message

def perform_actions(obs_client: obs.ReqClient, actions: list[dict]) -> None:
    for action in actions:
        perform_action(obs_client, action)

def perform_action(obs_client: obs.ReqClient, action: dict) -> None:
    match action["type"]:
        case "trigger_studio_mode_transition":
            obs_client.trigger_studio_mode_transition()
        case "toggle_input_mute":
            obs_client.toggle_input_mute(action['name'])
        case "set_current_preview_scene":
            obs_client.set_current_preview_scene(action['name'])
        case "set_current_scene_transition":
            obs_client.set_current_scene_transition(action['name'])
        case "set_source_visibility":
            set_source_visibility(obs_client, action['scene'], action['name'], action['visible'])
        case "set_spectated_player":
            global target_character_index
            target_character_index = action['index']

def get_midi_input_device() -> Any: # idk what actual type is
    controller = None
    controllers = mido.get_input_names()

    if len(controllers) == 0:
        print('No available controllers found. Exiting...')
        return None
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
    
    return controller

def main() -> None:
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except OSError as e:
        print(f'Error opening config.json: {e}. Exiting...')
        return
    
    print('Connecting to OBS... ', end='')
    obs_client = obs.ReqClient(
        host=config['obs']['host'],
        port=config['obs']['port'],
        password=config['obs']['password'],
        timeout=3)
    print('connected!')

    midi_controller = None
    if config['use_midi_controller']:
        midi_controller = get_midi_input_device()
        if midi_controller is None:
            # could not find a valid controller
            return
    
    for binding in config['keyboard_bindings']:
        keyboard.on_press_key(binding['key'],
                              functools.partial(perform_actions, obs_client, binding['actions']))
    character_switch_thread = threading.Thread(target=move_to_target_loop)
    character_switch_thread.daemon = True
    character_switch_thread.start()

    try:
        if midi_controller is not None:
            inport = mido.open_input(name=midi_controller,
                                    callback=create_on_message(obs_client, config['midi_bindings']))
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        inport.close()
        keyboard.unhook_all()


if __name__ == '__main__':
    main()
