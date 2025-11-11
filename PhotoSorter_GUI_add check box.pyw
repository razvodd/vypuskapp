import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import datetime
import re
import subprocess
import json # Для сохранения/загрузки конфигурации
import atexit # Для сохранения конфигурации при закрытии
import shutil # Для перемещения/копирования файлов
import threading # НОВОЕ: Для неблокирующего копирования

# ДОБАВЛЕНИЕ: Импорт Pillow (PIL) для работы с PNG
try:
    from PIL import Image, ImageTk
except ImportError:
    pass

# ====================================================================
# КОНСТАНТЫ И ПУТИ
# ====================================================================
FONT_FAMILY = 'Roboto'
COLOR_BACKGROUND = 'white'
COLOR_TEXT_NORMAL = '#444'
COLOR_TEXT_LIGHT = '#888'
COLOR_ACCENT_PINK = '#e53965'
COLOR_LINE_INACTIVE = '#ccc'
COLOR_BUTTON_DISABLED = '#444'
COLOR_BUTTON_DISABLED_LIGHT = '#EAEAEA'
COLOR_BUTTON_TEXT_DISABLED = '#ccc'
COLOR_CHECKBOX_BORDER = '#AEAEAE'
COLOR_STATUS_ERROR = '#D32F2F' # Красный для ошибок
COLOR_STATUS_NORMAL = '#2E7D32' # Зеленый для успеха

# Параметры UI
BLOCK_PADY_VERTICAL = (20, 0)
ANIMATION_STEPS = 4
BUTTON_HEIGHT = 50
CONFIG_FILE = os.path.join(os.path.expanduser('~'), '.vyipusk_config.json')

# ИЗМЕНЕНИЕ: Список RAW-расширений (с точкой в начале)
RAW_EXTENSIONS = [
    '.raw', '.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2',
    '.pef', '.dng', '.raf', '.srw', '.kdc', '.mos'
]

# НОВОЕ: Карта позиций для переименования учеников
STUDENT_POSITIONS = {
    0: "Виньетка", # Будет переименовано в ФИО.JPG
    1: "ЛР_Портрет1", # Будет переименовано в ЛР_ФИО.JPG
    2: "ЛС_Портрет2", # Будет переименовано в ЛС_ФИО.JPG
    3: "Друг1",      # Сохраняет номер
    4: "Друг2"       # Сохраняет номер
}

