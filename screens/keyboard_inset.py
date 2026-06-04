# ---------------------------------------------------------------------------
# POMOCNICZA FUNKCJA DO OBSŁUGI KLAWIATURY
# ---------------------------------------------------------------------------
# Gdy na telefonie pojawia się miękka klawiatura (ekranowa), może zasłonić
# dolną część ekranu aplikacji. Ta funkcja oblicza, ile pikseli klawiatura
# zajmuje od dołu, aby reszta aplikacji mogła się odpowiednio przesunąć
# i żadne pole tekstowe nie zostało zasłonięte.
#
# Problem: Różne telefony inaczej zgłaszają wysokość klawiatury.
# Rozwiązanie: Używamy trzech niezależnych metod pomiaru i wybieramy
# największą wartość – to najlepiej działa na różnych urządzeniach.
# ---------------------------------------------------------------------------

from kivy.core.window import Window
from kivy.metrics import Metrics, dp
from kivy.utils import platform


# Funkcja główna: oblicza wysokość klawiatury w pikselach Kivy.
# "baseline_window_height" – wysokość okna ZANIM pojawiła się klawiatura
# (zapamiętana wcześniej). Dzięki temu wiemy o ile okno się zmniejszyło.
def keyboard_inset(baseline_window_height=0):
    # Lista do której zbieramy pomiary z różnych metod
    values = []

    # Metoda 1: Wbudowana wartość Kivy.
    # Window.keyboard_height to właściwość która mówi, ile pikseli
    # zajmuje klawiatura według Kivy. Niestety nie zawsze jest dokładna.
    kh = float(Window.keyboard_height or 0)
    if kh > 0:
        values.append(kh)

    # Metoda 2: Porównanie rozmiaru okna przed i po pojawieniu się klawiatury.
    # Gdy klawiatura się pojawia, Android często zmniejsza wysokość okna
    # (tzw. "resize" – okno się kurczy, by zrobić miejsce klawiaturze).
    # Różnica między pierwotną wysokością a obecną to właśnie wysokość klawiatury.
    win_h = float(Window.height or 0)
    baseline = float(baseline_window_height or 0)
    if baseline > 0 and win_h > 0:
        shrunk = baseline - win_h          # O ile okno się zmniejszyło
        if shrunk > 0:
            values.append(shrunk)

    # Metoda 3: Odczyt bezpośrednio z systemu Android przez JNI.
    # JNI (Java Native Interface) – to sposób w jaki Python/Kivy może
    # wywoływać funkcje napisane w Javie (języku Androida).
    # Dzięki temu mamy dostęp do niskopoziomowych informacji o ekranie.
    if platform == "android":
        android_kh = _android_keyboard_inset()
        if android_kh > 0:
            values.append(android_kh)

    # Jeśli żadna metoda nie dała wyniku – zwróć 0 (brak klawiatury)
    if not values:
        return 0.0
    
    # Wybierz największą wartość – to daje najlepszy efekt wizualny
    return max(values)


# Funkcja pomocnicza: odczytuje wysokość klawiatury bezpośrednio z systemu
# Android używając JNI (Java Native Interface).
#
# CO SIĘ DZIEJE KROK PO KROKU:
# 1. Ładujemy klasy Javy przez "autoclass" (to narzędzie Kivy do JNI)
# 2. Pobieramy główne okno aplikacji (DecorView)
# 3. Pytamy system: "jaki obszar ekranu jest widoczny?"
# 4. Odejmujemy widoczny obszar od całkowitej wysokości ekranu
# 5. To co zostaje to wysokość klawiatury (w pikselach)
# 6. Przeliczamy na piksele Kivy (dzieląc przez gęstość ekranu)
def _android_keyboard_inset():
    try:
        # "jnius" to biblioteka która pozwala Pyhonowi wywoływać kod Javy.
        # "autoclass" ładuje klasę Javę po jej nazwie (np. "org.kivy.android.PythonActivity").
        from jnius import autoclass

        # PythonActivity – to główna klasa aktywności Kivy na Androidzie.
        # Każda aplikacja na Androidzie ma jedną "aktywność" (Activity) –
        # to jak "okno" aplikacji.
        # mActivity to statyczne pole które przechowuje bieżącą aktywność.
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        m_activity = PythonActivity.mActivity
        
        # Jeśli aktywność nie istnieje (jeszcze nie utworzona) – wyjdź
        if m_activity is None:
            return 0.0

        # "DecorView" – to najwyższy element w hierarchii widoków Androida.
        # Zawiera całą zawartość okna: pasek stanu, pasek nawigacji,
        # oraz naszą aplikację. Pobieramy go przez getWindow().getDecorView().
        decor_view = m_activity.getWindow().getDecorView()
        if decor_view is None:
            return 0.0

        # "Rect" – to klasa Javy reprezentująca prostokąt (współrzędne:
        # left, top, right, bottom). Tworzymy pusty prostokąt.
        Rect = autoclass("android.graphics.Rect")
        visible = Rect()
        
        # "getWindowVisibleDisplayFrame(visible)" – to kluczowa funkcja.
        # Pyta system: "jaki fragment okna jest WIDOCZNY dla użytkownika?"
        # System zapisuje odpowiedź w obiekcie "visible" (naszym prostokącie).
        # visible.bottom = dolna krawędź widocznego obszaru.
        # Jeśli klawiatura jest ukryta, visible.bottom = pełna wysokość ekranu.
        # Jeśli klawiatura jest widoczna, visible.bottom = wysokość ekranu
        # minus wysokość klawiatury (bo klawiatura zakrywa dół).
        decor_view.getWindowVisibleDisplayFrame(visible)

        # Pobieramy "RootView" – główny widok okna. Jego wysokość to
        # pełna wysokość ekranu (łącznie z obszarem pod klawiaturą).
        root_view = decor_view.getRootView()
        if root_view is None:
            return 0.0

        # "getHeight()" – zwraca wysokość w pikselach fizycznych ekranu.
        screen_px = float(root_view.getHeight())
        
        # "visible.bottom" – dolna krawędź widocznego obszaru.
        # Różnica: screen_px - visible.bottom = wysokość klawiatury
        # (bo klawiatura jest tym, co zakrywa dół ekranu).
        inset_px = screen_px - float(visible.bottom)
        
        # Jeśli różnica jest mniejsza niż 20dp – to raczej nie klawiatura,
        # tylko pasek nawigacji Androida. Pomijamy taki mały odczyt.
        if inset_px < dp(20):
            return 0.0

        # Przeliczamy piksele fizyczne na piksele Kivy.
        # Gęstość ekranu (density) mówi ile fizycznych pikseli przypada
        # na jeden piksel Kivy. Np. jeśli density=2.0, to Kivy myśli że
        # ekran ma połowę rzeczywistej rozdzielczości.
        # Dzieląc przez density, dostajemy wartość w pikselach Kivy.
        density = float(Metrics.density or 1.0)
        return inset_px / density
    
    except Exception:
        # Jeśli coś poszło nie tak (np. brak uprawnień) – zwróć 0
        return 0.0