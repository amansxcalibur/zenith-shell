from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.image import Image

from player_service import PlayerService
import icons.icons as icons
import os

class Player(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="player",
            orientation="v",
            **kwargs)
        
        self.manager = PlayerService()
        self.manager.connect("meta-change", self.on_metadata)
        
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

        self.children = [
            Box(name="source", h_expand=True, v_expand=True),
            # self.image,
            CenterBox(
                name="details", 
                # h_expand=True, 
                # v_expand=True,
                start_children=self.music,
                end_children=Button(
                    name="pause-button",
                    child=Label(name="pause-label", markup=icons.pause),
                    tooltip_text="Exit",
                    # on_clicked=lambda *_: self.close_launcher()
                ),
            ),
            Box(name="controls", 
                # h_expand=True, 
                # v_expand=True,
                spacing=20,
                children=[
                    Label(name="play-previous", markup=icons.previous),
                    CenterBox(
                        name="progress-container",
                        h_expand=True,
                        v_expand=False,
                        orientation='v',
                        center_children=Box(name="progress")
                    ),
                    Label(name="play-next", markup=icons.next),
                    Label(name="shuffle", markup=icons.shuffle),
                ]
            )
        ]
    def on_metadata(self, manager, metadata):
        keys = metadata.keys()
        if 'xesam:artist' in keys and 'xesam:title' in keys:
            self.song.set_label(metadata['xesam:title'])
            self.artist.set_label(metadata['xesam:artist'][0])