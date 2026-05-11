from kivymd.uix.screen import MDScreen
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse
from kivy.properties import ListProperty


class PieChart(Widget):
    """
    Niestandardowy wykres kołowy napisany w czystym Kivy.
    Przyjmuje listę słowników w formacie:
    [{'color': (r, g, b, a), 'percent': wartość_procentowa}, ...]
    """
    data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.update_canvas, size=self.update_canvas, data=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.clear()
        with self.canvas:
            angle_start = 0
            for item in self.data:
                Color(*item.get('color', (1, 1, 1, 1)))
                percent = item.get('percent', 0)
                angle_end = angle_start + (percent / 100.0) * 360
                Ellipse(pos=self.pos, size=self.size, angle_start=angle_start, angle_end=angle_end)
                angle_start = angle_end


class StatisticsScreen(MDScreen):
    def on_enter(self):
        pie_chart = self.ids.pie_chart
        pie_chart.data = [
            {'color': (0.13, 0.59, 0.95, 1), 'percent': 45},
            {'color': (0.85, 0.19, 0.19, 1), 'percent': 30},
            {'color': (0.6, 0.4, 0.8, 1), 'percent': 25},
        ]
