import time
import sys
from dataclasses import dataclass
from typing import Callable, Any
import threading
import json
import functools
import queue
import os
import random

import mido
import obsws_python as obs
import win32api, win32con
import keyboard
import sounddevice as sd
import soundfile as sf
import numpy as np


MUSIC_BUFFERSIZE = 20 # number of blocks in the buffer
MUSIC_BLOCKSIZE = 2048 # size of each sample block


# god this is awful
log = print


current_character_index = 0
target_character_index = 0

music_end_event = threading.Event()
audio_output_device = None
music_fade_out_length = 0
current_music_fade_out_progress = 0


class OBSInterfaceException(Exception):
    pass

class SoundPlayer:
    
    filename: str
    device: int | str
    soundfile: sf.SoundFile
    _queue: queue.Queue
    buffer_size: int
    block_size: int
    playing: bool
    
    def __init__(self,
                 filename: str,
                 device: int | str,
                 buffer_size: int = 20,
                 block_size: int = 2048):
        self.filename = filename
        self.device = device
        self.soundfile = sf.SoundFile(filename)
        self._queue = queue.Queue(maxsize=buffer_size)
        self.buffer_size = buffer_size
        self.block_size = block_size
        self.playing = False
    
    def callback(self, outdata, frames, time, status):
        assert frames == self.block_size
        if status.output_underflow:
            log('Output underflow: increase blocksize?', file=sys.stderr)
            raise sd.CallbackAbort
        assert not status
        try:
            data = self._queue.get_nowait()
        except queue.Empty as e:
            log('Buffer is empty: increase buffersize?', file=sys.stderr)
            raise sd.CallbackAbort from e
        if len(data) < len(outdata):
            outdata[:len(data)] = data
            outdata[len(data):].fill(0)
            raise sd.CallbackStop
        else:
            outdata[:] = data
    
    def play(self):
        if self.playing:
            return
        self.playing = True
        self.soundfile.seek(0)
        music_end_event.clear()
        
        # Pre-fill queue
        for _ in range(self.buffer_size):
            data = self.soundfile.read(self.block_size)
            if not len(data):
                break
            self._queue.put_nowait(data)
        
        # Create output stream
        stream = sd.OutputStream(
            samplerate=self.soundfile.samplerate, blocksize=self.block_size,
            device=self.device, channels=self.soundfile.channels,
            callback=self.callback, finished_callback=music_end_event.set)
        
        with stream:
            # Keep playing until the entire file has been played
            timeout = self.block_size * self.buffer_size / self.soundfile.samplerate
            while len(data):
                # If the music has been stopped, break
                if music_end_event.is_set():
                    break
                data = self.soundfile.read(self.block_size)
                global music_fade_out_length
                if music_fade_out_length > 0:
                    global current_music_fade_out_progress
                    if current_music_fade_out_progress == music_fade_out_length:
                        # done fading out
                        break
                    # big range that will be sliced
                    fade_out = np.arange(1.0, 0.0, -(1.0 / music_fade_out_length))
                    new_fade_out_progress = current_music_fade_out_progress + len(data)
                    # fade out progress should cap at the length
                    if new_fade_out_progress > music_fade_out_length:
                        new_fade_out_progress = music_fade_out_length
                        music_fade_out_length = 0
                        # shorten data to match if fade out progress was shortened
                        data = data[:(new_fade_out_progress - current_music_fade_out_progress)]
                    # apply the fade out
                    fade_out = fade_out[current_music_fade_out_progress:new_fade_out_progress]
                    data *= np.vstack([fade_out, fade_out]).T
                    current_music_fade_out_progress = new_fade_out_progress
                try:
                    self._queue.put(data, timeout=timeout)
                except queue.Full:
                    # yucky fix
                    pass
            music_end_event.wait()  # Wait until playback is finished
        
        # Clean up
        music_end_event.clear()
        self._queue.queue.clear()
        self.playing = False
    
    def close(self):
        self.soundfile.close()

def create_music_thread(filename: str,
                        device: int | str,
                        buffer_size = 20,
                        block_size = 2048) -> threading.Thread:
    music_thread = threading.Thread(
        target=SoundPlayer(filename, device, buffer_size, block_size).play)
    music_thread.daemon = True
    music_thread.start()
    return music_thread

def play_random_audio(folder_path: str, device: int | str | None) -> threading.Thread:
    if device is None:
        log('Error: To play audio, \'use_output_audio\' must be set to true in config.json')
    songs = os.listdir(folder_path)
    song = random.choice(songs)
    return create_music_thread(os.path.join(folder_path, song), device)

def fade_out_audio(length: int) -> None:
    global music_fade_out_length
    global current_music_fade_out_progress
    music_fade_out_length = length
    current_music_fade_out_progress = 0

