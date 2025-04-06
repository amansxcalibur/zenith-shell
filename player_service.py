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
            self._player.connect('seeked', self.on_seeked)
            print(type(player))

        self.status = self._player.props.playback_status
        self.weather_fabricator = Fabricator(
                interval=1000 * 60,  # 1min
                poll_from=lambda f, *_: self._player.get_position(),
                on_changed=lambda f, *_: self.fabricating,
            )
        self.poll_progress()
        # print(self.status, "player is now faksfalsdkfja;sdlkfja;sldkfja;sdlkf")

    @Signal
    def shuffle_toggle(self, player: Playerctl.Player, status: bool) -> None: ...
    
    @Signal
    def meta_change(self, metadata: GLib.Variant, player: Playerctl.Player) -> None: ...

    @Signal
    def pause(self) -> None: ...

    @Signal
    def play(self) -> None: ...

    @Signal
    def track_position(self, pos: float, dur: float) -> None: ...

    def on_seeked(self, player, position):
        if self.status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
            self.weather_fabricator.start()

    def set_position(self, pos: float):
        print("seeking in the service")
        self.weather_fabricator.stop()
        micro_pos = int(pos * 1_000_000)
        try:
            self._player.set_position(micro_pos)
            print(f"Set position to {micro_pos}")
        except GLib.Error as e:
            print(f"Failed to seek: {e}")

    def poll_progress(self):
        if self.status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
            self.weather_fabricator = Fabricator(
                interval=1000,  # 1s
                poll_from=lambda f, *_: self._player.get_position(),
                on_changed=lambda f, *_: self.fabricating(),
            )
            self.weather_fabricator.start()
        else:
            self.weather_fabricator.stop()
            
    def fabricating(self):
        pos = self._player.get_position() / 1_000_000  # seconds
        dur = self._player.props.metadata["mpris:length"] / 1_000_000  # seconds
        print(self._player.get_position())
        # print(f"[progress] {pos:.2f}s / {dur:.2f}s")
        self.track_position(pos, dur)

    def on_play(self, player, status):
        print('player is playing: {}'.format(player.props.player_name))
        self.status = player.props.playback_status
        self.poll_progress()
        self.play()

    def on_pause(self, player, status):
        print('player is paused: {}'.format(player.props.player_name))
        self.status = player.props.playback_status
        self.poll_progress()
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