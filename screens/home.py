from kivymd.uix.screen import MDScreen
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp

class TimelineWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.clear()
        with self.canvas:
            # Środek widgetu w pionie
            cy = self.center_y - dp(10)
            start_x = self.x + dp(20)
            end_x = self.right - dp(20)
            
            # 1. Rysowanie linii bazowej (biała/jasna)
            Color(1, 1, 1, 1)
            Line(points=[start_x, cy, end_x, cy], width=1.5)
            
            # Konfiguracja punktów
            steps = 5
            spacing = (end_x - start_x) / (steps - 1)
            completed_steps = 4 # Ile kroków jest "zamalowanych" na czarno

            for i in range(steps):
                px = start_x + (i * spacing)
                
                # Rysowanie kropki
                if i < completed_steps:
                    Color(0, 0, 0, 1) # Czarny dla ukończonych
                else:
                    Color(1, 1, 1, 1) # Biały dla nadchodzących
                
                Ellipse(pos=(px - dp(8), cy - dp(8)), size=(dp(16), dp(16)))
                
                # Opcjonalnie: pogrubiona linia dla ukończonego postępu
                if i < completed_steps - 1:
                    Color(0, 0, 0, 1)
                    Line(points=[px, cy, px + spacing, cy], width=2)

class HomeScreen(MDScreen):
    def plus_button_pressed(self):
        print("Plus button pressed on Home Screen, navigating to AddProjectScreen")
        self.manager.current = 'add_project'
        