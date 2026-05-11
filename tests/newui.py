from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.graphics import Color, Line, Ellipse
from kivy.utils import get_color_from_hex

# KivyMD imports
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDIconButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.relativelayout import MDRelativeLayout

# --- KONFIGURACJA OKNA ---
Window.size = (360, 800)

KV = '''
#:import utils kivy.utils

<DotProgressBar>:
    size_hint_y: None
    height: dp(20)

<ProjectCard>:
    size_hint: None, None
    size: dp(180), dp(220)
    radius: [dp(24), ]
    md_bg_color: app.theme_cls.accent_color if not app.edit_mode else utils.get_color_from_hex("#FFCDD2")
    elevation: 2
    orientation: 'vertical'
    padding: dp(10)
    spacing: dp(5)

    canvas.before:
        PushMatrix
        Rotate:
            angle: self.angle
            origin: self.center
    canvas.after:
        PopMatrix

    MDRelativeLayout:
        # Obrazek tła
        MDCard:
            size_hint: 1, 0.6
            pos_hint: {'center_x': 0.5, 'top': 1}
            radius: [dp(18), ]
            elevation: 0
            md_bg_color: 0, 0, 0, 0
            AsyncImage:
                source: root.image_source
                allow_stretch: True
                keep_ratio: False

        # Tytuł
        MDLabel:
            text: root.title
            font_style: "Subtitle2"
            bold: True
            halign: "center"
            theme_text_color: "Custom"
            text_color: utils.get_color_from_hex(app.theme_text_dark)
            size_hint_y: None
            height: dp(25)
            pos_hint: {'center_x': 0.5, 'y': 0.2}
            
        # Pasek postępu
        DotProgressBar:
            size_hint_x: 0.9
            pos_hint: {'center_x': 0.5, 'y': 0.05}
            total_steps: root.total_steps
            current_step: root.current_step
            
        # Pływająca emotikona
        MDIcon:
            icon: root.emoji_source
            size_hint: None, None
            size: dp(40), dp(40)
            pos_hint: {'right': 1.1, 'top': 1.1}
            theme_text_color: "Custom"
            text_color: 1, 0.8, 0, 1 # Złoty kolor dla korony itp.

<SessionCard>:
    size_hint: 0.9, None
    height: dp(140)
    radius: [dp(24), ]
    md_bg_color: utils.get_color_from_hex(app.theme_session_bg)
    elevation: 3
    padding: dp(15)
    orientation: 'vertical'
    
    # Nagłówek sesji
    MDRelativeLayout:
        size_hint_y: None
        height: dp(20)
        MDLabel:
            text: "Ostatnia sesja"
            bold: True
            font_style: "Caption"
            halign: "left"
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
        MDLabel:
            text: "Wczoraj"
            bold: True
            font_style: "Caption"
            halign: "right"
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
            
    # Nazwa i emotikona
    MDBoxLayout:
        spacing: dp(10)
        size_hint_y: None
        height: dp(40)
        MDIcon:
            icon: "crown"
            theme_text_color: "Custom"
            text_color: 1, 0.8, 0, 1
        MDLabel:
            text: "Nazwa Projektu"
            font_style: "H6"
            bold: True
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
                
    # Czas i Progress
    MDLabel:
        text: "Czas:  01:12:53"
        halign: "right"
        font_style: "Caption"
        theme_text_color: "Custom"
        text_color: 1, 1, 1, 1
        
    DotProgressBar:
        size_hint_x: 1
        total_steps: 5
        current_step: 2

<MainScreen>:
    md_bg_color: utils.get_color_from_hex(app.theme_bg)

    MDBoxLayout:
        orientation: 'vertical'
        
        # 1. SAFE AREA
        Widget:
            size_hint_y: None
            height: dp(35) 
            
        # 2. HEADER
        MDFloatLayout:
            size_hint_y: None
            height: dp(70)
            canvas.after:
                Color:
                    rgba: 1, 1, 1, 1
                Line:
                    points: [self.x, self.y, self.right, self.y]
                    width: dp(1.5)
            
            MDLabel:
                text: "JUST DO IT"
                font_style: "H4"
                bold: True
                halign: "center"
                pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                theme_text_color: "Custom"
                text_color: 1, 1, 1, 1
                
            MDIconButton:
                icon: "view-grid"
                pos_hint: {'right': 0.98, 'center_y': 0.5}
                theme_text_color: "Custom"
                text_color: (1, 1, 0, 1) if app.edit_mode else (1, 1, 1, 1)
                on_release: app.toggle_layout_menu()

        # 3. CONTENT
        ScrollView:
            do_scroll_x: False
            
            MDFloatLayout:
                id: projects_container
                size_hint_y: None
                height: dp(900)
                
                SessionCard:
                    pos_hint: {'center_x': 0.5, 'y': 0.05}

    # --- FLOATING BOTTOM PANEL ---
    MDFloatLayout:
        size_hint: 1, None
        height: dp(90)
        pos_hint: {'center_x': 0.5, 'y': 0}
        
        MDCard:
            size_hint: 0.96, 0.75
            pos_hint: {'center_x': 0.5, 'y': 0.1}
            radius: [dp(25), ]
            elevation: 4
            md_bg_color: 1, 1, 1, 1
            
            MDBoxLayout:
                padding: [dp(20), 0, dp(20), 0]
                MDIconButton:
                    icon: "home-outline"
                    user_font_size: dp(30)
                    pos_hint: {"center_y": .5}
                Widget:
                MDIconButton:
                    icon: "chart-arc"
                    user_font_size: dp(30)
                    pos_hint: {"center_y": .5}

        MDIconButton:
            icon: "plus"
            md_bg_color: utils.get_color_from_hex(app.theme_card_bg)
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
            user_font_size: dp(40)
            size_hint: None, None
            size: dp(75), dp(75)
            pos_hint: {'center_x': 0.5, 'center_y': 0.55}
            canvas.before:
                Color:
                    rgba: utils.get_color_from_hex(app.theme_card_bg)
                Ellipse:
                    pos: self.pos
                    size: self.size
'''

