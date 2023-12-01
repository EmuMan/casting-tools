import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Any
from dataclasses import dataclass

import obsws_python as obs

import casting_tools as ct

@dataclass
class Action:
    name: str
    key: str
    action: Callable
    
    def get_args(self):
        args = self.__dict__.copy()
        del args['name']
        del args['key']
        del args['action']
        return args

    def format_for_gui(self) -> str:
        args_str = ', '.join(f'{k}={v}' for k, v in self.get_args().items())
        return f'{self.name}: {args_str}'

    @classmethod
    def get_variable_init_fields(cls) -> list[tuple[str, Any]]:
        return [p for p in cls.__init__.__annotations__.items() if p[0] not in {'return', 'key', 'obs_client'}]

@dataclass
class NoneAction(Action):
    def __init__(self, key: str, **_):
        super().__init__(
            name='None',
            key=key,
            action=lambda: None,
        )

class TriggerStudioModeTransitionAction(Action):
    
    def __init__(self, key: str, obs_client: obs.ReqClient, **_):
        super().__init__(
            name='Trigger Studio Mode Transition',
            key=key,
            action=lambda: obs_client.trigger_studio_mode_transition(),
        )

class ToggleInputMuteAction(Action):
    
    input_name: str

    def __init__(self, key: str, obs_client: obs.ReqClient, input_name: str, **_):
        self.input_name = input_name
        super().__init__(
            name='Toggle Input Mute',
            key=key,
            action=lambda: obs_client.toggle_input_mute(input_name),
        )

class SetCurrentPreviewSceneAction(Action):
    
    scene_name: str
    
    def __init__(self, key: str, obs_client: obs.ReqClient, scene_name: str, **_):
        self.scene_name = scene_name
        super().__init__(
            name='Set Current Preview Scene',
            key=key,
            action=lambda: obs_client.set_current_preview_scene(scene_name),
        )

class SetCurrentSceneTransitionAction(Action):
    
    transition_name: str
    
    def __init__(self, key: str, obs_client: obs.ReqClient, transition_name: str, **_):
        self.transition_name = transition_name
        super().__init__(
            name='Set Current Scene Transition',
            key=key,
            action=lambda: obs_client.set_current_scene_transition(transition_name),
        )

class SetSourceVisibilityAction(Action):
    
    scene_name: str
    source_name: str
    visibility: bool
    
    def __init__(self, key: str, obs_client: obs.ReqClient, scene_name: str, source_name: str, visibility: bool, **_):
        self.scene_name = scene_name
        self.source_name = source_name
        self.visibility = visibility
        super().__init__(
            name='Set Source Visibility',
            key=key,
            action=lambda: ct.set_source_visibility(obs_client, scene_name, source_name, visibility),
        )

class SetSpectatedPlayerAction(Action):
    
    player_index: int
    
    def __init__(self, key: str, player_index: int, **_):
        self.player_index = player_index
        super().__init__(
            name='Set Spectated Player',
            key=key,
            action=lambda: ct.set_spectated_player(player_index),
        )

class PlayRandomAudioAction(Action):
    
    folder: str
    
    def __init__(self, key: str, folder: str, **_):
        self.folder = folder
        super().__init__(
            name='Play Random Audio',
            key=key,
            action=lambda: ct.play_random_audio(folder),
        )

class StopAudioAction(Action):
    
    def __init__(self, key: str, **_):
        super().__init__(
            name='Stop Audio',
            key=key,
            action=ct.stop_audio,
        )

class FadeOutAudioAction(Action):
    
    length: int
    
    def __init__(self, key: str, length: int, **_):
        self.length = length
        super().__init__(
            name='Fade Out Audio',
            key=key,
            action=lambda: ct.fade_out_audio(length),
        )

