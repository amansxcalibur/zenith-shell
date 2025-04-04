from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.stack import Stack

from player_service import PlayerService
import icons.icons as icons
import os

class Player(Box):
    def __init__(self, manager, player, **kwargs):
        super().__init__(
            name="player",
            orientation="v",
            **kwargs)
        
        self.manager = manager
        # self.manager.connect("meta-change", self.on_metadata)
        self.manager.connect("pause", self.on_pause)
        self.manager.connect("play", self.on_play)
        self.player_name = Label(name=player.props.player_name, style_classes="player-icon", markup=getattr(icons, player.props.player_name, icons.disc))
        
        # self.image = Image(
        #     name="player-image",
        #     image_file=os.path.expanduser("/home/aman/Pictures/Wallpapers/wallhaven-rr9dlm_1848x1500.png"),
        #     size=500,
        #     h_align="center",
        #     v_align="center",
        # )

        self.set_style(f"background-image:url('/home/aman/Pictures/Wallpapers/wallhaven-weprlq_1920x1080.png')")

        self.song = Label(name="song", label="song", justification="left", h_align="start")
        self.artist = Label(name="artist", label="artist", justification="left", h_align="start")
        self.music = Box(
            name="music",
            orientation="v",
            h_expand=True,
            v_expand=True,
            children=[
                self.song,
                self.artist
            ]
        )

        self.play_pause_button = Button(
                    name="pause-button",
                    child=Label(name="pause-label", markup=icons.play),
                    tooltip_text="Exit",
                    # on_clicked=lambda *_: self.close_launcher()
        )

        self.children = [
            Box(name="source", h_expand=True, v_expand=True, children=self.player_name),
            CenterBox(
                name="details", 
                # h_expand=True, 
                # v_expand=True,
                start_children=self.music,
                end_children=self.play_pause_button
            ),
            Box(name="controls", 
                # h_expand=True, 
                # v_expand=True,
                spacing=20,
                children=[
                    Button(name="prev-button",child=Label(name="play-previous", markup=icons.previous)),
                    CenterBox(
                        name="progress-container",
                        h_expand=True,
                        v_expand=False,
                        orientation='v',
                        center_children=Box(name="progress")
                    ),
                    Button(name="next-button", child=Label(name="play-next", markup=icons.next)),
                    Button(name="shuffle-button", child=Label(name="shuffle", markup=icons.shuffle)),
                ]
            )
        ]

    def on_metadata(self, manager, metadata, player):
        keys = metadata.keys()
        if 'xesam:artist' in keys and 'xesam:title' in keys:
            self.song.set_label(metadata['xesam:title'])
            self.artist.set_label(metadata['xesam:artist'][0])
        print("everuthgin fine here")
        # self.player_name.set_label(player.props.player_name)

    def on_pause(self, manager):
        self.play_pause_button.get_child().set_markup(icons.play)

    def on_play(self, manager):
        self.play_pause_button.get_child().set_markup(icons.pause)

class PlayerContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="player-container",
            orientation="v",
            **kwargs
        )
        
        self.manager = PlayerService()
        self.manager.connect("new-player", self.new_player)
        self.manager.connect("meta-change", self.on_metadata)
        self.stack = Stack(
            name="player-container",
            transition_type="crossfade",
            transition_duration=100,
            children=[]
        )

        self.player_stack = Stack(
            name="player-stack",
            transition_type="crossfade",
            transition_duration=100,
            children=[]
        )

        self.player_switch_container = CenterBox(
            name="player-switch-container", 
            orientation='h',
            center_children=[]
            )
        self.children = [self.stack, self.player_switch_container]
        self.player = []
        self.manager.init_all_players()
        
    def new_player(self, manager, player):
        print(player.props.player_name,"here is the appended hcild name")
        new_player = Player(manager = self.manager, player = player)
        self.player.append(new_player)
        print("stacking dis bitvch")
        self.stack.add_named(new_player, player.props.player_name)
        self.player_switch_container.add_center(
            Button(name="player-button", on_clicked=lambda b: self.switch_player(player.props.player_name, b)))

    def switch_player(self, player_name, b):
        self.stack.set_visible_child_name(player_name)
        for i, btn in enumerate(self.player_switch_container.center_children):
            btn.remove_style_class("active")
        b.add_style_class("active")
        # print(self.stack.get_visible_child().player_name.get_label())

    def on_metadata(self, manager, metadata, player):
        keys = metadata.keys()
        if 'xesam:artist' in keys and 'xesam:title' in keys:
            print('{} - {}'.format(metadata['xesam:artist'][0], metadata['xesam:title']))
        # Find the Player instance in PlayerContainer and update only it
        for player_instance in self.player:
            if player_instance.player_name.get_name() == player.props.player_name:
                player_instance.on_metadata(manager, metadata, player)
                break