# ====================================================================
# ФУНКЦИЯ ДЛЯ УПРАВЛЕНИЯ ПУТЯМИ (КРИТИЧНО ДЛЯ PYINSTALLER)
# ====================================================================
def resource_path(relative_path):
    """Получает абсолютный путь к ресурсу, работает для dev и PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
    
# ====================================================================
# КЛАСС FloatingLabelEntry
# ====================================================================
class FloatingLabelEntry(tk.Frame):
    def __init__(self, master, label_text, font_family, initial_value="", on_change_callback=None, **kwargs):
        # ИСПРАВЛЕНИЕ: Исправлен вызов super()
        super().__init__(master, bg=COLOR_BACKGROUND)
        self.label_text = label_text
        self.font_family = font_family
        self.on_change_callback = on_change_callback
        self.is_floating = False
        self.animating = False

        self.entry_container = tk.Frame(self, bg=COLOR_BACKGROUND, height=45)
        self.entry_container.pack(fill='x', expand=True)
        self.entry_container.pack_propagate(False)

        # ИЗМЕНЕНИЕ: Убран bd и relief, добавлен highlightthickness=0
        self.entry = tk.Entry(self.entry_container, bd=0, relief=tk.FLAT,
                                  highlightthickness=0, # Убраны серые рамки
                                  font=(font_family, 12), bg=COLOR_BACKGROUND,
                                  fg=COLOR_TEXT_NORMAL, insertbackground=COLOR_ACCENT_PINK,
                                  insertwidth=1, # Уменьшен курсор
                                  readonlybackground=COLOR_BACKGROUND, # КРИТИЧНОЕ ИСПРАВЛЕНИЕ
                                  **kwargs)
        self.entry.place(relx=0, rely=0.7, relwidth=1, anchor='w')

        self.label = tk.Label(self.entry_container, text=label_text,
                                  bg=COLOR_BACKGROUND, fg=COLOR_TEXT_LIGHT,
                                  font=(font_family, 12), anchor='w')
        self.label.place(relx=-0.01, rely=0.5, relwidth=1, height=20, anchor='w')

        self.line = tk.Frame(self, height=1, bg=COLOR_LINE_INACTIVE)
        self.line.pack(fill='x', pady=(0, 0))

        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.label.bind("<Button-1>", lambda e: self.entry.focus_set())
        
        self._setup_universal_entry_clipboard()

        if initial_value:
             self.entry.insert(0, initial_value)
             self._float_label(initial_call=True)

    def _setup_universal_entry_clipboard(self):
        """Настраивает привязки для Ctrl+C/V/X, работающие независимо от раскладки."""
        self.entry.bind("<Control-Key-v>", lambda e: (e.widget.event_generate("<<Paste>>"), "break"), add="+")
        self.entry.bind("<Control-Key-c>", lambda e: (e.widget.event_generate("<<Copy>>"), "break"), add="+")
        self.entry.bind("<Control-Key-x>", lambda e: (e.widget.event_generate("<<Cut>>"), "break"), add="+")

    def _focus_in(self, event=None):
        self.line.config(bg=COLOR_ACCENT_PINK, height=2)
        self._float_label(initial_call=True)

    def _focus_out(self, event=None):
        self.line.config(bg=COLOR_LINE_INACTIVE, height=1)
        if not self.entry.get().strip():
            self._sink_label()
            
        # ИЗМЕНЕНИЕ: При потере фокуса для поля "Дата", принудительно устанавливаем цвет текста
        # если есть значение, чтобы он не сливался с опускающейся меткой.
        if self.label_text == "Дата" and self.entry.get().strip():
            self.entry.config(fg=COLOR_TEXT_NORMAL)
            
        if self.on_change_callback:
            self.on_change_callback()

    def _on_key_release(self, event=None):
        if self.entry.get().strip() and not self.is_floating:
            self._float_label()
            
        if self.on_change_callback:
            self.on_change_callback()

    def _float_label(self, initial_call=False):
        if self.is_floating or self.animating:
            return
        self.animating = True
        self._animate_label(0, True)

    def _sink_label(self):
        if not self.is_floating or self.animating:
            return
        self.animating = True
        self._animate_label(0, False)

    # ИСПРАВЛЕНИЕ (ПРОБЛЕМА С "ДАТА"): Новая функция
    def _force_float(self):
        """Принудительно поднимает метку без анимации."""
        RELX_OFFSET = -0.01
        self.animating = False
        self.is_floating = True
        self.label.config(font=(self.font_family, 9), fg=COLOR_TEXT_LIGHT)
        self.label.place(relx=RELX_OFFSET, rely=0.05, relwidth=1, anchor='nw')


    def _animate_label(self, step, float_up):
        RELX_OFFSET = -0.01
        
        if step > ANIMATION_STEPS:
            self.animating = False
            self.is_floating = float_up
            
            self.label.config(fg=COLOR_TEXT_LIGHT)
            if float_up:
                self.label.place(relx=RELX_OFFSET, rely=0.05, relwidth=1, anchor='nw')
            else:
                self.label.place(relx=RELX_OFFSET, rely=0.5, relwidth=1, anchor='w')
            return
            
        t = step / ANIMATION_STEPS
        ease = t*t*(3 - 2*t)
        
        base_size = 12
        float_size = 9 

        if float_up:
            y = 0.5 - (0.5 - 0.05) * ease
            size = base_size - int((base_size - float_size) * ease)
        else:
            y = 0.05 + (0.5 - 0.05) * ease
            size = float_size + int((base_size - float_size) * ease)
            
        if float_up:
            self.label.place(relx=RELX_OFFSET, rely=y, relwidth=1, height=size+7, anchor='nw')
        else:
            self.label.place(relx=RELX_OFFSET, rely=y, relwidth=1, height=size+7, anchor='w')
        
        fg_color = COLOR_TEXT_LIGHT
            
        self.label.config(font=(self.font_family, size), fg=fg_color)
        self.after(15, lambda: self._animate_label(step+1, float_up))

    def get(self):
        return self.entry.get()
        
    def set_state(self, new_state):
        """Устанавливает состояние (normal/readonly/disabled) для Entry."""
        # 'readonly' используется для PathFileSelector, 'disabled' для обычных
        if new_state == tk.DISABLED:
            # Для FloatingLabelEntry, 'disabled' выглядит плохо
            # Используем 'readonly' и меняем цвет, чтобы имитировать 'disabled'
            self.entry.config(state='readonly')
            self.entry.config(fg=COLOR_TEXT_LIGHT) # Серый текст
        else:
            self.entry.config(state=new_state)
            self.entry.config(fg=COLOR_TEXT_NORMAL)
        
        # Для PathFileSelector, который 'readonly' по умолчанию
        if isinstance(self, PathFileSelector) and new_state == tk.NORMAL:
             self.entry.config(state='readonly')
             self.entry.config(fg=COLOR_TEXT_NORMAL)

# ====================================================================
# КЛАСС PathFileSelector
# ====================================================================
class PathFileSelector(FloatingLabelEntry):
    def __init__(self, master, label_text, font_family, select_dir=True, allow_multiple=False, initial_value="", on_select_callback=None, **kwargs):
        self.select_dir = select_dir
        self.allow_multiple = allow_multiple 
        self.on_select_callback = on_select_callback
        
        # ИЗМЕНЕНИЕ: Вызываем super() без extra kwargs, так как они уже обработаны
        super().__init__(master, label_text, font_family, initial_value=initial_value, on_change_callback=None, state='readonly', **kwargs)
        
        self.entry.config(cursor="hand2")
        self.entry.unbind("<KeyRelease>")
        self.entry.unbind("<Key>")

        # ИСПРАВЛЕНИЕ: Используем lambda, чтобы вызов self.select_path_or_file
        # можно было переопределить ПОСЛЕ __init__
        self.entry.bind("<Button-1>", lambda e: self.select_path_or_file(e))
        self.label.bind("<Button-1>", lambda e: self.select_path_or_file(e))
        
        self.entry.config(state='normal')
        if initial_value:
             self.entry.insert(0, initial_value)
             self._float_label(initial_call=True)
        self.entry.config(state='readonly')

    def select_path_or_file(self, event=None):
        
        # НОВОЕ: Если виджет отключен, ничего не делаем
        if self.entry.cget('state') == tk.DISABLED:
            return

        initial_dir = os.path.expanduser('~')
        current_val = self.get().strip()
        # ИЗМЕНЕНИЕ: Проверяем, содержит ли текущее значение запятую (признак нескольких файлов)
        if (not self.allow_multiple or ',' not in current_val) and current_val:
            # Пытаемся найти существующий путь (даже если это список)
            first_path_guess = current_val.split(',')[0].strip()
            # Проверяем, существует ли путь, прежде чем использовать dirname
            if os.path.exists(first_path_guess):
                if os.path.isfile(first_path_guess):
                    initial_dir = os.path.dirname(first_path_guess)
                elif os.path.isdir(first_path_guess):
                    initial_dir = first_path_guess

        paths_selected = None
            
        if self.select_dir:
            paths_selected = filedialog.askdirectory(initialdir=initial_dir)
        elif self.allow_multiple:
            paths_selected = filedialog.askopenfilenames(
                initialdir=initial_dir,
                filetypes=[("JPEG files", "*.jpg *.jpeg")]
            )
        else:
            paths_selected = filedialog.askopenfilename(
                initialdir=initial_dir,
                filetypes=[("JPEG files", "*.jpg *.jpeg")]
            )
            
        if paths_selected:
            self.entry.config(state='normal')
            self.entry.delete(0, tk.END)
            
            display_text = ""
            if isinstance(paths_selected, (list, tuple)):
                # ИЗМЕНЕНИЕ: Отображаем имена файлов через запятую, как в скриншоте
                if len(paths_selected) > 0:
                    filenames = [os.path.basename(p) for p in paths_selected]
                    display_text = ", ".join(filenames)
                # (Если 0 файлов, display_text останется пустым)
            else:
                display_text = paths_selected # Для askdirectory (один путь)

            self.entry.insert(0, display_text)
            self.entry.config(state='readonly')
            self._float_label(initial_call=True)
            
            if self.on_select_callback:
                # Передаем кортеж (для askopenfilenames) или строку (для askdirectory)
                self.on_select_callback(paths_selected)
                
    def set_state(self, new_state):
        """Переопределяем set_state для PathFileSelector."""
        current_state = tk.DISABLED if new_state == tk.DISABLED else 'readonly'
        self.entry.config(state=current_state)
        
        if new_state == tk.DISABLED:
            self.entry.config(fg=COLOR_TEXT_LIGHT, cursor="arrow")
            self.label.config(cursor="arrow")
            self.entry.unbind("<Button-1>")
            self.label.unbind("<Button-1>")
        else:
            self.entry.config(fg=COLOR_TEXT_NORMAL, cursor="hand2")
            self.label.config(cursor="hand2")
            self.entry.bind("<Button-1>", lambda e: self.select_path_or_file(e))
            self.label.bind("<Button-1>", lambda e: self.select_path_or_file(e))

# ====================================================================
# ОСНОВНОЙ КЛАСС ПРИЛОЖЕНИЯ
# ====================================================================
class FolderGeneratorApp:
    
    # ИЗМЕНЕНИЕ: НОВАЯ ФУНКЦИЯ ЦЕНТРИРОВАНИЯ
    def _center_window(self, width=380, height=680): # Уменьшена высота
        """Центрирует окно приложения на экране."""
        # Получаем размеры экрана
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        # Рассчитываем позицию x, y
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.master.geometry(f'{width}x{height}+{x}+{y}')

    def __init__(self, master):
        self.master = master
        master.title("ВЫПУСК.РУ")
        
        master.resizable(False, False)
        master.configure(bg=COLOR_BACKGROUND)

        # --- Переменные состояния ---
        self.output_path = "" 
        self.shooting_path = ""
        self.selection_file_path = None # ИЗМЕНЕНИЕ: Теперь это ключевое поле
        
        # ИЗМЕНЕНИЕ: Словарь для хранения номеров и их позиций
        # Пример: {студент: {102: 0, 105: 1, 110: 3, 112: 4}, учитель: {401: 0}, общая: {501: 0}}
        self.selection_data = {} 
        
        self.entries = {}
        
        # --- ИЗМЕНЕНИЕ: Новые переменные для чекбоксов ---
        self.var_copy_selected_raw = tk.BooleanVar()
        self.var_copy_all_raw_jpg = tk.BooleanVar()
        self.var_jpg_exported = tk.BooleanVar()
        
        self.generate_button = None 
        self.sort_button = None 
        self.logo_image = None
        self.status_label = None
        self.canvas_gen = None 
        self.canvas_sort = None
        
        # --- ИЗМЕНЕНИЕ: Ссылки на виджеты для блокировки ---
        self.path_shooting_sel = None
        self.path_selection_file = None
        
        # НОВОЕ: Контейнеры для чекбоксов (для блокировки)
        # (frame, canvas, label)
        self.cb_widgets_selected_raw = None
        self.cb_widgets_all_raw_jpg = None
        self.cb_widgets_jpg_exported = None
        
        # НОВОЕ: Общий флаг блокировки для ВСЕХ фоновых задач
        self.is_processing = False
        # ИСПРАВЛЕНИЕ (ПРОБЛЕМА "ЗАВИСШИХ" КНОПОК):
        self.current_task_canvas = None # Хранит canvas запущенной задачи
        
        # --- Загрузка и инициализация ---
        self.config_data = self._load_config()
        self._init_variables_from_config()
        
        self.setup_ui()
        self.set_default_path()
        
        # ИЗМЕНЕНИЕ: Центрируем окно ПОСЛЕ setup_ui
        self._center_window(width=380, height=680)
        
        master.protocol("WM_DELETE_WINDOW", self._on_closing)
        atexit.register(self.save_config)

    # ====================================================================
    # КОНФИГУРАЦИЯ И СТАТУС
    # ====================================================================
    def _load_config(self):
        """Загружает конфигурацию из файла .vyipusk_config.json."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка загрузки конфигурации: {e}")
                return {}
        return {}

    def _init_variables_from_config(self):
        """Инициализирует переменные из загруженной конфигурации."""
        data = self.config_data
        
        # ИЗМЕНЕНИЕ (NEW): Загружаем последний базовый путь для съемки
        self.shooting_path = data.get('last_shooting_base_path', "") 
        self.output_path = "" 
        
        # ИЗМЕНЕНИЕ: Новые чекбоксы, по умолчанию включены
        self.var_copy_selected_raw.set(True)
        self.var_copy_all_raw_jpg.set(True)
        self.var_jpg_exported.set(False)
        
    def save_config(self):
        """Сохраняет текущие настройки в файл .vyipusk_config.json."""
        # НОВОЕ: Получаем родительский каталог для сохранения (без последней папки)
        last_shooting_dir = ""
        # Если shooting_path установлен (например, 'D:\DCIM\104MSDCF'), сохраняем его родителя ('D:\DCIM')
        if self.shooting_path:
             last_shooting_dir = os.path.dirname(self.shooting_path)

        config_data = {
            'last_shooting_base_path': last_shooting_dir
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")
            
    def _on_closing(self):
        """Обработчик закрытия окна."""
        self.save_config()
        self.master.destroy()

    def _update_status(self, message, is_error=False):
        """Обновляет метку статуса внизу."""
        # ИСПРАВЛЕНИЕ (ПРОБЛЕМА КРАСНЫХ ПОДСКАЗОК):
        color = COLOR_TEXT_LIGHT # По умолчанию серый
        if is_error:
             color = COLOR_STATUS_ERROR # Если ошибка, используем красный
            
        if self.status_label:
            self.status_label.config(text=message, fg=color)
            self.master.update_idletasks() # Обновляем UI немедленно
        else:
            print(f"СТАТУС: {message}")

    # ====================================================================
    # UI Вспомогательные методы
    # ====================================================================
    def create_rounded_rectangle(self, canvas, x1, y1, x2, y2, radius, fill_color, outline_color="", width=1, tags=None):
        """Вспомогательная функция для отрисовки скругленного прямоугольника на Canvas."""
        points = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        canvas.create_polygon(points, smooth=True, fill=fill_color, outline=outline_color, width=width, tags=tags)

    def draw_button(self, canvas, state, text, event=None):
        """Отрисовывает кастомную скругленную кнопку на Canvas."""
        if not canvas: return
        
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        
        if width <= 0 or height <= 0: return
            
        radius = 16
        
        # ИЗМЕНЕНИЕ: Обе кнопки ("Сгенерировать" и "Разложить") теперь серые
        is_action_button = (canvas == self.canvas_gen or canvas == self.canvas_sort)
        
        fill_col = ""
        text_color = ""
        outline_col = ""
        cursor = "arrow"

        if state == tk.NORMAL:
            if is_action_button:
                fill_col = COLOR_BUTTON_DISABLED # Темно-серый
                text_color = "white"
                outline_col = ""
            else: # Fallback для других (если появятся)
                fill_col = COLOR_ACCENT_PINK
                text_color = "white"
            cursor = "hand2"
        
        else: # state == tk.DISABLED
            # ИСПРАВЛЕНИЕ (ПРОБЛЕМА "ЗАВИСШИХ" КНОПОК):
            # Показываем "Выполнение..." ТОЛЬКО на той кнопке, которая была нажата
            if self.is_processing and canvas == self.current_task_canvas:
                fill_col = COLOR_BUTTON_DISABLED # Темно-серый
                text_color = "white"
                text = "Выполнение..."
            else:
                # Все остальные случаи (просто неактивна, или занята другой задачей)
                fill_col = COLOR_BUTTON_DISABLED_LIGHT # Светло-серый
                text_color = COLOR_BUTTON_TEXT_DISABLED
            cursor = "arrow" 

        self.create_rounded_rectangle(canvas, 1, 1, width-1, height-1, radius, fill_color=fill_col, outline_color=outline_col, tags="button_bg") 
        
        canvas.create_text(width/2, height/2, text=text, 
                             font=(FONT_FAMILY, 14, 'bold'), fill=text_color, tags="button_text")
        
        canvas.config(cursor=cursor)


    def create_styled_checkbox_in_frame(self, master, text, variable, app_ref, row, col, columnspan, label_right_pad=4):
        """
        Создает стилизованный чекбокс.
        НОВОЕ: Принимает 'app_ref' для проверки self.is_processing.
        Возвращает (internal_frame, canvas, label) для управления состоянием.
        """
        internal_frame = tk.Frame(master, bg=COLOR_BACKGROUND)
        internal_frame.grid(row=row, column=col, columnspan=columnspan, sticky='w') 

        indicator_size = 20
        
        canvas = tk.Canvas(internal_frame, width=indicator_size, height=indicator_size, 
                             bg=COLOR_BACKGROUND, highlightthickness=0, bd=0)
        canvas.pack(side=tk.LEFT, padx=(0, 4))
        
        def draw_indicator():
            canvas.delete("all")
            x1, y1 = 1, 1
            x2, y2 = indicator_size - 1, indicator_size - 1
            checkbox_radius = 6
            
            # Определяем цвет рамки в зависимости от состояния (для неактивного)
            border_color = COLOR_CHECKBOX_BORDER
            
            # НОВОЕ: Если приложение занято, делаем чекбокс серым
            if app_ref.is_processing:
                border_color = COLOR_BUTTON_DISABLED_LIGHT # Бледно-серый
                
            if variable.get():
                # Активное состояние (вкл)
                fill_color = COLOR_ACCENT_PINK
                if app_ref.is_processing:
                    fill_color = COLOR_BUTTON_TEXT_DISABLED # Серый, если занято

                self.create_rounded_rectangle(canvas, x1, y1, x2, y2, checkbox_radius, 
                                                fill_color=fill_color, tags="checkbox_outer_border")
                offset_white = 2
                w_x1, w_y1 = x1 + offset_white, y1 + offset_white
                w_x2, w_y2 = x2 - offset_white, y2 - offset_white
                self.create_rounded_rectangle(canvas, w_x1, w_y1, w_x2, w_y2, 
                                                checkbox_radius, fill_color=COLOR_BACKGROUND, tags="checkbox_white_fill")
                offset_pink = 4
                p_x1, p_y1 = x1 + offset_pink, y1 + offset_pink
                p_x2, p_y2 = x2 - offset_pink, y2 - offset_pink
                self.create_rounded_rectangle(canvas, p_x1, p_y1, p_x2, p_y2, 
                                                checkbox_radius, fill_color=fill_color, tags="checkbox_inner_fill")
            else:
                # Неактивное состояние (выкл)
                self.create_rounded_rectangle(canvas, x1, y1, x2, y2, checkbox_radius, 
                                                fill_color=COLOR_BACKGROUND, outline_color=border_color, width=1, tags="checkbox_border")
            
        label = tk.Label(internal_frame, text=text, bg=COLOR_BACKGROUND, fg=COLOR_TEXT_NORMAL,
                           font=(FONT_FAMILY, 12), cursor="hand2")
        label.pack(side=tk.LEFT, anchor='w', padx=(0, label_right_pad))
        
        # НОВОЕ: Обновляем цвет текста, если занято
        if app_ref.is_processing:
            label.config(fg=COLOR_BUTTON_TEXT_DISABLED, cursor="arrow")
            canvas.config(cursor="arrow")
        else:
            label.config(fg=COLOR_TEXT_NORMAL, cursor="hand2")
            canvas.config(cursor="hand2")


        def toggle_state(event=None):
            # НОВОЕ: Блокируем переключение, если идет процесс
            if app_ref.is_processing:
                return
            variable.set(not variable.get())
            # НОВОЕ: Запускаем проверку полей (для "Я вывел jpg")
            app_ref.check_input_fields()
        
        variable.trace_add('write', lambda *args: draw_indicator())
        
        canvas.bind("<Button-1>", toggle_state)
        label.bind("<Button-1>", toggle_state)
        internal_frame.bind("<Button-1>", toggle_state)
        
        draw_indicator()
        return (internal_frame, canvas, label)

    # ====================================================================
    # UI Setup
    # ====================================================================
    def setup_ui(self):
        main_frame = tk.Frame(self.master, bg=COLOR_BACKGROUND)
        main_frame.pack(pady=(20, 10), padx=20, fill="both", expand=True) # ИСПРАВЛЕНИЕ: Уменьшен нижний отступ
            
        for i in range(4):
            main_frame.grid_columnconfigure(i, weight=1)
            
        # ЛОГОТИП И ЗАГОЛОВОК
        header_frame = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        header_frame.grid(row=1, column=0, columnspan=4, sticky='w', padx=10, pady=(10, 20))
        
        try:
            original_image = Image.open(resource_path("assets/logo.png"))
            logo_height = 38 
            aspect_ratio = original_image.width / original_image.height
            logo_width = int(logo_height * aspect_ratio)
            resized_image = original_image.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
            self.logo_image = ImageTk.PhotoImage(resized_image)
            logo_label = tk.Label(header_frame, image=self.logo_image, bg=COLOR_BACKGROUND)
            logo_label.pack(side=tk.LEFT, padx=(0, 0))
        except:
            tk.Label(header_frame, text="ВЫПУСК.РУ",
                         font=(FONT_FAMILY, 24, 'bold'),
                         fg=COLOR_ACCENT_PINK, bg=COLOR_BACKGROUND).pack(side=tk.LEFT)
            
        row = 2
        
        # --------------------------------------------------------------------------
        # ИЗМЕНЕНИЕ: Поля 1 и 2 (Номер заказа, Дата) - ТЕПЕРЬ НАВЕРХУ
        # --------------------------------------------------------------------------
        dual_field_container_1 = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        dual_field_container_1.grid(row=row, column=0, columnspan=4, sticky='ew', padx=10, pady=BLOCK_PADY_VERTICAL)
        dual_field_container_1.grid_columnconfigure(0, weight=1)
        dual_field_container_1.grid_columnconfigure(1, weight=0)
        dual_field_container_1.grid_columnconfigure(2, weight=1)

        f_order = FloatingLabelEntry(dual_field_container_1, "Номер заказа", FONT_FAMILY, 
                                         initial_value=self.config_data.get('order_number', ''), 
                                         on_change_callback=self.check_input_fields)
        f_order.grid(row=0, column=0, sticky='ew')
        self.entries["Номер заказа"] = f_order

        tk.Frame(dual_field_container_1, width=20, bg=COLOR_BACKGROUND).grid(row=0, column=1, sticky='ns')

        f_date = FloatingLabelEntry(dual_field_container_1, "Дата", FONT_FAMILY, on_change_callback=self.check_input_fields)
        f_date.grid(row=0, column=2, sticky='ew')
        self.entries["Дата"] = f_date
        
        # Устанавливаем текущую дату
        config_date = self.config_data.get('date', datetime.datetime.now().strftime("%d.%m.%Y"))
            
        f_date.entry.delete(0, tk.END)
        f_date.entry.insert(0, config_date)
        f_date._float_label(initial_call=True)
        f_date.entry.config(fg=COLOR_TEXT_NORMAL)
        row += 1 
        
        # --------------------------------------------------------------------------
        # ИЗМЕНЕНИЕ: Поля 3 и 4 (Номер школы, Класс) - ТЕПЕРЬ НАВЕРХУ
        # --------------------------------------------------------------------------
        dual_field_container_2 = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        dual_field_container_2.grid(row=row, column=0, columnspan=4, sticky='ew', padx=10, pady=BLOCK_PADY_VERTICAL)
        dual_field_container_2.grid_columnconfigure(0, weight=1) 
        dual_field_container_2.grid_columnconfigure(1, weight=0)
        dual_field_container_2.grid_columnconfigure(2, weight=1)

        f_school = FloatingLabelEntry(dual_field_container_2, "Номер школы", FONT_FAMILY, 
                                          initial_value=self.config_data.get('school_number', ''), 
                                          on_change_callback=self.check_input_fields)
        f_school.grid(row=0, column=0, sticky='ew')
        self.entries["Номер школы"] = f_school

        tk.Frame(dual_field_container_2, width=20, bg=COLOR_BACKGROUND).grid(row=0, column=1, sticky='ns')

        f_class = FloatingLabelEntry(dual_field_container_2, "Класс", FONT_FAMILY, 
                                         initial_value=self.config_data.get('class_name', ''), 
                                         on_change_callback=self.check_input_fields)
        f_class.grid(row=0, column=2, sticky='ew')
        self.entries["Класс"] = f_class
        row += 1
        
        # --------------------------------------------------------------------------
        # 5. Путь к съемке (PathSelector) - ТЕПЕРЬ НИЖЕ
        # --------------------------------------------------------------------------
        self.path_shooting_sel = PathFileSelector(main_frame, "Выберите путь к съемке", FONT_FAMILY, 
                                                    select_dir=True, 
                                                    initial_value=self.shooting_path,
                                                    on_select_callback=lambda path: self._update_paths_and_check_fields(path, 'shooting_path'))
        self.path_shooting_sel.grid(row=row, column=0, columnspan=4, padx=10, pady=BLOCK_PADY_VERTICAL, sticky='ew')
        self.entries["Путь к съемке"] = self.path_shooting_sel # Для блокировки
        row += 1
        
        # --------------------------------------------------------------------------
        # 6. Файл отбора (ОТОБРАЖЕНИЕ) - ТЕПЕРЬ НИЖЕ
        # --------------------------------------------------------------------------
        self.path_selection_file = PathFileSelector(main_frame, "Файл отбора", FONT_FAMILY, 
                                                  select_dir=False, 
                                                  allow_multiple=False, # Только один файл
                                                  initial_value="", # Всегда пусто при старте
                                                  on_select_callback=lambda path: self._update_paths_and_check_fields(path, 'selection_file'))
        
        # ИЗМЕНЕНИЕ: Меняем тип файла для диалога
        self.path_selection_file.select_path_or_file = lambda event=None: self._select_txt_file(self.path_selection_file)

        self.path_selection_file.grid(row=row, column=0, columnspan=4, padx=10, pady=BLOCK_PADY_VERTICAL, sticky='ew')
        self.path_selection_file.entry.config(cursor="hand2") 
        
        self.entries["Файл отбора"] = self.path_selection_file # Сохраняем для обновления и блокировки
        row += 1
        
        
        # --------------------------------------------------------------------------
        # 7. НОВЫЕ Чекбоксы (Копирование)
        # --------------------------------------------------------------------------
        checkbox_container_top = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        checkbox_container_top.grid(row=row, column=0, columnspan=4, sticky='w', padx=10, pady=(20,0))
        
        # Чекбокс 1
        self.cb_widgets_selected_raw = self.create_styled_checkbox_in_frame(
            checkbox_container_top, "Скопировать отобранные raw", 
            self.var_copy_selected_raw, self, 0, 0, 1, 4
        )
        
        # Чекбокс 2
        # ИСПРАВЛЕНИЕ: Текст возвращен к оригиналу
        self.cb_widgets_all_raw_jpg = self.create_styled_checkbox_in_frame(
            checkbox_container_top, "Скопировать все raw и jpg", 
            self.var_copy_all_raw_jpg, self, 1, 0, 1, 4
        )
        row += 1
        
        # --------------------------------------------------------------------------
        # 8. Кнопка 1 (Генерация)
        # --------------------------------------------------------------------------
        button_container_1 = tk.Frame(main_frame, bg=COLOR_BACKGROUND, height=BUTTON_HEIGHT)
        button_container_1.grid(row=row, column=0, columnspan=4, padx=10, pady=(15, 10), sticky='ew')
        button_container_1.pack_propagate(False)

        self.canvas_gen = tk.Canvas(button_container_1, bd=0, highlightthickness=0, bg=COLOR_BACKGROUND)
        self.canvas_gen.pack(fill='both', expand=True)

        self.generate_button = tk.Button(state=tk.DISABLED) # Dummy
        
        self.canvas_gen.bind("<Configure>", lambda e: self.draw_button(self.canvas_gen, self.generate_button['state'], "Сгенерировать структуру"))
        # ИЗМЕНЕНИЕ: Вызываем новую "главную" функцию
        self.canvas_gen.bind("<Button-1>", lambda e: self.start_generation_process() if self.generate_button['state'] == tk.NORMAL and not self.is_processing else None)
        self.canvas_gen.config(cursor="hand2")
        
        row += 1
        
        # --------------------------------------------------------------------------
        # 9. НОВЫЙ Чекбокс ("Я вывел jpg")
        # --------------------------------------------------------------------------
        checkbox_container_bottom = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        checkbox_container_bottom.grid(row=row, column=0, columnspan=4, sticky='w', padx=10, pady=(10, 0))

        self.cb_widgets_jpg_exported = self.create_styled_checkbox_in_frame(
            checkbox_container_bottom, "Я вывел jpg файлы", 
            self.var_jpg_exported, self, 0, 0, 1, 4
        )
        # Этот чекбокс будет отслеживаться в check_input_fields
        row += 1

        # --------------------------------------------------------------------------
        # 10. Кнопка 2 (Разложить JPG)
        # --------------------------------------------------------------------------
        button_container_3 = tk.Frame(main_frame, bg=COLOR_BACKGROUND, height=BUTTON_HEIGHT)
        button_container_3.grid(row=row, column=0, columnspan=4, padx=10, pady=(10, 15), sticky='ew')
        button_container_3.pack_propagate(False)

        self.canvas_sort = tk.Canvas(button_container_3, bd=0, highlightthickness=0, bg=COLOR_BACKGROUND)
        self.canvas_sort.pack(fill='both', expand=True)

        self.sort_button = tk.Button(state=tk.DISABLED) # Dummy
        
        self.canvas_sort.bind("<Configure>", lambda e: self.draw_button(self.canvas_sort, self.sort_button['state'], "Разложить JPG по папкам"))
        # ИЗМЕНЕНИЕ: Вызываем новую потоковую функцию
        self.canvas_sort.bind("<Button-1>", lambda e: self.start_sort_jpgs() if self.sort_button['state'] == tk.NORMAL and not self.is_processing else None)
        self.canvas_sort.config(cursor="hand2")
        
        row += 1

        # --------------------------------------------------------------------------
        # 11. Метка статуса (Внизу)
        # --------------------------------------------------------------------------
        self.status_label = tk.Label(main_frame, text="", anchor="w",
                                      fg=COLOR_STATUS_NORMAL, bg=COLOR_BACKGROUND,
                                      font=(FONT_FAMILY, 10))
        self.status_label.grid(row=row, column=0, columnspan=4, sticky='ew', padx=10, pady=(10,0))
        row += 1

        self.master.after_idle(self.check_input_fields)


    # ====================================================================
    # ЛОГИКА ФАЙЛОВЫХ ОПЕРАЦИЙ И ВАЛИДАЦИЯ
    # ====================================================================

    def _sanitize_folder_name(self, name):
        """Удаляет символы, недопустимые в именах папок (Windows/Unix, заменяя их на тире."""
        name = re.sub(r'[\\/:\*\?"<>\|]', '-', name)
        name = name.rstrip(' .')
        return name.strip()

    def set_default_path(self):
        """Устанавливает путь для сохранения структуры (Desktop/Home)."""
        # ИЗМЕНЕНИЕ: output_path теперь всегда = shooting_path, но по умолчанию Desktop
        if not self.output_path: # Устанавливаем только при запуске, если пустой
            if sys.platform == "win32":
                desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
                if not os.path.exists(desktop):
                    desktop = os.path.expanduser('~')
            else:
                desktop = os.path.expanduser('~')
            self.output_path = desktop
            
    def select_path(self):
        """Больше не используется, так как output_path = shooting_path"""
        pass
    
    def _update_paths_and_check_fields(self, paths_or_path, identifier):
        """Обрабатывает выбор пути к съемке или файлов отбора."""
        if identifier == 'shooting_path':
            self.shooting_path = paths_or_path
            # ИЗМЕНЕНИЕ: Устанавливаем output_path
            self.output_path = self.shooting_path
            
            # НОВОЕ: Пытаемся авто-загрузить данные
            self._try_autoload_data(self.shooting_path)
            
            # НОВОЕ: Автоматическое создание/проверка TXT-файла
            self._create_selection_file_template()
            
            # ДОБАВЛЕНИЕ: Гарантируем, что selection_file_path установлен корректно
            expected_path = self._get_expected_selection_file_path()
            if expected_path:
                self.selection_file_path = expected_path

        elif identifier == 'selection_file':
            self.selection_file_path = paths_or_path
            
        self.check_input_fields()

    def _set_checkbox_state(self, cb_widgets, new_state):
        """Включает/выключает кастомный чекбокс."""
        if not cb_widgets:
            return
            
        (frame, canvas, label) = cb_widgets
        
        # Просто перерисовываем, 'draw_indicator' сам проверит self.is_processing
        # Находим 'variable'
        if cb_widgets == self.cb_widgets_selected_raw:
            self.var_copy_selected_raw.set(self.var_copy_selected_raw.get())
        elif cb_widgets == self.cb_widgets_all_raw_jpg:
            self.var_copy_all_raw_jpg.set(self.var_copy_all_raw_jpg.get())
        elif cb_widgets == self.cb_widgets_jpg_exported:
            self.var_jpg_exported.set(self.var_jpg_exported.get())


    def check_input_fields(self):
        """Проверяет заполнение полей и активирует/деактивирует кнопки."""
        order_num = self._sanitize_folder_name(self.entries["Номер заказа"].get())
        class_name = self._sanitize_folder_name(self.entries["Класс"].get())
        shooting_path_valid = self.shooting_path and os.path.isdir(self.shooting_path)
        
        selection_file_exists = self.selection_file_path and os.path.exists(self.selection_file_path)

        # --- КНОПКА 1: Сгенерировать структуру ---
        is_gen_complete = all([order_num, class_name]) and shooting_path_valid
        
        # Блокируем, если идет процесс ИЛИ поля не заполнены
        new_state_gen = tk.DISABLED if self.is_processing else (tk.NORMAL if is_gen_complete else tk.DISABLED)

        # ИСПРАВЛЕНИЕ (КНОПКИ НЕ ВИДНЫ):
        # Принудительно обновляем состояние И перерисовываем кнопку КАЖДЫЙ РАЗ.
        self.generate_button.config(state=new_state_gen)
        self.draw_button(self.canvas_gen , new_state_gen, "Сгенерировать структуру")

        # --- КНОПКА 2: Разложить JPG по папкам ---
        
        # Условия: путь, файл отбора, И нажат чекбокс "Я вывел"
        is_sort_complete = all([shooting_path_valid, selection_file_exists, self.var_jpg_exported.get()])
        
        # Блокируем, если идет процесс ИЛИ условия не выполнены
        new_state_sort = tk.DISABLED if self.is_processing else (tk.NORMAL if is_sort_complete else tk.DISABLED)

        # ИСПРАВЛЕНИЕ (КНОПКИ НЕ ВИДНЫ):
        # Принудительно обновляем состояние И перерисовываем кнопку КАЖДЫЙ РАЗ.
        self.sort_button.config(state=new_state_sort)
        self.draw_button(self.canvas_sort, new_state_sort, "Разложить JPG по папкам")
            
        # --- БЛОКИРОВКА ПОЛЕЙ И ЧЕКБОКСОВ ---
        fields_state = tk.DISABLED if self.is_processing else tk.NORMAL
        for entry_widget in self.entries.values():
            entry_widget.set_state(fields_state)
            
        self._set_checkbox_state(self.cb_widgets_selected_raw, fields_state)
        self._set_checkbox_state(self.cb_widgets_all_raw_jpg, fields_state)
        self._set_checkbox_state(self.cb_widgets_jpg_exported, fields_state)
            
        # Обновление статуса
        if self.is_processing:
            # Не меняем статус, если он уже показывает прогресс
            pass
        # ИСПРАВЛЕНИЕ (УБРАТЬ ПОДСКАЗКУ НА СТАРТЕ):
        elif not shooting_path_valid and not order_num and not class_name:
             self._update_status("", is_error=False) # Ничего не выводим при чистом старте
        elif not shooting_path_valid:
             self._update_status("Выберите Путь к съемке.", is_error=False) # Не ошибка
        elif not selection_file_exists:
             self._update_status("Файл 'selected.txt' не найден (выберите Путь к съемке).", is_error=False) # Не ошибка
        elif not order_num or not class_name:
             self._update_status("Введите Номер заказа и Класс.", is_error=False) # Не ошибка
        else:
            self._update_status("Готово к работе.", is_error=False)


    # ====================================================================
    # ЛОГИКА ОБРАБОТКИ ОТЧЕТА (СОЗДАНИЕ ШАБЛОНА)
    # ====================================================================
    
    def _get_expected_selection_file_path(self):
        """Формирует ожидаемый путь к файлу отбора."""
        if not self.shooting_path or not os.path.isdir(self.shooting_path):
            return None
        # ИЗМЕНЕНИЕ: Имя файла теперь "selected.txt"
        filename = "selected.txt"
        return os.path.join(self.shooting_path, filename)

    # ИЗМЕНЕНИЕ: Автоматическое создание TXT-файла
    def _create_selection_file_template(self):
        """Создает ПУСТОЙ TXT-шаблон со всеми секциями и ИНСТРУКЦИЯМИ."""
        
        if not self.shooting_path or not os.path.isdir(self.shooting_path):
             return

        selection_path = self._get_expected_selection_file_path()
        self.selection_file_path = selection_path
        
        # ИЗМЕНЕНИЕ: Обновленный шаблон согласно запросу пользователя
        mock_data = f"""# ИНСТРУКЦИЯ: Заполните этот файл вручную.
#
# --------------------------------------------------
УЧЕНИКИ
# 5 Колонок: [Виньетка] [Портрет 1] [Портрет 2] [Друг 1] [Друг 2]
# Если фото нет, ставьте 0 или -.
# --------------------------------------------------
Иванов Иван 102 105 - 110 112

# --------------------------------------------------
УЧИТЕЛЯ
# Формат: ФИО учитель Предмет [Номер]
# --------------------------------------------------
Иванова Марья Васильевна учитель истории 401 

# --------------------------------------------------
ОБЩАЯ ФОТОГРАФИЯ
# Формат: общая [Номер 1] [Номер 2]
# --------------------------------------------------
общая 501

# --------------------------------------------------
ГРУППОВЫЕ / РЕПОРТАЖ
# Формат: репортаж [Номер 1] [Номер 2] ...
# --------------------------------------------------
репортаж 601 

# --------------------------------------------------
ФОН
# Формат: фон [Номер]
# --------------------------------------------------
фон 901
"""
        try:
            # 1. Проверяем, существует ли файл до попытки создания
            file_was_created = not os.path.exists(selection_path)
            
            # 2. Создаем файл, только если он не существует
            if file_was_created: 
                with open(selection_path, 'w', encoding='utf-8') as f:
                    f.write(mock_data)
            
            # Обновляем поле "Файл отбора"
            entry_widget = self.entries.get("Файл отбора")
            if entry_widget:
                entry_widget.entry.config(state='normal')
                entry_widget.entry.delete(0, tk.END)
                # Показываем только имя файла в поле ввода
                entry_widget.entry.insert(0, os.path.basename(selection_path))
                entry_widget.entry.config(state='readonly')
                entry_widget._float_label(initial_call=True)

            
            # 3. НОВОЕ: Открываем файл, только если он был только что создан
            if file_was_created:
                try:
                    # АВТОМАТИЧЕСКОЕ ОТКРЫТИЕ ФАЙЛА ДЛЯ РЕДАКТИРОВАНИЯ
                    if sys.platform == "win32": subprocess.Popen(['notepad.exe', selection_path])
                    elif sys.platform == "darwin": subprocess.Popen(["open", selection_path])
                    else: subprocess.Popen(["xdg-open", selection_path])
                    
                    self._update_status(f"Файл отбора создан и открыт: {os.path.basename(selection_path)}.", is_error=False) 
                except Exception as open_e:
                     print(f"Ошибка при попытке открыть файл: {open_e}")
                     self._update_status(f"Файл отбора найден, но не открыт: {os.path.basename(selection_path)}.", is_error=True) 
            
        except Exception as e:
            self._update_status(f"Ошибка создания/обновления файла отбора: {e}", is_error=True)
            
        # self.check_input_fields() # Убрано, т.к. вызовется в _update_paths...

    # ИЗМЕНЕНИЕ: Кастомный селектор для TXT-файлов
    def _select_txt_file(self, selector_widget):
        """Открывает диалог выбора TXT-файла."""
        
        # НОВОЕ: Если виджет отключен, ничего не делаем
        if selector_widget.entry.cget('state') == tk.DISABLED:
            return

        initial_dir = self.shooting_path or os.path.expanduser('~')
        
        path_selected = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="Выберите файл отбора",
            filetypes=[("Файлы отбора", "*.txt")] # ИСПРАВЛЕНИЕ: Показываем только TXT
        )
        
        if path_selected:
            selector_widget.entry.config(state='normal')
            selector_widget.entry.delete(0, tk.END)
            selector_widget.entry.insert(0, os.path.basename(path_selected)) # Показываем только имя файла
            selector_widget.entry.config(state='readonly')
            selector_widget._float_label(initial_call=True)
            
            # Вызываем коллбэк
            if selector_widget.on_select_callback:
                selector_widget.on_select_callback(path_selected)
                
    # НОВОЕ: Открытие файла (для PathFileSelector)
    def _open_selection_file(self):
        if self.selection_file_path and os.path.exists(self.selection_file_path):
            try:
                # Открываем папку, в которой находится файл selected.txt
                folder_path = os.path.dirname(self.selection_file_path)
                if sys.platform == "win32":
                    # На Windows пытаемся открыть папку и выделить файл (более удобный UX)
                    subprocess.Popen(['explorer', '/select,', self.selection_file_path]) 
                elif sys.platform == "darwin": # macOS
                    subprocess.Popen(["open", folder_path])
                else: # Linux/UNIX
                    subprocess.Popen(["xdg-open", folder_path])
            except Exception as e:
                self._update_status(f"Не удалось открыть папку с файлом: {e}", is_error=True)
        else:
             self._update_status("Файл отбора не найден. Выберите 'Путь к съемке'.", is_error=True)


    def _read_selection_from_file(self, file_path=None):
        """Читает и парсит данные из TXT-файла отбора, разделяя по категориям."""
        path_to_read = file_path if file_path else self.selection_file_path
        
        if not path_to_read or not os.path.exists(path_to_read):
            return {} 

        selection_data = {
            "Ученики": {}, "Учителя": {}, "Общая": {}, "Групповые": {}, "Фон": {} 
        }
        current_category = None
        
        try:
            # ИЗМЕНЕНИЕ: Используем 'utf-8-sig' для обработки BOM (от Блокнота)
            with open(path_to_read, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    
                    # ИЗМЕНЕНИЕ: Сначала убираем #, потом проверяем на пустоту
                    if line.startswith('#') or line.startswith('-'):
                        continue
                        
                    if not line:
                        continue

                    # --- 1. Определение категории ---
                    if "УЧЕНИКИ" in line:
                        current_category = "Ученики"
                        continue
                    elif "УЧИТЕЛЯ" in line:
                        current_category = "Учителя"
                        continue
                    elif "ОБЩАЯ ФОТОГРАФИЯ" in line:
                        current_category = "Общая"
                        continue
                    elif "ГРУППОВЫЕ" in line or "РЕПОРТАЖ" in line:
                        current_category = "Групповые"
                        continue
                    elif "ФОН" in line: # НОВАЯ СЕКЦИЯ
                        current_category = "Фон"
                        continue

                    # ИЗМЕНЕНИЕ: Логика парсинга БЕЗ двоеточия
                    if current_category:
                        # Ищем первое число в строке
                        match = re.search(r'\d+', line)
                        
                        if not match:
                            continue # Строка без номеров, пропускаем

                        name_part = line[:match.start()].strip()
                        num_part = line[match.start():].strip()
                        
                        # Если name_part пустой (например, в строке "общая 501"), 
                        # а ключ - это сама категория (кроме учеников и учителей)
                        if not name_part and current_category not in ["Ученики", "Учителя"]:
                            name_part = current_category.lower()


                        numbers = [int(n) for n in re.findall(r'\d+', num_part) if int(n) > 0]
                        
                        if not numbers: continue 

                        # --- НОВОЕ: Чтение и сохранение позиций учеников ---
                        if current_category == "Ученики":
                            student_name = self._sanitize_folder_name(name_part)
                            if student_name:
                                # 1. Извлекаем все части (включая прочерки)
                                # ИСПРАВЛЕНИЕ: Используем split() на чистой строке, чтобы получить части
                                raw_line_parts = re.split(r'\s+', line)
                                # Находим начало номеров
                                name_words_count = len(student_name.split())
                                number_parts = raw_line_parts[name_words_count:]
                                
                                position_map = {} # {102: 0, 105: 1, 110: 3, 112: 4}
                                for i, part in enumerate(number_parts):
                                    # Нас интересуют только числа > 0
                                    if part.isdigit() and int(part) > 0:
                                        # i — это индекс позиции (0, 1, 2, 3, 4).
                                        if i >= 5: continue # Игнорируем лишние номера
                                        position_map[int(part)] = i 
                                
                                # Если map не пуста, добавляем ученика
                                if position_map:
                                    # Мы сохраняем не номера, а именно карту позиций в self.selection_map
                                    selection_data["Ученики"][student_name] = position_map
                                    
                        else:
                            description = self._sanitize_folder_name(name_part) # Используем name_part как ключ
                            if description:
                                # Для остальных категорий (где нет 5 позиций), сохраняем как обычно (список номеров)
                                if description in selection_data[current_category]:
                                    selection_data[current_category][description].extend(numbers)
                                else:
                                    selection_data[current_category][description] = numbers
                                
        except Exception as e:
            # ИЗМЕНЕНИЕ: Не показываем messagebox из потока, а бросаем исключение
            raise Exception(f"Не удалось прочитать или разобрать файл отбора: {e}")
            
        return selection_data

    # ====================================================================
    # НОВОЕ: АВТО-ЗАГРУЗКА ДАННЫХ
    # ====================================================================

    def _autofill_fields(self, order, date, school, class_name):
        """Безопасно заполняет поля на UI."""
        try:
            # Номер заказа
            f_order = self.entries["Номер заказа"]
            f_order.entry.config(state='normal')
            f_order.entry.delete(0, tk.END)
            f_order.entry.insert(0, order)
            f_order._force_float() # Используем _force_float

            # Дата
            f_date = self.entries["Дата"]
            f_date.entry.config(state='normal')
            f_date.entry.delete(0, tk.END)
            f_date.entry.insert(0, date)
            f_date._force_float() # Используем _force_float
            f_date.entry.config(fg=COLOR_TEXT_NORMAL) # Важно для даты

            # Номер школы
            f_school = self.entries["Номер школы"]
            f_school.entry.config(state='normal')
            f_school.entry.delete(0, tk.END)
            f_school.entry.insert(0, school)
            f_school._force_float() # Используем _force_float

            # Класс
            f_class = self.entries["Класс"]
            f_class.entry.config(state='normal')
            f_class.entry.delete(0, tk.END)
            f_class.entry.insert(0, class_name)
            f_class._force_float() # Используем _force_float
            
            self._update_status("Данные из существующей структуры загружены.", is_error=False)
            self.check_input_fields()
        except Exception as e:
            print(f"Ошибка автозаполнения полей: {e}")
            self._update_status("Ошибка автозаполнения полей.", is_error=True)

    def _try_autoload_data(self, base_path):
        """Пытается найти и загрузить данные из существующей структуры папок."""
        try:
            for order_num in os.listdir(base_path):
                path1 = os.path.join(base_path, order_num)
                if not os.path.isdir(path1) or order_num.startswith('.'):
                    continue
                
                # Ищем .../[OrderNum]/[OrderNum]
                path2 = os.path.join(path1, order_num)
                if not os.path.isdir(path2):
                    continue

                # Ищем .../Школа
                school_dirs = [d for d in os.listdir(path2) if os.path.isdir(os.path.join(path2, d)) and not d.startswith('.')]
                if not school_dirs:
                    continue
                school_num = school_dirs[0] # Берем первую
                path3 = os.path.join(path2, school_num)

                # Ищем .../Дата
                date_dirs = [d for d in os.listdir(path3) if os.path.isdir(os.path.join(path3, d)) and not d.startswith('.')]
                if not date_dirs:
                    continue
                date = date_dirs[0]
                path4 = os.path.join(path3, date)

                # Ищем .../Класс
                class_dirs = [d for d in os.listdir(path4) if os.path.isdir(os.path.join(path4, d)) and not d.startswith('.')]
                if not class_dirs:
                    continue
                class_name = class_dirs[0]
                
                # Если мы дошли сюда, мы нашли полную структуру!
                # Вызываем автозаполнение в основном потоке
                self.master.after(0, self._autofill_fields, order_num, date, school_num, class_name)
                return True # Останавливаем поиск
                
        except Exception as e:
            # Ошибки (например, Permission Denied) игнорируются
            print(f"Ошибка при авто-сканировании папок: {e}")
        
        return False

    # ====================================================================
    # ЭТАП 1: ГЕНЕРАЦИЯ СТРУКТУРЫ (И КОПИРОВАНИЕ)
    # ====================================================================
    
    def start_generation_process(self):
        """
        Запускает ГЛАВНЫЙ процесс генерации и копирования в отдельном потоке.
        """
        
        # 1. Проверка и подготовка (Остается в главном потоке)
        order_num = self._sanitize_folder_name(self.entries["Номер заказа"].get())
        if not order_num:
            messagebox.showerror("Ошибка", "Номер заказа не заполнен.")
            return
            
        # КРИТИЧНОЕ ИСПРАВЛЕНИЕ: Проверяем, что внутренняя переменная selection_file_path установлена
        # Она нужна, даже если "Скопировать отобранные" выключено (для папок учеников)
        if not self.selection_file_path or not os.path.exists(self.selection_file_path):
             messagebox.showerror("Ошибка", "Файл отбора не найден.")
             return
            
        self.output_path = self.shooting_path
        if not self.output_path or not os.path.isdir(self.output_path):
            messagebox.showerror("Ошибка", "Путь к съемке недействителен.")
            return
            
        # Получаем состояния чекбоксов ПЕРЕД запуском потока
        run_copy_selected = self.var_copy_selected_raw.get()
        run_copy_all = self.var_copy_all_raw_jpg.get()
    
        # 2. Блокировка UI
        self.is_processing = True # Установка флага
        self.current_task_canvas = self.canvas_gen # <--- ИСПРАВЛЕНИЕ (ЗАВИСШИЕ КНОПКИ)
        self.check_input_fields() # Обновление состояния кнопок
        
        self.master.after(0, self._update_status, "Начало...", False)

        # 3. Запуск задачи в отдельном потоке
        copy_thread = threading.Thread(
            target=self._generation_task, 
            args=(order_num, run_copy_selected, run_copy_all),
            daemon=True
        )
        copy_thread.start()

    def _generation_task(self, order_num, run_copy_selected, run_copy_all):
        """
        Фоновая задача: ВЫПОЛНЯЕТ ВСЕ задачи (генерация, копирование 1, копирование 2).
        """
        
        # --- ОБЩИЙ КОЛБЭК ДЛЯ СТАТУСА ---
        def on_progress(message, percent):
            self.master.after(0, self._update_status, message, False)
        
        try:
            # --- Подсчет общего кол-ва шагов ---
            total_steps = 1 # 1 for structure
            if run_copy_selected:
                total_steps += 1
            if run_copy_all:
                total_steps += 2 # 1 for RAW, 1 for JPG
            current_step = 0

            # --- ЧАСТЬ 0: Чтение данных (нужно для папок учеников) ---
            on_progress("Чтение файла отбора...", 0)
            try:
                self.selection_data = self._read_selection_from_file()
            except Exception as e:
                # Если файл отбора не читается, мы НЕ МОЖЕМ продолжать
                raise Exception(f"Ошибка чтения selected.txt: {e}")

            # --- ЧАСТЬ 1: Генерация структуры (Всегда выполняется) ---
            current_step += 1
            on_progress(f"Этап {current_step}/{total_steps}: Создание структуры папок...", 0)
            
            # Получаем список учеников из (уже прочитанных) данных
            students_map = self.selection_data.get("Ученики", {})
            students = list(students_map.keys())
            
            try:
                structure_text = self._build_structure(order_num, students)
                self._create_folders_from_structure(self.output_path, structure_text)
            except Exception as e:
                raise Exception(f"Ошибка создания структуры: {e}")

            # --- ЧАСТЬ 2: Копирование ОТОБРАННЫХ RAW (Если отмечено) ---
            if run_copy_selected:
                current_step += 1
                target_raw_dir = os.path.join(self.output_path, order_num, f"{order_num} дубли равы", "отобранный материал")
                
                # НОВОЕ: Проверка на существование
                if os.path.isdir(target_raw_dir) and os.listdir(target_raw_dir):
                    on_progress(f"Этап {current_step}/{total_steps}: Пропущено (отобранные RAW уже скопированы).", 0)
                else:
                    on_progress(f"Этап {current_step}/{total_steps}: Копирование отобранных RAW...", 0)
                    (message, is_error, not_found_files) = self._perform_selected_raw_copy_logic(
                        target_raw_dir, 
                        on_progress
                    )
                    if is_error:
                        raise Exception(message)
                    if not_found_files:
                         self.master.after(0, messagebox.showwarning, "Внимание", f"Не удалось найти следующие номера файлов (RAW): {', '.join(not_found_files)}")
                    
                    # ИСПРАВЛЕНИЕ (ОТКРЫТИЕ ПАПКИ): Открываем папку, куда были скопированы файлы
                    self.master.after(0, self._open_target_folder_after_copy, target_raw_dir)


            # --- ЧАСТЬ 3: Копирование ВСЕХ RAW и JPG (Если отмечено) ---
            if run_copy_all:
                # --- ЧАСТЬ 3.1: Копирование ВСЕХ RAW ---
                current_step += 1
                target_all_raw_dir = os.path.join(self.output_path, order_num, f"{order_num} дубли равы", "дубли")
                
                if os.path.isdir(target_all_raw_dir) and os.listdir(target_all_raw_dir):
                     on_progress(f"Этап {current_step}/{total_steps}: Пропущено (Все RAW уже скопированы).", 0)
                else:
                    on_progress(f"Этап {current_step}/{total_steps}: Копирование ВСЕХ RAW (в 'дубли равы/дубли')...", 0)
                    (message_raw, is_error_raw) = self._perform_all_raw_copy_logic(
                        self.shooting_path, # Откуда
                        target_all_raw_dir,    # Куда
                        on_progress
                    )
                    if is_error_raw:
                        raise Exception(message_raw)
                    
                # --- ЧАСТЬ 3.2: Копирование ВСЕХ JPG ---
                current_step += 1
                target_all_jpg_dir = os.path.join(self.output_path, order_num, f"{order_num} дубли")

                if os.path.isdir(target_all_jpg_dir) and os.listdir(target_all_jpg_dir):
                    on_progress(f"Этап {current_step}/{total_steps}: Пропущено (Все JPG уже скопированы).", 0)
                else:
                    on_progress(f"Этап {current_step}/{total_steps}: Копирование ВСЕХ JPG (в 'дубли')...", 0)
                    (message_jpg, is_error_jpg) = self._perform_all_jpg_copy_logic(
                        self.shooting_path, # Откуда
                        target_all_jpg_dir,    # Куда
                        on_progress
                    )
                    if is_error_jpg:
                        raise Exception(message_jpg)

            # --- ЗАВЕРШЕНИЕ ---
            # ИЗМЕНЕНИЕ: Улучшенное сообщение
            final_msg = "УСПЕХ! Структура проверена и обновлена."
            if not run_copy_selected and not run_copy_all:
                final_msg = "УСПЕХ! Структура папок создана."
                
            self.master.after(0, self._on_generation_complete, final_msg, False, order_num)

        except Exception as e:
            # Обработка любой ошибки из try
            self.master.after(0, self._on_generation_complete, f"ОШИБКА: {e}", True, order_num)

    # ИСПРАВЛЕНИЕ (ОТКРЫТИЕ ПАПКИ): Новая/измененная функция
    def _open_target_folder_after_copy(self, folder_path):
        """Открывает папку 'отобранный материал' (вызывается в главном потоке)"""
        self._update_status(f"Открытие папки 'отобранный материал'...", is_error=False) 
        try:
            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin": # macOS
                subprocess.Popen(["open", folder_path])
            else: # Linux/UNIX
                subprocess.Popen(["xdg-open", folder_path])
        except Exception as e:
            print(f"Ошибка при попытке открыть папку: {e}")
            self._update_status("Папка 'отобранный материал' скопирована, но не открыта.", is_error=True)


    def _on_generation_complete(self, message, is_error, order_num):
        """
        Восстанавливает UI после завершения ГЕНЕРАЦИИ, показывает статус.
        """
        # 1. Восстановление кнопок
        self.is_processing = False # Снятие флага
        self.current_task_canvas = None # <--- ИСПРАВЛЕНИЕ (ЗАВИСШИЕ КНОПКИ)
        self.check_input_fields() # Восстановление состояния кнопок
        self._update_status(message, is_error=is_error)
        self.save_config() # Сохраняем конфиг
        
        # ИСПРАВЛЕНИЕ (ОТКРЫТИЕ ПАПКИ): Убрано открытие папки отсюда
        
    # --- Логика для ЭТАПА 1 (Генерация) ---

    def _perform_selected_raw_copy_logic(self, target_raw_dir, on_progress):
        """
        Фоновая ЛОГИКА: Копирует отобранные RAW-файлы.
        Вызывается из _generation_task.
        Возвращает (message, is_error, not_found_files)
        """
        
        # (self.selection_data уже прочитан в _generation_task)
        if not any(self.selection_data.values()):
             return "Ошибка: Файл отбора пуст. Заполните TXT-файл.", True, []
            
        raw_copy_count = 0
        os.makedirs(target_raw_dir, exist_ok=True)
            
        all_files_to_copy = []
        for category, items in self.selection_data.items():
            for description_or_name, numbers_or_map in items.items():
                if isinstance(numbers_or_map, dict):
                    all_files_to_copy.extend(numbers_or_map.keys())
                else:
                    all_files_to_copy.extend(numbers_or_map)
        
        unique_file_numbers = sorted(list(set(all_files_to_copy))) 
        not_found_files = []

        total_files = len(unique_file_numbers)
        on_progress(f"0%: Найдено {total_files} отобранных RAW...", 0)

        for i, num in enumerate(unique_file_numbers):
            source_file = self._find_file_by_number(self.shooting_path, num)
            if source_file:
                try:
                    # Расчет прогресса (с округлением)
                    progress_percent = int(((i + 1) / total_files) * 100)
                    file_name = os.path.basename(source_file)
                    
                    # Обновление статуса
                    status_msg = f"{progress_percent}%: (Отбор) {file_name}..."
                    on_progress(status_msg, progress_percent)
                    
                    shutil.copy2(source_file, target_raw_dir) 
                    raw_copy_count += 1
                except Exception as e:
                    print(f"Ошибка копирования {source_file}: {e}")
            else:
                not_found_files.append(str(num))
                        
        final_msg = f"УСПЕХ! Скопировано {raw_copy_count} отобранных RAW."
        return final_msg, False, not_found_files

    def _perform_all_raw_copy_logic(self, source_dir, target_dir, on_progress):
        """
        Фоновая ЛОГИКА: Копирует ВСЕ RAW. (Переименовано)
        Вызывается из _generation_task.
        Возвращает (message, is_error)
        """
        try:
            os.makedirs(target_dir, exist_ok=True)
            
            # Собираем ВСЕ файлы (RAW) из папки съемки
            extensions_to_copy = tuple(RAW_EXTENSIONS) # <--- ТОЛЬКО RAW
            
            all_files = [
                f for f in os.listdir(source_dir) 
                if os.path.isfile(os.path.join(source_dir, f)) and f.lower().endswith(extensions_to_copy)
            ]
            
            total_files = len(all_files)
            if total_files == 0:
                return "Предупреждение: Не найдено RAW-файлов для копирования в 'дубли равы/дубли'.", False

            on_progress(f"0%: Найдено {total_files} (Все RAW)...", 0)
            
            for i, filename in enumerate(all_files):
                progress_percent = int(((i + 1) / total_files) * 100)
                on_progress(f"{progress_percent}%: (Все RAW) {filename}...", progress_percent)
                
                source_path = os.path.join(source_dir, filename)
                target_path = os.path.join(target_dir, filename)
                
                shutil.copy2(source_path, target_path)

            return f"УСПЕХ! Скопировано {total_files} (Все RAW).", False
            
        except Exception as e:
            return f"Ошибка копирования ВСЕХ RAW: {e}", True

    def _perform_all_jpg_copy_logic(self, source_dir, target_dir, on_progress):
        """
        Фоновая ЛОГИКА: Копирует ВСЕ JPG.
        Вызывается из _generation_task.
        Возвращает (message, is_error)
        """
        try:
            os.makedirs(target_dir, exist_ok=True)
            
            # Собираем ВСЕ файлы (JPG) из папки съемки
            extensions_to_copy = ('.jpg', '.jpeg') # <--- ТОЛЬКО JPG
            
            all_files = [
                f for f in os.listdir(source_dir) 
                if os.path.isfile(os.path.join(source_dir, f)) and f.lower().endswith(extensions_to_copy)
            ]
            
            total_files = len(all_files)
            if total_files == 0:
                return "Предупреждение: Не найдено JPG-файлов для копирования в 'дубли'.", False

            on_progress(f"0%: Найдено {total_files} (Все JPG)...", 0)
            
            for i, filename in enumerate(all_files):
                progress_percent = int(((i + 1) / total_files) * 100)
                on_progress(f"{progress_percent}%: (Все JPG) {filename}...", progress_percent)
                
                source_path = os.path.join(source_dir, filename)
                target_path = os.path.join(target_dir, filename)
                
                shutil.copy2(source_path, target_path)

            return f"УСПЕХ! Скопировано {total_files} (Все JPG).", False
            
        except Exception as e:
            return f"Ошибка копирования ВСЕХ JPG: {e}", True


    def _find_file_by_number(self, directory, number):
        """
        Ищет файл в директории по номеру, игнорируя расширение, но ПРЕДПОЧИТАЯ RAW.
        """
        if not directory or not os.path.isdir(directory):
            return None
            
        target_filename_part = str(number)
        
        for filename in os.listdir(directory):
            name_without_ext, ext = os.path.splitext(filename)
            ext_lower = ext.lower()
            
            # 1. Проверяем, является ли файл RAW
            if ext_lower not in RAW_EXTENSIONS:
                 continue
                 
            # 2. Проверяем совпадение номера (более надежная логика для ANT00102)
            
            # Поиск в конце имени имени файла: ищем номер (до 5 цифр)
            match = re.search(r'(\d{1,5})$', name_without_ext)
            
            if match:
                found_number = match.group(1)
                # Проверяем на прямое совпадение числами (например, 102 == 102)
                if int(found_number) == number:
                    return os.path.join(directory, filename)
                    
                # Проверяем на совпадение с ведущими нулями (например, 00102 == 102)
                if found_number.lstrip('0') == target_filename_part:
                    return os.path.join(directory, filename)
                    
        print(f"Внимание: Файл с номером {number} (RAW) не найден в {directory}")
        return None

    def _build_structure(self, order_num, students):
        """Формирует текстовое описание структуры папок для создания."""
        tab = "    "
        school_num = self._sanitize_folder_name(self.entries["Номер школы"].get())
        date = self._sanitize_folder_name(self.entries["Дата"].get())
        class_name = self._sanitize_folder_name(self.entries["Класс"].get())
        
        lines = [
            order_num,
            f"{tab}{order_num}", 
            f"{tab*2}{school_num}", 
            f"{tab*3}{date}", 
            f"{tab*4}{class_name}",
            f"{tab*5}доки", 
            f"{tab*5}здание", 
            f"{tab*5}общая", 
            f"{tab*5}репортаж", 
            f"{tab*5}учителя", 
            f"{tab*5}фон",
            f"{tab*5}ученики"
        ]
        
        # Добавляем папки для каждого ученика
        for s in students:
            lines.append(f"{tab*6}{s}")
            
        # ИЗМЕНЕНИЕ: Чекбоксы "Цитаты" и "Видео" удалены
            
        lines.extend([
            f"{tab}{order_num} дубли",
            f"{tab}{order_num} дубли равы", 
            f"{tab*2}дубли",
            f"{tab*2}отобранный материал"
        ])
        
        return "\n".join(lines)
        
    def _create_folders_from_structure(self, root_path, structure_text):
        """Создает папки на основе текстового описания структуры."""
        lines = structure_text.splitlines()
        depth_to_path = {0: root_path}
        
        for line in lines:
            new_depth = len(line) - len(line.lstrip())
            new_depth = new_depth // 4
            
            folder_name = line.strip()
            
            parent_path = None
            for i in range(new_depth - 1, -1, -1):
                if i in depth_to_path:
                    parent_path = depth_to_path[i]
                    break
            
            if not parent_path:
                parent_path = root_path

            folder_path = os.path.join(parent_path, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            depth_to_path[new_depth] = folder_path

    def _reset_ui(self):
        """Сбрасывает все поля ввода и флаги после успешной генерации."""
        
        # ИЗМЕНЕНИЕ: Обновляем список ключей
        keys_to_reset = ["Номер заказа", "Номер школы", "Класс", "Дата", "Файл отбора", "Путь к съемке"]
        for key in keys_to_reset:
            if key in self.entries:
                widget = self.entries[key]
                widget.set_state(tk.NORMAL) # Разблокируем
                
                widget.entry.config(state='normal') # Разблокируем для сброса
                widget.entry.delete(0, tk.END)
                widget._sink_label()
                
                # Восстанавливаем состояние 'readonly' для PathSelectors
                if isinstance(widget, PathFileSelector):
                    widget.entry.config(state='readonly')

        # 2. Восстанавливаем текущую дату
        f_date = self.entries["Дата"]
        today_str = datetime.datetime.now().strftime("%d.%m.%Y")
        
        # ИСПРАВЛЕНИЕ (ПРОБЛЕМА С "ДАТА"):
        # Сначала вставляем, потом принудительно поднимаем метку
        f_date.entry.insert(0, today_str)
        f_date._force_float()
        f_date.entry.config(fg=COLOR_TEXT_NORMAL) # Убеждаемся, что текст видимый

        # 3. Сбрасываем переменные состояния
        self.shooting_path = ""
        self.selection_file_path = None
        self.selection_data = {}
        
        # 4. Сбрасываем Чекбоксы
        self.var_copy_selected_raw.set(True)
        self.var_copy_all_raw_jpg.set(True)
        self.var_jpg_exported.set(False)
        
        self.check_input_fields()
        self._update_status("Сброс выполнен. Введите данные для нового заказа.", is_error=False)
        self.master.focus_set()


    # ====================================================================
    # ЭТАП 2: РАЗЛОЖИТЬ JPG ПО ПАПКАМ (СОРТИРОВКА)
    # ====================================================================

    def _get_renamed_path_and_folder(self, base_dir, filename, student_name, file_number, position_map):
        """
        Определяет целевую папку и НОВОЕ ИМЯ для файла ученика.
        Возвращает (target_folder, new_filename).
        """
        # Позиции 0, 1, 2 = переименовываются
        # Позиции 3, 4 = сохраняют оригинальное имя
        
        position_index = position_map.get(file_number)
        original_ext = os.path.splitext(filename)[1]
        
        target_folder = os.path.join(base_dir, "ученики", student_name)
        new_filename = filename # Default: оригинальное имя

        if position_index is not None:
            if 0 <= position_index <= 2:
                # Виньетка (0), Портрет 1 (1), Портрет 2 (2)
                type_key = STUDENT_POSITIONS[position_index]
                
                if type_key == "Виньетка":
                    # 1-я позиция: Имя Фамилия.JPG (Убрано слово "Виньетка")
                    new_filename = f"{student_name}{original_ext}"
                elif type_key.startswith("ЛР"):
                    # 2-я позиция: ЛР_Имя Фамилия.JPG
                    new_filename = f"ЛР_{student_name}{original_ext}"
                elif type_key.startswith("ЛС"):
                    # 3-я позиция: ЛС_Имя Фамилия.JPG
                    new_filename = f"ЛС_{student_name}{original_ext}"
                    
            elif position_index in [3, 4]:
                # 4-я и 5-я позиции (Друг 1, Друг 2)
                # Требуется сохранить исходное имя файла (ANT00110.JPG)
                new_filename = filename # Оригинальное имя
                
        return target_folder, new_filename


    def _get_target_directory(self, base_dir, filename, students_map, teachers_map, general_map, group_map, font_map):
        """
        Определяет целевую папку и новое имя для файла.
        Возвращает (target_folder, new_filename, is_friend_photo: bool).
        """
        
        original_filename_no_ext = os.path.splitext(filename)[0]
        
        # 1. Извлекаем номер из имени JPG-файла
        # Используем более точное извлечение номера (последняя последовательность цифр)
        match_num = re.search(r'(\d+)(?!.*\d)', original_filename_no_ext)
        file_number = int(match_num.group(1)) if match_num else None
        
        # Если номер не найден, мы не можем сортировать по данным из TXT
        if not file_number:
            # Fallback для JPG без номеров в имени (редкий случай, н-р "здание.jpg")
            # ИСПРАВЛЕНИЕ: Проверяем по имени файла (для "зд_")
            if filename.lower().startswith('зд_'):
                return os.path.join(base_dir, 'здание'), filename, False
            
            # Иначе не перемещаем
            return None, None, False

        # --- 1.1. Поиск по УЧЕНИКАМ (используя карту позиций) ---
        for student_name, position_map in students_map.items():
            if file_number in position_map:
                target_folder, new_filename = self._get_renamed_path_and_folder(base_dir, filename, student_name, file_number, position_map)
                
                position_index = position_map.get(file_number)
                is_friend = position_index in [3, 4] # Positions 3 and 4 are Friends

                return target_folder, new_filename, is_friend


        # --- 1.2. Поиск по УЧИТЕЛЯМ ---
        for teacher_key, numbers in teachers_map.items():
            if file_number in numbers:
                # Извлекаем ФИО учитель Предмет
                teacher_description = self._sanitize_folder_name(teacher_key)
                original_ext = os.path.splitext(filename)[1]
                new_filename = f"{teacher_description}{original_ext}" # Новое имя: ФИО учитель Предмет.JPG
                return os.path.join(base_dir, 'учителя'), new_filename, False

        # --- 1.3. Поиск по ОБЩАЯ/РЕПОРТАЖ/ФОН ---
        # Здесь оставляем оригинальное имя файла (filename), но добавляем префикс для сортировки
        for category_name, category_map in {
            "общая": general_map, 
            "репортаж": group_map, 
            "фон": font_map
        }.items():
            for description, numbers in category_map.items():
                if file_number in numbers:
                    # Для этих файлов имя = Префикс_ОригинальноеИмя
                    new_filename = f"{description}_{filename}" # Используем описание из TXT в качестве префикса
                    return os.path.join(base_dir, category_name), new_filename, False
        
        # --- 2. Fallback для файлов (н-р 'зд_') ---
        if filename.lower().startswith('зд_'):
            return os.path.join(base_dir, 'здание'), filename, False

        # --- 3. По умолчанию (если не найдено) ---
        # ИСПРАВЛЕНИЕ (ПРОБЛЕМА С "ОБЩАЯ"): Если файл имеет номер, но не найден в TXT,
        # мы его НЕ перемещаем (возвращаем None).
        if file_number:
            return None, None, False
            
        # (Остаются только файлы без номеров, которые не 'зд_')
        # (Например 'logo.jpg' - такие файлы мы тоже не трогаем)
        return None, None, False


    def start_sort_jpgs(self):
        """
        Запускает СОРТИРОВКУ JPG в отдельном потоке.
        """
        
        # 1. Проверки (в основном потоке)
        self.output_path = self.shooting_path
        if not self.output_path or not os.path.isdir(self.output_path):
            messagebox.showerror("Ошибка", "Путь к съемке недействителен.")
            return

        order_num = self._sanitize_folder_name(self.entries["Номер заказа"].get())
        if not order_num:
            messagebox.showerror("Ошибка", "Номер заказа не заполнен.")
            return
            
        if not self.selection_file_path or not os.path.exists(self.selection_file_path):
             messagebox.showerror("Ошибка", "Файл отбора не найден.")
             return
        
        # 2. Блокировка UI
        self.is_processing = True
        self.current_task_canvas = self.canvas_sort # <--- ИСПРАВЛЕНИЕ (ЗАВИСШИЕ КНОПКИ)
        self.check_input_fields()
        
        self.master.after(0, self._update_status, "Начало сортировки JPG...", False)
        
        # 3. Запуск задачи в отдельном потоке
        sort_thread = threading.Thread(
            target=self._sort_jpgs_task, 
            args=(order_num,),
            daemon=True
        )
        sort_thread.start()

    def _sort_jpgs_task(self, order_num):
        """
        Фоновая ЛОГИКА: Сортирует JPG-файлы.
        """
        
        # --- ОБЩИЙ КОЛБЭК ДЛЯ СТАТУСА ---
        def on_progress(message, percent):
            self.master.after(0, self._update_status, message, False)

        try:
            # --- 1. Чтение данных ---
            on_progress("Чтение файла отбора...", 0)
            try:
                self.selection_data = self._read_selection_from_file()
            except Exception as e:
                raise Exception(f"Ошибка чтения selected.txt: {e}")

            students_map = self.selection_data.get("Ученики", {})
            teachers_map = self.selection_data.get("Учителя", {})
            general_map = self.selection_data.get("Общая", {})
            group_map = self.selection_data.get("Групповые", {})
            font_map = self.selection_data.get("Фон", {})

            if not any([students_map, teachers_map, general_map, group_map, font_map]):
                raise Exception("Файл отбора пуст.")

            # --- 2. Определение путей ---
            school_num = self._sanitize_folder_name(self.entries["Номер школы"].get())
            date = self._sanitize_folder_name(self.entries["Дата"].get())
            class_name = self._sanitize_folder_name(self.entries["Класс"].get())

            # Куда (в папку класса)
            base_target_dir = os.path.join(
                self.output_path, order_num, order_num, school_num, date, class_name
            )
            
            if not os.path.isdir(base_target_dir):
                raise Exception(f"Папка структуры не найдена. (Выполните 'Сгенерировать')")
                
            # ИСПРАВЛЕНИЕ (ПРОБЛЕМА С "ВЫРЕЗАНИЕМ" - ПУТЬ):
            # Мы берем JPG из папки "отобранный материал".
            source_material_dir = os.path.join(self.output_path, order_num, f"{order_num} дубли равы", "отобранный материал")

            if not os.path.isdir(source_material_dir):
                raise Exception(f"Папка 'отобранный материал' не найдена.")
                
            # 3. Сканирование и перемещение
            moved_count = 0
            
            jpg_files_to_move = [f for f in os.listdir(source_material_dir) if f.lower().endswith(('.jpg', '.jpeg'))]
            total_files = len(jpg_files_to_move)
            
            if total_files == 0:
                raise Exception(f"В папке 'отобранный материал' не найдено JPG-файлов.")

            on_progress(f"Сортировка 0/{total_files} JPG...", 0)

            for i, filename in enumerate(jpg_files_to_move):
                source_path = os.path.join(source_material_dir, filename)
                
                # Обновляем статус
                progress_percent = int(((i + 1) / total_files) * 100)
                on_progress(f"Сортировка {progress_percent}%: {filename}...", progress_percent)

                # Получаем целевую папку, НОВОЕ ИМЯ и ФЛАГ, является ли это фото друга
                target_folder, new_filename, is_friend_photo = self._get_target_directory(
                    base_target_dir, filename, 
                    students_map, teachers_map, general_map, group_map,
                    font_map
                )
                
                # ИСПРАВЛЕНИЕ (ПРОБЛЕМА С "ОБЩАЯ"):
                # Если папка None, значит файл не нужно перемещать (он не в selected.txt)
                if target_folder is None:
                    continue
                
                # Конечный путь для перемещения/копирования
                target_path = os.path.join(target_folder, new_filename)
                
                # ИСПРАВЛЕНИЕ (ПРОБЛЕМА С "ВЫРЕЗАНИЕМ"):
                # Всегда используем ВЫРЕЗАТЬ (shutil.move).
                # Логика "копирования" фото друзей была неверной для этого этапа.
                operation = shutil.move
                
                # *** КРИТИЧНОЕ ИСПРАВЛЕНИЕ ДЛЯ ПЕРЕЗАПИСИ ***
                if os.path.exists(target_path):
                    name_base, name_ext = os.path.splitext(new_filename)
                    count = 1
                    while os.path.exists(os.path.join(target_folder, f"{name_base}_{count}{name_ext}")):
                        count += 1
                    new_filename = f"{name_base}_{count}{name_ext}"
                    target_path = os.path.join(target_folder, new_filename)
                # **********************************************
                
                os.makedirs(target_folder, exist_ok=True) 
                
                # ВЫПОЛНЕНИЕ ОПЕРАЦИИ
                try:
                    operation(source_path, target_path) 
                    moved_count += 1
                except FileNotFoundError:
                    # Эта ошибка теперь не должна возникать, но оставим защиту
                    print(f"Предупреждение: Файл {filename} не найден в источнике. Пропускаем.")
                except Exception as e:
                    raise # Перебрасываем любую другую ошибку
                
            # --- ЗАВЕРШЕНИЕ СОРТИРОВКИ ---
            self.master.after(0, self._on_sort_complete, f"УСПЕХ! Отсортировано {moved_count} JPG.", False)

        except Exception as e:
            self.master.after(0, self._on_sort_complete, f"Ошибка сортировки JPG: {e}", True)

    def _on_sort_complete(self, message, is_error):
        """Восстанавливает UI после СОРТИРОВКИ."""
        
        # 1. Восстановление
        self.is_processing = False
        self.current_task_canvas = None # <--- ИСПРАВЛЕНИЕ (ЗАВИСШИЕ КНОПКИ)
        
        # 2. Сбрасываем UI (по старому ТЗ)
        if not is_error:
            self._reset_ui() # Сбрасываем все поля
            self.save_config()
        else:
            # Если была ошибка, не сбрасываем, просто разблокируем
            self.var_jpg_exported.set(False) # Сбрасываем чекбокс
            self.check_input_fields() # Разблокируем UI

        # 3. Показываем статус
        self._update_status(message, is_error=is_error)


if __name__ == "__main__":
    root = tk.Tk()
    app = FolderGeneratorApp(root)
    
    # КРИТИЧНОЕ ИСПРАВЛЕНИЕ (КНОПКИ НЕ ВИДНЫ):
    # Мы ждем, пока Tkinter будет готов, и вручную
    # генерируем событие Configure, чтобы кнопки прорисовались.
    root.after(100, lambda: app.canvas_gen.event_generate('<Configure>'))
    root.after(100, lambda: app.canvas_sort.event_generate('<Configure>'))
    
    root.mainloop()