class DotProgressBar(Widget):
    total_steps = NumericProperty(5)
    current_step = NumericProperty(2)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.update_canvas, size=self.update_canvas, 
                  total_steps=self.update_canvas, current_step=self.update_canvas)

    def update_canvas(self, *args):
        app = MDApp.get_running_app()
        color_dark = get_color_from_hex(app.theme_text_dark) if app else (0.1, 0.1, 0.1, 1)
        color_light = get_color_from_hex("#E0E0E0") 
        
        self.canvas.clear()
        with self.canvas:
            Color(*color_dark)
            start_x = self.x + dp(5)
            end_x = self.right - dp(5)
            line_y = self.center_y
            Line(points=[start_x, line_y, end_x, line_y], width=dp(1.5))
            
            if self.total_steps > 1:
                spacing = (end_x - start_x) / (self.total_steps - 1)
                for i in range(self.total_steps):
                    Color(*(color_dark if i < self.current_step else color_light))
                    dot_x = start_x + (i * spacing) - dp(6)
                    dot_y = line_y - dp(6)
                    Ellipse(pos=(dot_x, dot_y), size=(dp(12), dp(12)))

class ProjectCard(MDCard):
    title = StringProperty("")
    image_source = StringProperty("")
    emoji_source = StringProperty("")
    total_steps = NumericProperty(5)
    current_step = NumericProperty(0)
    angle = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._long_press_ev = None
        self._shake_anim = None
    
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and MDApp.get_running_app().edit_mode:
            # Start 2s timer for long press detection
            self._long_press_ev = Clock.schedule_once(lambda dt: self._start_drag_mode(touch), 2.0)
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def _start_drag_mode(self, touch):
        self.pos_hint = {}  # Allow free movement within the FloatLayout
        # Start Shaking animation
        self._shake_anim = Animation(angle=2, d=0.08) + Animation(angle=-2, d=0.08)
        self._shake_anim.repeat = True
        self._shake_anim.start(self)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if self._shake_anim:
                # Shaking active, we can drag the card
                self.x += touch.dx
                self.y += touch.dy
            else:
                # Still waiting for 2s, cancel if finger moves too much
                if abs(touch.dx) > 10 or abs(touch.dy) > 10:
                    if self._long_press_ev:
                        Clock.unschedule(self._long_press_ev)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if self._long_press_ev:
                Clock.unschedule(self._long_press_ev)
            if self._shake_anim:
                self._shake_anim.stop(self)
                self._shake_anim = None
                # Reset rotation and save position
                Animation(angle=0, d=0.1).start(self)
                self.save_position()
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def save_position(self):
        # Relative coordinates are useful for persisting across different screen sizes
        rel_x = self.x / self.parent.width
        rel_y = self.top / self.parent.height
        print(f"Position saved for {self.title}: x={rel_x:.2f}, top={rel_y:.2f}")

class SessionCard(MDCard):
    pass

class MainScreen(MDFloatLayout):
    pass

class JustDoItApp(MDApp):
    theme_bg = StringProperty('#8A2BE2')
    theme_card_bg = StringProperty('#B388FF')
    theme_session_bg = StringProperty('#5E35B1')
    theme_text_dark = StringProperty('#212121')
    edit_mode = BooleanProperty(False)

    def build(self):
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.accent_palette = "Purple"
        self.theme_cls.accent_hue = "200"
        
        Builder.load_string(KV)
        return MainScreen()
        
    def on_start(self):
        # Teraz self.root na pewno nie jest None
        self.create_dynamic_project("Nauka Włoskiego", 'panda.png', "crown", 5, 2, 0.05, 0.95)
        self.create_dynamic_project("Siłownia", 'panda.png', "car", 8, 4, 0.48, 0.72)
        self.create_dynamic_project("Kodowanie", 'panda.png', "language-python", 4, 1, 0.05, 0.48)

    def create_dynamic_project(self, title, image, emoji, total_dots, current_dots, x_pos, y_top):
        # Używamy identyfikatora z self.root
        container = self.root.ids.projects_container
        new_card = ProjectCard(
            title=title,
            image_source=image,
            emoji_source=emoji,
            total_steps=total_dots,
            current_step=current_dots,
            pos_hint={'x': x_pos, 'top': y_top}
        )
        container.add_widget(new_card)

    def toggle_layout_menu(self):
        self.edit_mode = not self.edit_mode

if __name__ == '__main__':
    JustDoItApp().run()