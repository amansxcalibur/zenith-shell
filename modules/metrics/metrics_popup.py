import threading

from expressive_shapes.shapes import circle, cookie_12, sunny, very_sunny

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.stack import Stack
from fabric.widgets.overlay import Overlay

import icons

from services.metrics import IoRates, MetricsProvider, ProcessGroup
from services.power_profiles import power_profiles_service

from widgets.clipping_box import ClippingBox
from widgets.page_tabs import PageTabs
from widgets.graphs import (
    AnimatedBarGraph,
    CircularGraph,
    FillBar,
    LinearProgress,
    LoadShape,
    MirroredBarGraph,
    SegmentedBar,
)
from widgets.shapes.expressive.morphing_shapes import InteractiveMorphShape
from widgets.material_label import MaterialIconLabel, MaterialFontLabel

from gi.repository import GLib  # type: ignore

# bento dashboard
FULL_DASHBOARD = False

HISTORY_MIN = 5
HISTORY_MAX = AnimatedBarGraph.MAX_HISTORY
HISTORY_DEF = 30
RING_MARGIN_MAX = 22
USAGE_ALERT = 90  # percent
USAGE_ALERT_CLEAR = 80  # stays alerted until below this, so the shape doesn't flicker
TEMP_WARM = 70  # celsius
TEMP_ALERT = 90  # celsius

# bento grid, px; rows are ROW_HEIGHT plus a STRIP_HEIGHT info strip
COLUMN_LEFT = 230
COLUMN_MIDDLE = 350
COLUMN_RIGHT = 270
ROW_HEIGHT = 230
TILE_GAP = 8
SECTION_GAP = 10
COMPACT_GRAPH_HEIGHT = 110
PAGE_TRANSITION_MS = 250
GRAPH_HEADER_HEIGHT = 40  # px kept clear of bars, so they never run behind the header

BADGE_SIZE = 36
BAR_SIZE = (20, 18)

PROCESS_ROWS = 7
PROCESS_REFRESH_SECONDS = 2
CPU_BAR_FLOOR = 2  # percent; below this nothing is busy enough to fill a whole row


def format_bytes(value: float) -> str:
    for unit in ("B", "KB"):
        if value < 1024:
            return f"{value:.0f} {unit}"
        value /= 1024
    if value < 1024:
        return f"{value:.1f} MB" if value < 100 else f"{value:.0f} MB"
    return f"{value / 1024:.1f} GB"


def format_gb_ratio(used: float, total: float) -> str:
    used, total = used / 1024**3, total / 1024**3
    decimals = 1 if total < 100 else 0
    return f"{used:.{decimals}f} / {total:.{decimals}f} GB"


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def _set_class(widget, name: str, active: bool) -> None:
    context = widget.get_style_context()
    (context.add_class if active else context.remove_class)(name)


class ProcessRow(Overlay):
    def __init__(self):
        self.fill = FillBar()
        self.name_label = Label(
            label="",
            ellipsization="end",
            max_chars_width=14,
            h_expand=True,
            h_align="start",
        )
        self.count_label = Label(label="", style_classes="metrics-graph-detail")
        self.value_label = Label(label="", style_classes="metrics-graph-value")
        super().__init__(
            size=(-1, 30),
            child=self.fill,
            overlays=[
                Box(
                    style="padding: 0 10px;",
                    spacing=6,
                    children=[self.name_label, self.count_label, self.value_label],
                )
            ],
        )

    def show_group(self, group: ProcessGroup | None, fraction: float, value: str):
        self.name_label.set_label(group.name if group else "")
        self.count_label.set_label(
            f"×{group.count}" if group and group.count > 1 else ""
        )
        self.value_label.set_label(value)
        self.fill.set_fraction(fraction)
        self.set_tooltip_text(
            f"{group.name}\n{group.count} process(es) · {group.cpu:.1f}% CPU · "
            f"{format_bytes(group.rss)}"
            if group
            else None
        )