def stop_audio() -> None:
    music_end_event.set()

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

def set_spectated_player(index: int) -> None:
    global target_character_index
    target_character_index = index

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
        log(f'MIDI note pressed: {message.note}')
        for binding in midi_bindings:
            if binding['note'] == message.note:
                perform_actions(obs_client, binding['actions'])
    return on_message

def perform_actions(obs_client: obs.ReqClient, actions: list[dict], *_) -> None:
    # TODO: Use keyboard event that is passed in now I guess
    for action in actions:
        perform_action(obs_client, action)

def perform_action(obs_client: obs.ReqClient, action: dict) -> None:
    match action['type']:
        case 'trigger_studio_mode_transition':
            obs_client.trigger_studio_mode_transition()
        case 'toggle_input_mute':
            obs_client.toggle_input_mute(action['name'])
        case 'set_current_preview_scene':
            obs_client.set_current_preview_scene(action['name'])
        case 'set_current_scene_transition':
            obs_client.set_current_scene_transition(action['name'])
        case 'set_source_visibility':
            set_source_visibility(obs_client, action['scene'], action['name'], action['visible'])
        case 'set_spectated_player':
            set_spectated_player(action['index'])
        case 'play_random_audio':
            play_random_audio(action['folder'], audio_output_device)
        case 'stop_audio':
            music_end_event.set()
        case 'fade_out_audio':
            fade_out_audio(action['length'])

def get_midi_input_device() -> Any: # idk what actual type is
    controller = None
    controllers = mido.get_input_names()

    if len(controllers) == 0:
        log('No available controllers found. Exiting...')
        return None
    elif len(controllers) == 1:
        controller = controllers[0]

    if controller is None:
        log('Choose an available controller (type the number):')
        for i, option in enumerate(controllers, start=1):
            log(f'\t{i}: {option}')
        log()

    while controller is None:
        user_input = input('Selected controller: ')
        try:
            controller = controllers[int(user_input) - 1]
        except ValueError:
            log('Error: Selection must be a valid integer.')
        except IndexError:
            log(f'Error: Selection must be between 1 and {len(controllers)}')
    
    return controller

def list_possible_audio_devices() -> list[str]:
    devices = sd.query_devices()
    devices = {device['index']: device['name'] for device in devices if device['max_output_channels'] > 0}
    devices[sd.default.device[1]] += ' (default)'
    return [f'{str(index)}: {name}' for index, name in sorted(list(devices.items()), key=lambda x: x[0])]

def set_audio_output_device(device: int) -> None:
    global audio_output_device
    audio_output_device = device

def get_audio_output_device() -> dict[str, Any]:
    devices = sd.query_devices()
    for device in devices:
        device['is_output'] = device['max_output_channels'] > 0
    log('Select an audio output device (type the number):')
    for i, device in enumerate(devices, start=1):
        if device['is_output']:
            if device['index'] == sd.default.device[1]:
                log('>', end='')
            log(f'\t{i}: {device["name"]}')
    log()

    while True:
        user_input = input('Selected device: ')
        try:
            return devices[int(user_input) - 1]
        except ValueError:
            log('Error: Selection must be a valid integer.')
        except IndexError:
            log(f'Error: Selection must be between 1 and {len(devices)}')

def connect_to_obs(host: str, port: int | str, password: str) -> obs.ReqClient | None:
    try:
        port = int(port)
    except ValueError:
        log('Port number must be a valid integer!')
    log('Connecting to OBS... ', end='')
    try:
        obs_client = obs.ReqClient(
            host=host,
            port=port,
            password=password,
            timeout=3)
    except ConnectionRefusedError:
        log('Error!')
        log('Could not connect to OBS! Make sure you have a websocket server open.')
        return
    log('connected!')
    return obs_client

def main() -> None:
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except OSError as e:
        log(f'Error opening config.json: {e}. Exiting...')
        return
    
    obs_client = connect_to_obs(
        host=config['obs']['host'],
        port=config['obs']['port'],
        password=config['obs']['password'],
    )
    if obs_client is None:
        return

    midi_controller = None
    if config['use_midi_controller']:
        log()
        midi_controller = get_midi_input_device()
        if midi_controller is None:
            # could not find a valid controller
            return
    
    if config['use_output_audio']:
        log()
        set_audio_output_device(get_audio_output_device()['index'])
    
    for binding in config['keyboard_bindings']:
        keyboard.on_press_key(binding['key'],
                              functools.partial(perform_actions, obs_client, binding['actions']))
    character_switch_thread = threading.Thread(target=move_to_target_loop)
    character_switch_thread.daemon = True
    character_switch_thread.start()

    log()
    log('Listening for actions...')

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
