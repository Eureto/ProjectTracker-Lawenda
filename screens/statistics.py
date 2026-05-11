from kivymd.app import MDApp
from kivy.lang import Builder
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
        # Nasłuchujemy zmian rozmiaru, pozycji i danych, aby przerysować wykres
        self.bind(pos=self.update_canvas, size=self.update_canvas, data=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.clear()
        with self.canvas:
            angle_start = 0
            for item in self.data:
                # Ustawienie koloru dla danego wycinka
                Color(*item.get('color', (1, 1, 1, 1)))
                percent = item.get('percent', 0)
                # Obliczenie kąta końcowego (procent z 360 stopni)
                angle_end = angle_start + (percent / 100.0) * 360
                
                # Rysowanie wycinka koła
                Ellipse(pos=self.pos, size=self.size, angle_start=angle_start, angle_end=angle_end)
                angle_start = angle_end

class MainScreen(MDScreen):
    pass

class MyApp(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.theme_style = "Light"
        return Builder.load_file('main.kv')

    def on_start(self):
        # 1. Inicjalizacja wykresu kołowego
        # Łatwo dodajesz dane, podając kolor (RGBA) i wartość procentową
        pie_chart = self.root.ids.pie_chart
        pie_chart.data = [
            {'color': (0.13, 0.59, 0.95, 1), 'percent': 45}, # Niebieski
            {'color': (0.85, 0.19, 0.19, 1), 'percent': 30}, # Czerwony
            {'color': (0.6, 0.4, 0.8, 1), 'percent': 25},    # Fioletowy/Inny
        ]

        # ---------------------------------------------------------
        # ZAKOMENTOWANA OPCJA Z ROZWIJANĄ LISTĄ (MDDropdownMenu)
        # Aby użyć: odkomentuj to i powiązany przycisk w pliku .kv
        # ---------------------------------------------------------
        # from kivymd.uix.menu import MDDropdownMenu
        # menu_items = [
        #     {"viewclass": "OneLineListItem", "text": "Miesiąc", 
        #      "on_release": lambda x="Miesiąc": self.set_dropdown_item(x)},
        #     {"viewclass": "OneLineListItem", "text": "Tydzień", 
        #      "on_release": lambda x="Tydzień": self.set_dropdown_item(x)},
        #     {"viewclass": "OneLineListItem", "text": "Dzień", 
        #      "on_release": lambda x="Dzień": self.set_dropdown_item(x)}
        # ]
        # self.menu = MDDropdownMenu(
        #     caller=self.root.ids.dropdown_button,
        #     items=menu_items,
        #     width_mult=4,
        # )

    # def set_dropdown_item(self, text_item):
    #     self.root.ids.dropdown_button.text = text_item
    #     self.menu.dismiss()

if __name__ == '__main__':
    MyApp().run()