action_types = {
    'None': NoneAction,
    'Trigger Studio Mode Transition': TriggerStudioModeTransitionAction,
    'Toggle Input Mute': ToggleInputMuteAction,
    'Set Current Preview Scene': SetCurrentPreviewSceneAction,
    'Set Current Scene Transition': SetCurrentSceneTransitionAction,
    'Set Source Visibility': SetSourceVisibilityAction,
    'Set Spectated Player': SetSpectatedPlayerAction,
    'Play Random Audio': PlayRandomAudioAction,
    'Stop Audio Action': StopAudioAction,
    'Fade Out Audio Action': FadeOutAudioAction,
}

class CastingToolsGUI:
    
    root: tk.Tk | None = None
    obs_client: obs.ReqClient | None = None
    keybind_list: ttk.Treeview | None = None
    action_list: ttk.Treeview | None = None
    
    status_var: tk.StringVar | None = None
    obs_status_var: tk.StringVar | None = None
    audio_status_var: tk.StringVar | None = None
    midi_status_var: tk.StringVar | None = None
    
    keybinds: dict[str, list[Action]] = {}
    
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title('Casting Tools')
        self.root.geometry('1000x500')
        
        info_frame = tk.Frame(self.root)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        keybind_info_frame = tk.Frame(info_frame)
        keybind_info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.keybind_list = self.configure_keybind_info_frame(keybind_info_frame)
        
        action_info_frame = tk.Frame(info_frame)
        action_info_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.action_list = self.configure_action_info_frame(action_info_frame)
        
        status_frame = tk.Frame(self.root)
        status_frame.pack(fill=tk.X)
        self.configure_status_frame(status_frame)
        
        buttons_frame = tk.Frame(self.root)
        buttons_frame.pack(fill=tk.X)
        self.configure_buttons(buttons_frame)
        
        # Make it so that clicking a row in the table will print the row's values.
        def on_select(event):
            self.refresh_action_display()
        self.keybind_list.bind('<<TreeviewSelect>>', on_select)
        
        # Make it so that pressing delete will delete the selected row.
        def delete(event):
            self.keybind_list.delete(self.keybind_list.focus())
        self.root.bind('<Delete>', delete)
    
    def mainloop(self) -> None:
        self.root.mainloop()
    
    def create_connection_window(self, title: str, connect: Callable) -> tk.Toplevel:
        # Create a new window.
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry('300x100')
        window.grab_set()
        
        # Make it so that pressing enter will connect.
        def on_enter(event):
            connect()
        window.bind('<Return>', on_enter)
        
        # Make it so that pressing escape will close the window.
        def on_escape(event):
            window.destroy()
        window.bind('<Escape>', on_escape)
        
        # Make it so that the window will close when the root window closes.
        def on_close():
            window.destroy()
            self.root.destroy()
        self.root.protocol('WM_DELETE_WINDOW', on_close)
        
        return window
    
    def connect_to_obs_window(self) -> None:
        '''Open a new window to connect to OBS.'''
        address_var = tk.StringVar()
        address_var.set('localhost')
        port_var = tk.StringVar()
        port_var.set('4444')
        password_var = tk.StringVar()
        password_var.set('')
        
        def connect() -> None:
            self.obs_client = ct.connect_to_obs(address_var.get(), port_var.get(), password_var.get())
        window = self.create_connection_window('Connect to OBS', connect)
        
        # Create a text box for the address.
        ttk.Label(window, text='Address:').grid(row=0, column=0)
        ttk.Entry(window, textvariable=address_var).grid(row=0, column=1)
        
        # Create a text box for the port.
        ttk.Label(window, text='Port:').grid(row=1, column=0)
        ttk.Entry(window, textvariable=port_var).grid(row=1, column=1)
        
        # Create a text box for the password.
        ttk.Label(window, text='Password:').grid(row=2, column=0)
        ttk.Entry(window, textvariable=password_var).grid(row=2, column=1)
        
        # Create a submit button.
        def submit():
            connect()
            window.destroy()
        ttk.Button(window, text='Connect', command=submit).grid(row=3, column=0, columnspan=2)
    
    def connect_to_audio_device_window(self) -> None:
        '''Open a new window to connect to an audio device'''
        possible_devices = ct.list_possible_audio_devices()
        
        def connect() -> None:
            device_index = int(device_var.get().split(':')[0])
            self.audio_status_var.set(f'Connected to audio device {device_index}')
            ct.set_audio_output_device(device_index)
        window = self.create_connection_window('Connect to Audio Device', connect)
        
        # Create a dropdown for the audio device.
        device_var = tk.StringVar()
        device_var.set(possible_devices[0])
        ttk.Label(window, text='Device:').grid(row=0, column=0)
        ttk.OptionMenu(window, device_var, *possible_devices).grid(row=0, column=1)
        
        # Create a submit button.
        def submit():
            connect()
            window.destroy()
        ttk.Button(window, text='Connect', command=submit).grid(row=1, column=0, columnspan=2)
    
    def edit_action_window(self, original: Action) -> None:
        '''Open a new window to edit an action'''
        window = tk.Toplevel(self.root)
        window.title('Edit Action')
        window.geometry('300x100')
        window.grab_set()
        
        action_type_dropdown_var = tk.StringVar()
        action_type_dropdown_var.set(original.name)
        possible_action_types = list(action_types.keys())
        ttk.Label(window, text='Action Type:').grid(row=0, column=0)
        ttk.OptionMenu(window, action_type_dropdown_var, original.name, *possible_action_types).grid(row=0, column=1)
        
        action_options_frame = tk.Frame(window)
        action_options_frame.grid(row=1, column=0, columnspan=2)
        
        action_option_vars: list[tk.StringVar] = []
        
        def update_action_options_frame() -> None:
            for child in action_options_frame.winfo_children():
                child.destroy()
            action_option_vars.clear()
            action_type = action_types[action_type_dropdown_var.get()]
            for i, (field_name, _) in enumerate(action_type.get_variable_init_fields()):
                var = tk.StringVar()
                if action_type == type(original):
                    var.set(str(getattr(original, field_name)))
                action_option_vars.append(var)
                ttk.Label(action_options_frame, text=f'{field_name}:').grid(row=i, column=0)
                ttk.Entry(action_options_frame, textvariable=var).grid(row=i, column=1)
        
        update_action_options_frame()
        # update the options frame when the dropdown changes
        action_type_dropdown_var.trace('w', lambda *args: update_action_options_frame())
        
        def submit() -> None:
            action_type = action_types[action_type_dropdown_var.get()]
            init_fields: list[tuple[str, Any]] = action_type.get_variable_init_fields()
            args = [v.get() for v in action_option_vars]
            try:
                casted = [t(v) for (_, t), v in zip(init_fields, args)]
            except ValueError as e:
                ct.log(f'Error: {e}')
                return
            kwargs = dict(zip((f[0] for f in init_fields), casted))
            kwargs['key'] = original.key
            kwargs['obs_client'] = self.obs_client
            new_action = action_type(**kwargs)
            self.update_action(original, new_action)
            window.destroy()
        ttk.Button(window, text='Confirm', command=submit).grid(row=2, column=0, columnspan=2)
    
    def edit_keybind_window(self, original: str) -> None:
        '''Open a new window to edit a keybind'''
        window = tk.Toplevel(self.root)
        window.title('Edit Keybind')
        window.geometry('300x100')
        window.grab_set()
        
        keybind_var = tk.StringVar()
        keybind_var.set(original)
        ttk.Label(window, text='Keybind:').grid(row=0, column=0)
        ttk.Entry(window, textvariable=keybind_var).grid(row=0, column=1)
        
        def submit() -> None:
            new_keybind = keybind_var.get()
            if new_keybind not in self.keybinds:
                self.change_keybind(original, new_keybind)
                window.destroy()
            else:
                ct.log(f'Error: Keybind {new_keybind} already exists')
        ttk.Button(window, text='Confirm', command=submit).grid(row=1, column=0, columnspan=2)
        
    def get_current_keybind_focus(self) -> str | None:
        keybind_focus = self.keybind_list.focus()
        if keybind_focus != '':
            return self.keybind_list.item(keybind_focus)['values'][0]
        return None
    
    def add_action(self, action: Action, index: int | None = None) -> None:
        '''Add an action to the table.'''
        if action.key not in self.keybinds:
            self.keybinds[action.key] = []
            self.keybind_list.insert('', index if index is not None else tk.END, values=(action.key,))
        if index is None:
            self.keybinds[action.key].append(action)
        else:
            self.keybinds[action.key].insert(index, action)
        self.refresh_action_display()
    
    def remove_action(self, keybind: str, index: int) -> None:
        '''Remove an action from the table.'''
        self.keybinds[keybind].pop(index)
        self.refresh_action_display()
    
    def update_action(self, old_action: Action, new_action: Action) -> None:
        '''Update an action in the table.'''
        index = self.keybinds[old_action.key].index(old_action)
        self.remove_action(old_action.key, index)
        self.add_action(new_action, index)
    
    def add_keybind(self, keybind: str) -> None:
        '''Add a keybind to the table.'''
        if keybind not in self.keybinds:
            self.keybinds[keybind] = []
            self.keybind_list.insert('', tk.END, values=(keybind,))
    
    def remove_keybind(self, keybind: str) -> None:
        '''Remove a keybind from the table.'''
        del self.keybinds[keybind]
        for child in self.keybind_list.get_children():
            if self.keybind_list.item(child)['values'][0] == keybind:
                self.keybind_list.delete(child)
                break
    
    def change_keybind(self, old_keybind: str, new_keybind: str) -> None:
        '''Change a keybind in the table.'''
        self.keybinds[new_keybind] = self.keybinds[old_keybind]
        del self.keybinds[old_keybind]
        for action in self.keybinds[new_keybind]:
            action.key = new_keybind
        
        item = ''
        for child in self.keybind_list.get_children():
            if self.keybind_list.item(child)['values'][0] == old_keybind:
                item = child
        
        self.keybind_list.item(item, values=(new_keybind,))
    
    def refresh_action_display(self) -> None:
        '''Refresh the action table.'''
        self.action_list.delete(*self.action_list.get_children())
        current_focus = self.keybind_list.focus()
        if current_focus != '':
            for action in self.keybinds[self.keybind_list.item(current_focus)['values'][0]]:
                self.action_list.insert('', tk.END, values=(action.format_for_gui(),))

    def configure_keybind_info_frame(self, frame: tk.Frame) -> ttk.Treeview:
        '''Create a table of hotkey information with two columns.'''
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        table = ttk.Treeview(frame, columns=('key',), show='headings')
        table.pack(fill=tk.BOTH, expand=True)
        table.heading('key', text='Key')
        
        button_frame = tk.Frame(frame)
        button_frame.pack(fill=tk.X)
        
        def add_new_keybind() -> None:
            keybind = 'None'
            self.add_keybind(keybind)
            self.edit_keybind_window(keybind)
        ttk.Button(button_frame, text='Add Keybind', command=add_new_keybind).pack(side=tk.LEFT)
        
        def remove_selected_keybind() -> None:
            keybind_focus = self.keybind_list.focus()
            if keybind_focus != '':
                self.remove_keybind(self.keybind_list.item(keybind_focus)['values'][0])
        ttk.Button(button_frame, text='Remove Keybind', command=remove_selected_keybind).pack(side=tk.LEFT)
        
        def edit_selected_keybind() -> None:
            keybind_focus = self.keybind_list.focus()
            if keybind_focus != '':
                self.edit_keybind_window(self.keybind_list.item(keybind_focus)['values'][0])
        ttk.Button(button_frame, text='Edit Keybind', command=edit_selected_keybind).pack(side=tk.LEFT)
        
        return table
    
    def configure_action_info_frame(self, frame: tk.Frame) -> None:
        '''Create a frame of information about the selected action.'''
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        table = ttk.Treeview(frame, columns=('action',), show='headings')
        table.pack(fill=tk.BOTH, expand=True)
        table.heading('action', text='Action')
        
        button_frame = tk.Frame(frame)
        button_frame.pack(fill=tk.X)
        
        def add_new_action() -> None:
            current_keybind = self.get_current_keybind_focus()
            if current_keybind is not None:
                action = NoneAction(current_keybind)
                self.add_action(action)
                self.edit_action_window(action)
        ttk.Button(button_frame, text='Add Action', command=add_new_action).pack(side=tk.LEFT)

        def remove_selected_action() -> None:
            current_keybind = self.get_current_keybind_focus()
            if current_keybind is not None:
                action_focus = self.action_list.focus()
                if action_focus != '':
                    self.remove_action(current_keybind, self.action_list.index(action_focus))
        ttk.Button(button_frame, text='Remove Action', command=remove_selected_action).pack(side=tk.LEFT)
        
        def edit_selected_action() -> None:
            current_keybind = self.get_current_keybind_focus()
            if current_keybind is not None:
                action_focus = self.action_list.focus()
                if action_focus != '':
                    action = self.keybinds[current_keybind][self.action_list.index(action_focus)]
                    self.edit_action_window(action)
        ttk.Button(button_frame, text='Edit Action', command=edit_selected_action).pack(side=tk.LEFT)
        
        return table

    def configure_buttons(self, frame: tk.Frame) -> None:
        '''Create a frame of buttons for connecting to OBS, adding a sound device, and adding a MIDI device.'''       
        # Create a button to connect to OBS.
        ttk.Button(frame, text='Connect to OBS', command=self.connect_to_obs_window).pack(side=tk.LEFT, padx=5)
        
        # Create a button to add a sound device.
        ttk.Button(frame, text='Add Sound Device', command=self.connect_to_audio_device_window).pack(side=tk.LEFT, padx=5)
        
        # Create a button to add a MIDI device.
        ttk.Button(frame, text='Add MIDI Device', command=lambda: None).pack(side=tk.LEFT, padx=5)
    
    def configure_status_frame(self, frame: tk.Frame) -> None:
        '''Create a frame of connection status information.'''        
        # Create a label for the OBS connection status.
        self.obs_status_var = tk.StringVar()
        self.obs_status_var.set('Not connected to OBS')
        tk.Label(frame, textvariable=self.obs_status_var).pack(side=tk.LEFT, padx=5)
        
        # Create a label for the audio connection status.
        self.audio_status_var = tk.StringVar()
        self.audio_status_var.set('No audio device connected')
        tk.Label(frame, textvariable=self.audio_status_var).pack(side=tk.LEFT, padx=5)
        
        # Create a label for the MIDI connection status.
        self.midi_status_var = tk.StringVar()
        self.midi_status_var.set('No MIDI device connected')
        tk.Label(frame, textvariable=self.midi_status_var).pack(side=tk.LEFT, padx=5)

    def insert_test_values(self) -> None:
        '''Insert some test values into the table.'''
        test_action_1 = SetSourceVisibilityAction('Ctrl+Shift+1', None, 'Scene 1', 'Source 1', True)
        test_action_2 = SetSourceVisibilityAction('Ctrl+Shift+1', None, 'Scene 1', 'Source 2', True)
        test_action_3 = SetSourceVisibilityAction('Ctrl+Shift+2', None, 'Scene 1', 'Source 3', True)
        self.add_action(test_action_1)
        self.add_action(test_action_2)
        self.add_action(test_action_3)

def main():
    gui = CastingToolsGUI()
    gui.insert_test_values()
    gui.mainloop()

if __name__ == '__main__':
    main()