class Metrics(Box):
    def __init__(self, **kwargs):
        super().__init__(name="metrics", spacing=SECTION_GAP, orientation="v", **kwargs)

        self.service = MetricsProvider()
        self._ring_disk = None  # disk % the rings were last styled for
        self._rates = IoRates()
        self._cpu_hot = False
        self._page_stacks: list[Stack] = []
        self._page = "memory"
        self.page_tabs = None

        self._process_groups: list[ProcessGroup] = []
        self._process_key = "cpu"
        self._process_pending = False
        self._process_countdown = 0

        self._build_widgets()
        self._build_layout()

        self.cpu_name_label.set_label(self.service.cpu_brand)
        self._animated_widgets = [
            self.cpu_graph,
            self.mem_graph,
            self.net_graph,
            self.load_shape,
        ]
        self._sync_power_profile()
        power_profiles_service.connect("changed", self._sync_power_profile)

        self.connect("map", self._on_map)
        GLib.timeout_add_seconds(1, self._update_ui)

    def _sync_power_profile(self, *_) -> None:
        animated = power_profiles_service.active_profile != "power-saver"
        for widget in self._animated_widgets:
            widget.set_animated(animated)
        for stack in self._page_stacks:
            stack.set_transition_duration(PAGE_TRANSITION_MS if animated else 0)
        if self.page_tabs:
            self.page_tabs.set_animated(animated)

    def _build_widgets(self):
        cores, threads = self.service.get_cpu_counts()
        self._threads = threads

        self.cpu_graph = AnimatedBarGraph(
            HISTORY_DEF, top_inset=GRAPH_HEADER_HEIGHT, size=(COLUMN_MIDDLE, ROW_HEIGHT)
        )
        self.mem_graph = AnimatedBarGraph(
            HISTORY_DEF, top_inset=GRAPH_HEADER_HEIGHT, size=(COLUMN_MIDDLE, 160)
        )
        self.net_graph = MirroredBarGraph(
            format_value=lambda v: f"{format_bytes(v)}/s",
            history_seconds=HISTORY_DEF,
            top_inset=GRAPH_HEADER_HEIGHT + 20,
            size=(COLUMN_RIGHT, -1),
        )
        self.net_graph.set_vexpand(True)
        self.cpu_circular_graph = CircularGraph(bar_count=threads)
        self.load_shape = LoadShape(cookie_12, very_sunny)

        self.cpu_label = MaterialFontLabel(
            text="--",
            v_align="center",
            style_classes="metrics-main-label",
            font_family="Google Sans Flex",
        )
        self.disk_label = MaterialFontLabel(
            text="--",
            style_classes="metrics-main-label",
            font_family="Google Sans Flex",
        )
        self.disk_ratio_label = Label(label="-- / --", style_classes="metrics-sub-text")
        self.cores = Label(
            label=f"{cores}C · {threads}T",
            style_classes="metrics-sub-text",
            tooltip_text=f"{cores} cores, {threads} threads",
        )
        self.cpu_name_label = Label(
            label="--",
            style_classes=["roboto", "metrics-cpu-name"],
            ellipsization="end",
            max_chars_width=20,
            h_expand=True,
        )
        self.cpu_name_label.set_xalign(0)
        self.cpu_name_label.set_tooltip_text(self.service.cpu_brand)

        self.cpu_temp_label = Label(label="--", style_classes="roboto")
        self.temp_icon, self.temp_shape = self._make_badge(
            icons.device_thermostat.symbol()
        )
        self.temp_state_label = self._make_tile_caption()
        self.load_now_label = Label(
            label="--",
            style_classes="roboto",
            tooltip_text=(
                "Threads running or waiting to run, averaged over the last minute. "
                f"Above {threads}, work is queuing up."
            ),
        )
        self.load_trend_label = self._make_tile_caption()

        self.cpu_value_label = Label(style_classes="metrics-graph-value", label="--")
        self.mem_value_label = Label(style_classes="metrics-graph-value", label="--")
        self.cpu_split_label = Label(label="", style_classes="metrics-graph-detail")
        # capped: the popup's width must not change with the numbers
        self.mem_ratio_label = Label(
            label="",
            style_classes="metrics-graph-detail",
            ellipsization="end",
            max_chars_width=13,
        )
        self.cpu_panel_icon = MaterialIconLabel(
            icon_text=icons.cpu.symbol(), font_size=14
        )
        self.mem_panel_icon = MaterialIconLabel(
            icon_text=icons.memory.symbol(), font_size=14
        )

        self.freq_bar = LinearProgress(size=BAR_SIZE)
        self.freq_bar.set_hexpand(True)
        self.freq_label = Label(label="--", style_classes="roboto")
        self.load_label = Label(
            label="--",
            style_classes="roboto",
            tooltip_text="Load average over 1, 5 and 15 minutes",
            ellipsization="end",
            max_chars_width=15,
        )

        self.mem_bar = SegmentedBar()
        self.mem_used_label = Label(label="--", style_classes="metrics-legend")
        self.mem_cache_label = Label(label="--", style_classes="metrics-legend")
        self.mem_free_label = Label(label="--", style_classes="metrics-legend")

        self.swap_bar = LinearProgress(size=BAR_SIZE)
        self.swap_bar.set_hexpand(True)
        self.swap_label = Label(
            label="--", style_classes="roboto", ellipsization="end", max_chars_width=14
        )

        self.disk_read_label = Label(label="--", style_classes="roboto")
        self.disk_write_label = Label(label="--", style_classes="roboto")
        self.net_down_label = Label(label="--", style_classes="metrics-legend")
        self.net_up_label = Label(label="--", style_classes="metrics-legend")
        self.net_peak_label = Label(
            label="", style_classes="metrics-graph-detail", h_align="end"
        )

        self.uptime_label = Label(label="--", style_classes="roboto")
        self.tasks_label = Label(label="--", style_classes="roboto")

        self.process_rows = [ProcessRow() for _ in range(PROCESS_ROWS)]
        self.sort_buttons = {
            "cpu": self._make_sort_button("CPU", "cpu"),
            "rss": self._make_sort_button("RAM", "rss"),
        }
        self.sort_buttons["cpu"].add_style_class("active")

    @staticmethod
    def _make_tile_caption() -> Label:
        """Sits where a tile's bar would be, at the same height."""
        caption = Label(
            label="--",
            style_classes="metrics-stat-name",
            size=(-1, BAR_SIZE[1]),
            h_align="start",
        )
        caption.set_xalign(0)
        return caption

    @staticmethod
    def _make_badge(icon: str) -> tuple[Overlay, InteractiveMorphShape]:
        """Icon on a round backdrop; the shape can morph (see `is_active`)."""
        shape = InteractiveMorphShape(
            name="metrics-stat-shape", shape_start=circle, shape_end=sunny
        )
        # it asks to expand by default, which would stretch the badge along its row
        shape.set_hexpand(False)
        shape.set_vexpand(False)
        badge = Overlay(
            size=(BADGE_SIZE, BADGE_SIZE),
            v_align="center",
            child=shape,
            overlays=[MaterialIconLabel(icon_text=icon, font_size=15)],
        )
        return badge, shape

    def _make_sort_button(self, label: str, key: str) -> Button:
        button = Button(
            label=label,
            style_classes="metrics-sort",
            on_clicked=lambda *_: self._set_process_key(key),
        )
        button.set_can_focus(False)
        return button

    def _make_history_slider(self, width: int = -1) -> Box:
        slider = Scale(
            name="slider-mui",
            style_classes="metrics-popup",
            orientation="h",
            h_expand=True,
            increments=(1, 1),
            min_value=HISTORY_MIN,
            max_value=HISTORY_MAX,
            value=HISTORY_DEF,
            tooltip_text="Seconds of history shown in the CPU, memory and network graphs",
        )
        value_label = Label(
            label=f"{HISTORY_DEF}s", style_classes="metrics-graph-value"
        )

        def _on_change(scale):
            seconds = int(scale.get_value())
            for graph in (self.cpu_graph, self.mem_graph, self.net_graph):
                graph.set_history(seconds)
            value_label.set_label(f"{seconds}s")

        slider.connect("value-changed", _on_change)
        return Box(
            size=(width, -1),
            spacing=8,
            children=[
                MaterialIconLabel(icon_text=icons.history.symbol(), font_size=14),
                slider,
                value_label,
            ],
        )

    @staticmethod
    def _ring_style(margin: float) -> str:
        return f"padding:{2 * margin:.1f}px {margin:.1f}px 0 {margin:.1f}px; border-radius: 999px"

    @staticmethod
    def _strip(*children, **kwargs) -> Box:
        return Box(
            style_classes="metrics-desc-box",
            spacing=8,
            children=list(children),
            **kwargs,
        )

    @staticmethod
    def _stat(icon, label: Label, **kwargs) -> Box:
        return Box(
            spacing=3,
            children=[MaterialIconLabel(icon_text=icon, font_size=13), label],
            **kwargs,
        )

    @staticmethod
    def _legend_item(dot_class: str, label: Label) -> Box:
        return Box(
            spacing=5,
            children=[
                Box(style_classes=["metrics-dot", dot_class], v_align="center"),
                label,
            ],
        )

    @staticmethod
    def _graph_panel(
        graph, icon: Label, title: str, value=None, detail=None, footer=None
    ):
        header = Box(
            style="padding: 10px;",
            v_align="start",
            spacing=6,
            children=[
                icon,
                Label(label=title, h_align="start", h_expand=True),
                *([detail] if detail else []),
                *([value] if value else []),
            ],
        )
        body = Box(orientation="v", v_expand=True, children=[graph])
        if footer:
            body.add(footer)
        return Overlay(
            name="metric-graph-container",
            child=ClippingBox(
                style="background-color: var(--shadow); border-radius: 20px",
                v_expand=True,
                children=body,
            ),
            overlays=[header],
        )

    def _build_cpu_radial(self) -> ClippingBox:
        self.cpu_title = Box(
            style_classes="metrics-sub-text",
            h_align="center",
            spacing=4,
            children=[
                MaterialIconLabel(icon_text=icons.cpu.symbol()),
                Label(label="CPU"),
            ],
        )
        return ClippingBox(
            size=(COLUMN_LEFT, ROW_HEIGHT),
            v_align="center",
            style="background-color: var(--shadow); border-radius: 999px",
            children=Overlay(
                h_expand=True,
                child=self.load_shape,
                overlays=[
                    self.cpu_circular_graph,
                    Box(
                        h_align="center",
                        v_align="center",
                        orientation="v",
                        children=[
                            self.cpu_title,
                            Box(h_align="center", children=[self.cpu_label]),
                            self.cores,
                        ],
                    ),
                ],
            ),
        )

    def _build_disk_rings(self) -> Box:
        m = RING_MARGIN_MAX
        disk_core = Box(
            h_expand=True,
            style_classes=["metrics-storage-circle", "active"],
            style="border-radius: 999px",
            children=Box(
                h_expand=True,
                v_align="center",
                orientation="v",
                children=[
                    Box(
                        style_classes="metrics-sub-text",
                        h_align="center",
                        spacing=4,
                        children=[
                            MaterialIconLabel(icon_text=icons.disk.symbol()),
                            Label(label="Disk"),
                        ],
                    ),
                    self.disk_label,
                    self.disk_ratio_label,
                ],
            ),
        )
        # three concentric ring boxes
        self.ring_3 = Box(
            h_expand=True,
            style_classes="metrics-storage-circle",
            style=self._ring_style(m),
            children=disk_core,
        )
        self.ring_2 = Box(
            h_expand=True,
            style_classes="metrics-storage-circle",
            style=self._ring_style(m),
            children=self.ring_3,
        )
        self.ring_1 = Box(
            size=(COLUMN_LEFT, ROW_HEIGHT),
            style_classes="metrics-storage-circle",
            style=self._ring_style(m),
            children=self.ring_2,
        )
        return self.ring_1

    def _build_process_panel(self) -> Box:
        return Box(
            name="metrics-process-panel",
            size=(COLUMN_RIGHT, -1),
            orientation="v",
            v_expand=True,
            spacing=4,
            children=[
                Box(
                    spacing=4,
                    style="margin-bottom: 4px;",
                    children=[
                        MaterialIconLabel(
                            icon_text=icons.leaderboard.symbol(), font_size=14
                        ),
                        Label(label="Top", h_align="start", h_expand=True),
                        *self.sort_buttons.values(),
                    ],
                ),
                *self.process_rows,
            ],
        )

    def _memory_legend(self) -> Box:
        return Box(
            spacing=10,
            h_align="center",
            children=[
                self._legend_item("used", self.mem_used_label),
                self._legend_item("cache", self.mem_cache_label),
                self._legend_item("free", self.mem_free_label),
            ],
        )

    def _network_legend(self) -> Box:
        return Box(
            spacing=12,
            h_align="center",
            children=[
                self._legend_item("down", self.net_down_label),
                self._legend_item("up", self.net_up_label),
            ],
        )

    def _build_memory_footer(self) -> Box:
        return Box(
            orientation="v",
            spacing=10,
            style="padding: 8px 12px 12px 12px;",
            v_align="end",
            v_expand=True,
            children=[self.mem_bar, self._memory_legend()],
        )

    def _build_network_panel(self) -> Overlay:
        panel = self._graph_panel(
            self.net_graph,
            MaterialIconLabel(icon_text=icons.lan.symbol(), font_size=14),
            "Network",
            detail=self.net_peak_label,
        )
        panel.add_overlay(
            Box(
                style="padding: 34px 10px 0 10px;",
                v_align="start",
                h_align="start",
                children=[self._network_legend()],
            )
        )
        return panel

    def _build_layout(self):
        if FULL_DASHBOARD:
            self._build_dashboard_layout()
        else:
            self._build_compact_layout()

    def _build_compact_layout(self):
        """Two circles over one paged card: only one graph on screen at a time."""
        for graph in (self.mem_graph, self.net_graph):
            graph.top_inset = 0
            graph.set_size_request(-1, COMPACT_GRAPH_HEIGHT)
            graph.set_vexpand(True)

        self.page_tabs = PageTabs(
            [
                ("memory", self.mem_panel_icon, "Memory"),
                (
                    "network",
                    MaterialIconLabel(icon_text=icons.lan.symbol(), font_size=14),
                    "Network",
                ),
                (
                    "details",
                    MaterialIconLabel(
                        icon_text=icons.monitoring.symbol(), font_size=14
                    ),
                    "Details",
                ),
            ],
            on_change=self._show_page,
        )

        self.page_stack = Stack(
            transition_type="slide-left-right",
            transition_duration=PAGE_TRANSITION_MS,
            v_expand=True,
        )
        self.page_stack.add_named(
            Box(
                orientation="v",
                spacing=8,
                children=[self.mem_graph, self.mem_bar, self._memory_legend()],
            ),
            "memory",
        )
        self.page_stack.add_named(
            Box(
                orientation="v",
                spacing=8,
                children=[self.net_graph, self._network_legend()],
            ),
            "network",
        )
        self.page_stack.add_named(self._build_details_page(), "details")

        self.summary_stack = Stack(
            transition_type="crossfade",
            transition_duration=PAGE_TRANSITION_MS,
            h_expand=True,
            h_align="end",
        )
        self.summary_stack.add_named(
            Box(
                h_align="end",
                spacing=6,
                children=[self.mem_ratio_label, self.mem_value_label],
            ),
            "memory",
        )
        self.summary_stack.add_named(self.net_peak_label, "network")
        self.summary_stack.add_named(Box(), "details")

        # the history slider has nothing to act on while Details is showing
        self.footer_stack = Stack(
            transition_type="crossfade", transition_duration=PAGE_TRANSITION_MS
        )
        self.footer_stack.add_named(self._make_history_slider(), "graphs")
        self.cpu_name_label.get_style_context().remove_class("metrics-cpu-name")
        self.footer_stack.add_named(
            Box(
                style_classes="metrics-tile",
                spacing=12,
                children=[
                    self.cpu_name_label,
                    self._stat(icons.schedule.symbol(), self.uptime_label),
                    self._stat(icons.apps.symbol(), self.tasks_label),
                ],
            ),
            "details",
        )
        self._page_stacks = [self.page_stack, self.summary_stack, self.footer_stack]
        self._show_page(self._page)

        self.children = [
            Box(
                spacing=SECTION_GAP,
                children=[self._build_cpu_radial(), self._build_disk_rings()],
            ),
            Box(
                name="metrics-card",
                orientation="v",
                spacing=8,
                children=[
                    Box(
                        spacing=8,
                        children=[
                            Box(name="metrics-page-tabs", children=self.page_tabs),
                            self.summary_stack,
                        ],
                    ),
                    self.page_stack,
                    self.footer_stack,
                ],
            ),
        ]

    def _build_details_page(self) -> Box:
        def tile(badge, title: str, value: Label, footer) -> Box:
            value.add_style_class("metrics-tile-value")
            value.set_xalign(0)
            return Box(
                style_classes="metrics-tile",
                h_expand=True,
                children=Box(
                    orientation="v",
                    spacing=6,
                    h_expand=True,
                    v_expand=True,
                    v_align="center",
                    children=[
                        Box(
                            spacing=10,
                            children=[
                                badge,
                                Box(
                                    orientation="v",
                                    v_align="center",
                                    children=[
                                        Label(
                                            label=title,
                                            style_classes="metrics-stat-name",
                                            h_align="start",
                                        ),
                                        value,
                                    ],
                                ),
                            ],
                        ),
                        footer,
                    ],
                ),
            )

        def tile_row(*tiles) -> Box:
            row = Box(spacing=TILE_GAP, v_expand=True, children=list(tiles))
            row.set_homogeneous(True)
            return row

        return Box(
            orientation="v",
            spacing=TILE_GAP,
            children=[
                tile_row(
                    tile(
                        self.temp_icon,
                        "Temperature",
                        self.cpu_temp_label,
                        self.temp_state_label,
                    ),
                    tile(
                        self._make_badge(icons.speed.symbol())[0],
                        "Speed",
                        self.freq_label,
                        self.freq_bar,
                    ),
                ),
                tile_row(
                    tile(
                        self._make_badge(icons.leaderboard.symbol())[0],
                        f"Load · {self._threads} threads",
                        self.load_now_label,
                        self.load_trend_label,
                    ),
                    tile(
                        self._make_badge(icons.swap_vert.symbol())[0],
                        "Swap",
                        self.swap_label,
                        self.swap_bar,
                    ),
                ),
            ],
        )

    def _show_page(self, page: str) -> None:
        self._page = page
        self.page_stack.set_visible_child_name(page)
        self.summary_stack.set_visible_child_name(page)
        self.footer_stack.set_visible_child_name(
            "details" if page == "details" else "graphs"
        )
        self.page_tabs.set_page(page)

        if self.get_mapped() and self._details_active():
            self._update_details(self.service.get_metrics()[0])

    def _details_active(self) -> bool:
        return FULL_DASHBOARD or self._page == "details"

    def _build_dashboard_layout(self):
        left_top = Box(
            orientation="v",
            spacing=TILE_GAP,
            children=[
                self._build_cpu_radial(),
                self._strip(
                    self.cpu_name_label,
                    self.temp_icon,
                    self.cpu_temp_label,
                    v_expand=True,
                ),
            ],
        )
        middle_top = Box(
            orientation="v",
            spacing=TILE_GAP,
            children=[
                self._graph_panel(
                    self.cpu_graph,
                    self.cpu_panel_icon,
                    "CPU",
                    value=self.cpu_value_label,
                    detail=self.cpu_split_label,
                ),
                self._strip(
                    MaterialIconLabel(icon_text=icons.speed.symbol(), font_size=14),
                    self.freq_bar,
                    self.freq_label,
                    self._stat(icons.monitoring.symbol(), self.load_label),
                    v_expand=True,
                ),
            ],
        )
        left_bottom = Box(
            orientation="v",
            spacing=TILE_GAP,
            children=[
                self._build_disk_rings(),
                self._strip(
                    self._stat(
                        icons.south.symbol(),
                        self.disk_read_label,
                        h_expand=True,
                        tooltip_text="Disk read",
                    ),
                    self._stat(
                        icons.north.symbol(),
                        self.disk_write_label,
                        tooltip_text="Disk write",
                    ),
                    v_expand=True,
                ),
            ],
        )
        middle_bottom = Box(
            orientation="v",
            spacing=TILE_GAP,
            children=[
                self._graph_panel(
                    self.mem_graph,
                    self.mem_panel_icon,
                    "Memory",
                    value=self.mem_value_label,
                    detail=self.mem_ratio_label,
                    footer=self._build_memory_footer(),
                ),
                self._strip(
                    MaterialIconLabel(icon_text=icons.swap_vert.symbol(), font_size=14),
                    Label(label="Swap", style_classes="roboto"),
                    self.swap_bar,
                    self.swap_label,
                    v_expand=True,
                ),
            ],
        )

        self.children = [
            self._strip(
                self._stat(icons.schedule.symbol(), self.uptime_label),
                self._stat(icons.apps.symbol(), self.tasks_label),
                Box(h_expand=True),
                self._make_history_slider(COLUMN_MIDDLE + COLUMN_RIGHT + SECTION_GAP),
            ),
            Box(
                spacing=SECTION_GAP,
                children=[left_top, middle_top, self._build_process_panel()],
            ),
            Box(
                spacing=SECTION_GAP,
                children=[left_bottom, middle_bottom, self._build_network_panel()],
            ),
        ]

    def _on_map(self, *_) -> None:
        self._update_visible()
        if FULL_DASHBOARD:
            self._refresh_processes()

    def _update_ui(self) -> bool:
        cpu, mem, _ = self.service.get_metrics()
        self._rates = self.service.get_io_rates()

        # graphs keep sampling while hidden so their history has no gaps
        if FULL_DASHBOARD:
            self.cpu_graph.add_value(cpu)
        self.mem_graph.add_value(mem)
        self.net_graph.add_value(self._rates.net_down, self._rates.net_up)

        if self.get_mapped():
            self._update_visible()
            # not part of _update_visible: these measure since the previous call,
            # so an extra sample on map could span mere milliseconds
            self.cpu_circular_graph._update_targets(self.service.get_per_cpu_usage())
            if FULL_DASHBOARD:
                user, system, iowait = self.service.get_cpu_time_split()
                self.cpu_split_label.set_label(
                    f"usr {user:.0f} · sys {system:.0f} · io {iowait:.0f}"
                )

                self._process_countdown -= 1
                if self._process_countdown <= 0:
                    self._refresh_processes()

        return True

    def _update_visible(self) -> None:
        """Refresh everything that's only worth computing while on screen."""
        cpu, mem, disk = self.service.get_metrics()

        self._update_cpu(cpu)
        self._update_memory(mem)
        self._update_disk(disk)

        self.net_down_label.set_label(f"Down {format_bytes(self._rates.net_down)}/s")
        self.net_up_label.set_label(f"Up {format_bytes(self._rates.net_up)}/s")
        self.net_peak_label.set_label(f"peak {format_bytes(self.net_graph.peak)}/s")

        if self._details_active():
            self._update_details(cpu)

    def _update_details(self, cpu: float) -> None:
        """Stats on the Details page and the full dashboard; costs nothing elsewhere."""
        self.cpu_value_label.set_label(f"{cpu:.0f}%")
        self._set_panel_alert(self.cpu_panel_icon, icons.cpu.symbol(), self._cpu_hot)

        self.uptime_label.set_label(format_duration(self.service.get_uptime()))
        self.tasks_label.set_label(f"{self.service.get_task_count()} tasks")

        temp = self.service.get_cpu_temp()
        self.cpu_temp_label.set_label("N/A" if temp is None else f"{temp:.0f}°C")
        self.temp_state_label.set_label(self._temp_state(temp))
        too_hot = temp is not None and temp >= TEMP_ALERT
        self.temp_shape.is_active = too_hot
        _set_class(self.temp_shape, "alert", too_hot)

        freq = self.service.get_cpu_freq()
        self.freq_bar.set_fraction(freq[0] / freq[1] if freq else 0)
        self.freq_label.set_label(f"{freq[0] / 1000:.1f} GHz" if freq else "N/A")

        load = self.service.get_load_avg()
        self.load_label.set_label(" ".join(f"{value:.2f}" for value in load))
        self.load_now_label.set_label(f"{load[0]:.2f}")
        self.load_trend_label.set_label(f"5 min {load[1]:.2f} · 15 min {load[2]:.2f}")

        swap_used, swap_total = self.service.get_swap()
        self.swap_bar.set_fraction(swap_used / swap_total if swap_total else 0)
        self.swap_label.set_label(
            format_gb_ratio(swap_used, swap_total) if swap_total else "Off"
        )

        self.disk_read_label.set_label(f"{format_bytes(self._rates.disk_read)}/s")
        self.disk_write_label.set_label(f"{format_bytes(self._rates.disk_write)}/s")

    @staticmethod
    def _temp_state(temp: float | None) -> str:
        if temp is None:
            return "No sensor"
        if temp >= TEMP_ALERT:
            return "Hot"
        return "Warm" if temp >= TEMP_WARM else "Normal"

    def _update_cpu(self, cpu: float) -> None:
        self.cpu_label.set_label(f"{cpu:.0f}%")
        # expressive type: the headline gets heavier as the machine works harder
        self.cpu_label.set_variations(wght=300 + 100 * round(cpu / 100 * 5))

        hot = cpu >= (USAGE_ALERT_CLEAR if self._cpu_hot else USAGE_ALERT)
        self._cpu_hot = hot
        self.load_shape.set_load(cpu / 100, hot)
        _set_class(self.load_shape, "alert", hot)
        _set_class(self.cpu_label, "alert", hot)
        _set_class(self.cores, "alert", hot)
        _set_class(self.cpu_title, "alert", hot)

    def _update_memory(self, mem: float) -> None:
        self.mem_value_label.set_label(f"{mem:.0f}%")
        self._set_panel_alert(
            self.mem_panel_icon, icons.memory.symbol(), mem >= USAGE_ALERT
        )

        used, cache, free, total = self.service.get_mem_breakdown()
        self.mem_ratio_label.set_label(format_gb_ratio(used, total))
        self.mem_bar.set_segments(
            [
                (used / total, "primary", 1.0),
                (cache / total, "primary", 0.45),
                (free / total, "surface-bright", 1.0),
            ]
        )
        self.mem_used_label.set_label(f"Used {format_bytes(used)}")
        self.mem_cache_label.set_label(f"Cache {format_bytes(cache)}")
        self.mem_free_label.set_label(f"Free {format_bytes(free)}")

    def _update_disk(self, disk: float) -> None:
        self.disk_label.set_label(f"{disk:.0f}%")
        used, total = self.service.get_disk_usage_gb()
        self.disk_ratio_label.set_label(f"{used:.0f} / {total:.0f} GB")

        if disk != self._ring_disk:
            self._ring_disk = disk
            margin = (1 - (disk / 100) ** 3) * RING_MARGIN_MAX
            style = self._ring_style(margin)
            for ring in (self.ring_1, self.ring_2, self.ring_3):
                ring.set_style(style)

    @staticmethod
    def _set_panel_alert(icon: MaterialIconLabel, normal_symbol: str, alert: bool):
        """Alerts are never color alone: the panel's icon becomes a warning sign."""
        icon.set_icon(icons.warning.symbol() if alert else normal_symbol)
        _set_class(icon, "metrics-alert-icon", alert)

    def _set_process_key(self, key: str) -> None:
        self._process_key = key
        for button_key, button in self.sort_buttons.items():
            _set_class(button, "active", button_key == key)
        self._show_processes()

    def _refresh_processes(self) -> None:
        self._process_countdown = PROCESS_REFRESH_SECONDS
        if self._process_pending:
            return
        self._process_pending = True

        def worker():
            groups = self.service.get_process_groups()
            GLib.idle_add(self._on_processes, groups)

        threading.Thread(target=worker, daemon=True).start()

    def _on_processes(self, groups: list[ProcessGroup]) -> bool:
        self._process_pending = False
        self._process_groups = groups
        self._show_processes()
        return False

    def _show_processes(self) -> None:
        key = self._process_key
        # ties fall back to memory: the first CPU sample after opening is all zeros
        top = sorted(
            self._process_groups, key=lambda g: (getattr(g, key), g.rss), reverse=True
        )[: len(self.process_rows)]
        # bars rank the rows against the leader; the text carries the actual value
        peak_cpu = max(top[0].cpu, CPU_BAR_FLOOR) if top else 0
        peak_rss = top[0].rss if top else 0

        for index, row in enumerate(self.process_rows):
            group = top[index] if index < len(top) else None
            if group is None:
                row.show_group(None, 0, "")
            elif key == "cpu":
                row.show_group(group, group.cpu / peak_cpu, f"{group.cpu:.1f}%")
            else:
                row.show_group(
                    group, group.rss / max(peak_rss, 1), format_bytes(group.rss)
                )
