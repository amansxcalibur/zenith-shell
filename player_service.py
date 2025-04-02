from fabric.utils import bulk_connect
from fabric.core.service import Service, Signal

import gi
gi.require_version('Playerctl', '2.0')
from gi.repository import Playerctl, GLib

class PlayerService(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._manager = Playerctl.PlayerManager()
        self._manager.connect('name-appeared', self.on_name_appeared)
        self._manager.connect('player-vanished', self.on_player_vanished)
        self.init_all_players()
        print("playerctl init done")

    def init_new_player(self, name):
        # choose if you want to manage the player based on the name
        if name.name in ['vlc', 'cmus', 'firefox', 'spotify']:
            player = Playerctl.Player.new_from_name(name)
            print("initing ", name.name)
            player.connect('playback-status::playing', self.on_play, self._manager)
            player.connect('metadata', self.on_metadata, self._manager)
            self._manager.manage_player(player)

    def init_all_players(self):
        for player_obj in self._manager.props.player_names:
            player = Playerctl.Player.new_from_name(player_obj)
            player.connect('playback-status::playing', self.on_play, self._manager)
            player.connect('metadata', self.on_metadata, self._manager)
            self._manager.manage_player(player)
            print("this",player_obj.name)

    def on_play(self, player, status, manager):
        print('player is playing: {}'.format(player.props.player_name))

    @Signal
    def meta_change(self, metadata: GLib.Variant) -> GLib.Variant:...

    def on_metadata(self, player, metadata, manager):
        keys = metadata.keys()
        # print("here is type brotha",type(metadata))
        if 'xesam:artist' in keys and 'xesam:title' in keys:
            print('{} - {}'.format(metadata['xesam:artist'][0],
                                metadata['xesam:title']))
        self.meta_change(metadata)

    def on_name_appeared(self, manager, name):
        print(name, "this appeated")
        self.init_new_player(name)


    def on_player_vanished(self, manager, player):
        print('player has exited: {}'.format(player.props.player_name))