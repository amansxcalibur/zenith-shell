from fabric.utils import bulk_connect
from fabric.core.service import Service, Signal
from fabric import Fabricator

import gi
gi.require_version('Playerctl', '2.0')
from gi.repository import Playerctl, GLib

class PlayerService(Service):
    def __init__(self, player: Playerctl.Player, **kwargs):
        self._player: Playerctl.Player = player
        super().__init__(**kwargs)
        if player.props.player_name in ['vlc', 'cmus', 'firefox', 'spotify']:
            print("initing ", player.props.player_name) 
            
            self._player.connect('playback-status::playing', self.on_play)
            self._player.connect('playback-status::paused', self.on_pause)
            self._player.connect('shuffle', self.on_shuffle)
            self._player.connect('metadata', self.on_metadata)
            print(type(player))

    @Signal
    def shuffle_toggle(self, player: Playerctl.Player, status: bool) -> None: ...
    
    @Signal
    def meta_change(self, metadata: GLib.Variant, player: Playerctl.Player) -> None: ...

    @Signal
    def pause(self) -> None: ...

    @Signal
    def play(self) -> None: ...

    def on_play(self, player, status):
        print('player is playing: {}'.format(player.props.player_name))
        # weather_fabricator = Fabricator(
        #         interval=1000 * 60,  # 1min
        #         poll_from="curl https://wttr.in/?format=Weather+in+%l:+%t+(Feels+Like+%f),+%C+%c",
        #         on_changed=lambda f, v: print(v.strip()),
        #     )
        self.play()

    def on_pause(self, player, status):
        print('player is paused: {}'.format(player.props.player_name))
        self.pause()

    def on_shuffle(self, player, status):
        print("suffle status changed for: {}".format(player.props.player_name))
        print(type(status), "here is the status type")
        self.shuffle_toggle(player, status)

    def on_metadata(self, player, metadata):
        keys = metadata.keys()
        if 'xesam:artist' in keys and 'xesam:title' in keys:
            print('{} - {}'.format(metadata['xesam:artist'][0],
                                metadata['xesam:title']))
        self.meta_change(metadata, player)

class PlayerManager(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._manager = Playerctl.PlayerManager()
        self._manager.connect('name-appeared', self._on_name_appeared, self._manager)
        self._manager.connect('player-vanished', self._on_player_vanished, self._manager)
        # self.init_all_players()
        print("playerctl init done")

        self._players={}

    @Signal
    def new_player(self, player: Playerctl.Player) -> Playerctl.Player: ...

    @Signal
    def player_vanish(self, player: Playerctl.Player) -> None: ...

    def init_all_players(self):
        # invoked in the UI
        for player_obj in self._manager.props.player_names:
            name_str = player_obj.name
            print(f"{name_str} appeared")
            if name_str in ['vlc', 'cmus', 'firefox', 'spotify']:
                player = Playerctl.Player.new_from_name(player_obj)
                self._manager.manage_player(player)
                # player_instance = Player(player)
                # self._players[name_str] = player_instance
                self.new_player(player)

    def _on_name_appeared(self, sender, name, manager):
        name_str = name.name
        print(f"{name_str} appeared")
        if name_str in ['vlc', 'cmus', 'firefox', 'spotify']:
            player = Playerctl.Player.new_from_name(name)
            self._manager.manage_player(player)
            # player_instance = Player(player)
            # self._players[name_str] = player_instance
            self.new_player(player)


    def _on_player_vanished(self, sender, player, manager):
        print('player has exited: {}'.format(player.props.player_name))
        print(type(player))
        self.player_vanish(player)