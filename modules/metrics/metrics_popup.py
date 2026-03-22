import psutil

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.overlay import Overlay

from widgets.clipping_box import ClippingBox
from widgets.graphs import AnimatedBarGraph, CircularGraph
from widgets.material_label import MaterialIconLabel, MaterialFontLabel
from services.metrics import MetricsProvider

import icons as icons

from expressive_shapes.shapes import cookie_12
from widgets.shapes.expressive.morphing_shapes import ExpressiveShape

from gi.repository import GLib

HISTORY_MIN = 5
HISTORY_MAX = 120
HISTORY_DEF = 30
RING_MARGIN_MAX = 25


class Metrics(Box):
    def __init__(self, **kwargs):
        super().__init__(name="metrics", spacing=10, orientation="v", **kwargs)

        self.service = MetricsProvider()

        self._build_widgets()
        self._build_layout()

        self.cpu_name_label.set_label(self.service.cpu_brand)
        GLib.timeout_add_seconds(1, self._update_ui)
        GLib.timeout_add_seconds(
            1,
            lambda: self.cpu_circular_graph._update_targets(psutil.cpu_percent(percpu=True)),
        )

    def _build_widgets(self):
        self.cpu_graph = AnimatedBarGraph(bar_width=4, color="#3498db", history_seconds=HISTORY_DEF)
        self.mem_graph = AnimatedBarGraph(bar_width=4, color="#2ecc71", history_seconds=HISTORY_DEF)
        self.cpu_circular_graph = CircularGraph(bar_count=psutil.cpu_count())

        self.cpu_label = MaterialFontLabel(
            text="--", v_align="center", style="font-size: 30px;", font_family="Google Sans Flex",
        )
        self.disk_label = MaterialFontLabel(
            text="--", style_classes="roboto", style="font-size: 30px",
            font_family="Google Sans Flex", h_expand=True, v_expand=True,
        )
        self.cores = Label(label=f"{psutil.cpu_count()} cores", style_classes="metrics-sub-text")
        self.cpu_name_label = Label(
            label="--", style_classes="roboto", ellipsization="end",
            max_chars_width=18, h_expand=True,
        )
        self.cpu_temp_label = Label(label="--", style_classes="roboto")
        self.disk_ratio_label = Label(
            label="-- / --", style_classes="roboto", h_expand=True, v_align="center",
        )
        self.mem_ratio_label = Label(
            label="-- / --", style_classes="roboto", h_expand=True,
            v_align="center", h_align="start",
        )

    def _make_history_slider(self, graph: AnimatedBarGraph) -> Box:
        slider = Scale(
            name="slider-mui", orientation="h", h_expand=True,
            increments=(1, 1), min_value=HISTORY_MIN, max_value=HISTORY_MAX, value=HISTORY_DEF,
        )
        curr_val_label = Label(label=f"{HISTORY_DEF}s")

        def _on_change(scale):
            graph.set_history(int(scale.get_value()))
            curr_val_label.set_label(f"{int(scale.get_value())}s")

        slider.connect("value-changed", _on_change)
        return Box(style_classes="metrics-desc-box", spacing=8, children=[slider, curr_val_label])

    @staticmethod
    def _ring_style(margin: float) -> str:
        return f"padding:{2 * margin:.1f}px {margin:.1f}px 0 {margin:.1f}px; border-radius: 999px"

    def _build_layout(self):
        m = RING_MARGIN_MAX

        # three concentric ring boxes
        disk_core = Box(
            h_expand=True,
            style_classes=["metrics-storage-circle", "active"],
            style="border-radius: 999px",
            children=Box(
                h_expand=True, v_align="center", orientation="v", spacing=5,
                children=[
                    Box(
                        h_expand=True, v_expand=True, h_align="center",
                        children=[MaterialIconLabel(icon_text=icons.disk.symbol()), Label(label="Disk")],
                    ),
                    self.disk_label,
                ],
            ),
        )
        self.ring_3 = Box(h_expand=True, style_classes="metrics-storage-circle", style=self._ring_style(m), children=disk_core)
        self.ring_2 = Box(h_expand=True, style_classes="metrics-storage-circle", style=self._ring_style(m), children=self.ring_3)
        self.ring_1 = Box(
            size=(250, 250), h_expand=True,
            style_classes="metrics-storage-circle", style=self._ring_style(m),
            children=self.ring_2,
        )

        # radial graph
        cpu_radial = ClippingBox(
            size=(250, 250), h_expand=True, v_align="center",
            style="background-color: black; border-radius: 999px",
            children=Box(
                h_expand=True, style="margin: -10px;",
                children=Overlay(
                    h_expand=True,
                    child=ExpressiveShape(
                        style="background-color: var(--surface-bright);",
                        shape=cookie_12,
                        child=Box(
                            style="padding: 2px;",
                            children=ExpressiveShape(
                                style="background-color: var(--surface-semi-bright);",
                                shape=cookie_12,
                                child=Box(children=[self.cpu_circular_graph]),
                            ),
                        ),
                    ),
                    overlays=[
                        Box(
                            h_expand=True, v_align="center", orientation="v",
                            children=[
                                Box(h_expand=True, h_align="center", children=[self.cpu_label]),
                                self.cores,
                            ],
                        )
                    ],
                ),
            ),
        )

        def graph_panel(graph, icon, title, extra_overlay=None):
            header = Box(spacing=2, children=[MaterialIconLabel(icon_text=icon, font_size=14), Label(label=title, h_align="start")])
            overlay_content = Box(style="padding: 10px;", h_align="start", orientation="v",
                                  children=[header] + ([extra_overlay] if extra_overlay else []))
            return Overlay(
                name="metric-graph-container",
                child=ClippingBox(style="background-color: black; border-radius: 20px", children=graph),
                overlays=[overlay_content],
            )

        self.children = [
            # CPU radial + CPU bar graph
            Box(
                h_expand=True, spacing=10,
                children=[
                    Box(
                        orientation="v", spacing=8,
                        children=[
                            cpu_radial,
                            Box(
                                style_classes="metrics-desc-box", v_expand=True, spacing=8,
                                children=[
                                    self.cpu_name_label,
                                    Box(children=[
                                        MaterialIconLabel(icon_text=icons.device_thermostat.symbol()),
                                        self.cpu_temp_label,
                                    ]),
                                ],
                            ),
                        ],
                    ),
                    Box(
                        spacing=8, orientation="v",
                        children=[
                            graph_panel(self.cpu_graph, icons.cpu.symbol(), "CPU"),
                            self._make_history_slider(self.cpu_graph),
                        ],
                    ),
                ],
            ),
            # disk circles + memory bar graph
            Box(
                spacing=10,
                children=[
                    Box(
                        spacing=8, orientation="v",
                        children=[
                            self.ring_1,
                            Box(
                                style_classes="metrics-desc-box", v_expand=True,
                                h_align="start", spacing=8,
                                children=[self.disk_ratio_label],
                            ),
                        ],
                    ),
                    Box(
                        spacing=8, orientation="v",
                        children=[
                            graph_panel(self.mem_graph, icons.memory.symbol(), "Memory", extra_overlay=self.mem_ratio_label),
                            self._make_history_slider(self.mem_graph),
                        ],
                    ),
                ],
            ),
        ]

    def _update_ui(self) -> bool:
        cpu, mem, disk = self.service.get_metrics()

        self.cpu_graph.add_value(cpu)
        self.mem_graph.add_value(mem)

        self.cpu_label.set_label(f"{cpu:.0f}%")
        self.disk_label.set_label(f"{disk:.0f}%")

        used_gb, total_gb = self.service.get_disk_usage_gb()
        used_mem, total_mem = self.service.get_mem_usage_gb()
        self.disk_ratio_label.set_label(f"{used_gb:.1f} / {total_gb:.1f} GB")
        self.mem_ratio_label.set_label(f"{used_mem:.1f} / {total_mem:.1f} GB")
        self.cpu_temp_label.set_label(self.service.get_cpu_temp())

        margin = (1 - (disk / 100) ** 3) * RING_MARGIN_MAX
        style = self._ring_style(margin)
        for ring in (self.ring_1, self.ring_2, self.ring_3):
            ring.set_style(style)

        return True