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
    3: "Друг1",       # Сохраняет номер
    4: "Друг2"        # Сохраняет номер
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
        # ИСПРАВЛЕНИЕ: Удалена привязка <Key>, которая конфликтовала с вводом текста (особенно кириллицы)
        
        self._setup_universal_entry_clipboard()

        if initial_value:
             self.entry.insert(0, initial_value)
             self._float_label(initial_call=True)

    # ИСПРАВЛЕНИЕ: Удален метод _handle_all_key_input
    
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

# ====================================================================
# ОСНОВНОЙ КЛАСС ПРИЛОЖЕНИЯ
# ====================================================================
class FolderGeneratorApp:
    
    # ИЗМЕНЕНИЕ: НОВАЯ ФУНКЦИЯ ЦЕНТРИРОВАНИЯ
    def _center_window(self, width=380, height=700): # Увеличена высота для 3 кнопок
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
        self.var_quotes = tk.BooleanVar()
        self.var_video = tk.BooleanVar()
        self.generate_button = None 
        self.copy_raw_button = None # НОВАЯ КНОПКА
        self.sort_button = None 
        self.logo_image = None
        self.status_label = None
        self.canvas_gen = None 
        self.canvas_copy_raw = None # НОВЫЙ CANVAS
        self.canvas_sort = None
        
        # ИЗМЕНЕНИЕ: Добавляем ссылки на виджеты для блокировки
        self.path_shooting_sel = None
        self.checkbox_container = None
        
        # НОВОЕ: Флаг состояния для неблокирующего копирования
        self.is_copying_raw = False
        
        # --- Загрузка и инициализация ---
        self.config_data = self._load_config()
        self._init_variables_from_config()
        
        self.setup_ui()
        self.set_default_path()
        
        # ИЗМЕНЕНИЕ: Центрируем окно ПОСЛЕ setup_ui
        self._center_window(width=380, height=700)
        
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
        
        # ИЗМЕНЕНИЕ: Всегда начинаем с пустых/выключенных значений
        self.var_quotes.set(False)
        self.var_video.set(False)
        
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
        # ИЗМЕНЕНИЕ: Цвет статуса всегда серый
        color = COLOR_TEXT_LIGHT # if is_error else COLOR_TEXT_LIGHT
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
        
        if state == tk.NORMAL:
            color = COLOR_ACCENT_PINK
            text_color = "white"
            cursor = "hand2"
        else:
            # Если DISABLED, проверяем, не идет ли копирование, чтобы показать "Копирование..."
            if self.is_copying_raw and canvas == self.canvas_copy_raw:
                 color = COLOR_ACCENT_PINK
                 text_color = "white"
                 text = "Копирование..."
            else:
                 color = COLOR_BUTTON_DISABLED_LIGHT
                 text_color = COLOR_BUTTON_TEXT_DISABLED
            cursor = "arrow" 
        
        self.create_rounded_rectangle(canvas, 1, 1, width-1, height-1, radius, fill_color=color, tags="button_bg") 
        
        canvas.create_text(width/2, height/2, text=text, 
                              font=(FONT_FAMILY, 14, 'bold'), fill=text_color, tags="button_text")
        
        canvas.config(cursor=cursor)

    def create_styled_checkbox_in_frame(self, master, text, variable, row, col, columnspan, label_right_pad=4):
        """Создает стилизованный чекбокс."""
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
            
            if variable.get():
                self.create_rounded_rectangle(canvas, x1, y1, x2, y2, checkbox_radius, 
                                              fill_color=COLOR_ACCENT_PINK, tags="checkbox_outer_border")
                offset_white = 2
                w_x1, w_y1 = x1 + offset_white, y1 + offset_white
                w_x2, w_y2 = x2 - offset_white, y2 - offset_white
                self.create_rounded_rectangle(canvas, w_x1, w_y1, w_x2, w_y2, 
                                              checkbox_radius, fill_color=COLOR_BACKGROUND, tags="checkbox_white_fill")
                offset_pink = 4
                p_x1, p_y1 = x1 + offset_pink, y1 + offset_pink
                p_x2, p_y2 = x2 - offset_pink, y2 - offset_pink
                self.create_rounded_rectangle(canvas, p_x1, p_y1, p_x2, p_y2, 
                                              checkbox_radius, fill_color=COLOR_ACCENT_PINK, tags="checkbox_inner_fill")
            else:
                outline_color = COLOR_CHECKBOX_BORDER
                self.create_rounded_rectangle(canvas, x1, y1, x2, y2, checkbox_radius, 
                                              fill_color=COLOR_BACKGROUND, outline_color=outline_color, width=1, tags="checkbox_border")
            
        label = tk.Label(internal_frame, text=text, bg=COLOR_BACKGROUND, fg=COLOR_TEXT_NORMAL,
                             font=(FONT_FAMILY, 12), cursor="hand2")
        label.pack(side=tk.LEFT, anchor='w', padx=(0, label_right_pad))

        def toggle_state(event=None):
            variable.set(not variable.get())
        
        variable.trace_add('write', lambda *args: draw_indicator())
        
        canvas.bind("<Button-1>", toggle_state)
        label.bind("<Button-1>", toggle_state)
        internal_frame.bind("<Button-1>", toggle_state)
        
        draw_indicator()
        return internal_frame

    # ====================================================================
    # UI Setup
    # ====================================================================
    def setup_ui(self):
        main_frame = tk.Frame(self.master, bg=COLOR_BACKGROUND)
        main_frame.pack(pady=20, padx=20, fill="both", expand=True)
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
        # 1. Путь к съемке (PathSelector)
        # --------------------------------------------------------------------------
        self.path_shooting_sel = PathFileSelector(main_frame, "Выберите путь к съемке", FONT_FAMILY, 
                                              select_dir=True, 
                                              initial_value=self.shooting_path,
                                              on_select_callback=lambda path: self._update_paths_and_check_fields(path, 'shooting_path'))
        self.path_shooting_sel.grid(row=row, column=0, columnspan=4, padx=10, pady=BLOCK_PADY_VERTICAL, sticky='ew')
        row += 1
        
        # --------------------------------------------------------------------------
        # 2. Файл отбора (ОТОБРАЖЕНИЕ)
        # ИЗМЕНЕНИЕ: Изменена метка с "Отбор" на "Файл отбора"
        # --------------------------------------------------------------------------
        f_selection_file = PathFileSelector(main_frame, "Файл отбора", FONT_FAMILY, 
                                               select_dir=False, 
                                               allow_multiple=False, # Только один файл
                                               initial_value="", # Всегда пусто при старте
                                               on_select_callback=lambda path: self._update_paths_and_check_fields(path, 'selection_file'))
        
        # ИЗМЕНЕНИЕ: Меняем тип файла для диалога
        f_selection_file.select_path_or_file = lambda event=None: self._select_txt_file(f_selection_file)

        f_selection_file.grid(row=row, column=0, columnspan=4, padx=10, pady=BLOCK_PADY_VERTICAL, sticky='ew')
        f_selection_file.entry.config(cursor="hand2") 
        
        self.entries["Файл отбора"] = f_selection_file # Сохраняем для обновления
        row += 1
        
        # --------------------------------------------------------------------------
        # 3. Номер заказа и Дата (FloatingLabelEntry)
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
        # 4. Номер школы и Класс (FloatingLabelEntry)
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
        # 5. Чекбоксы
        # --------------------------------------------------------------------------
        self.checkbox_container = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        self.checkbox_container.grid(row=row, column=0, columnspan=4, sticky='w', padx=10, pady=(20,10))
        self.checkbox_container.grid_columnconfigure(0, weight=0)
        self.checkbox_container.grid_columnconfigure(1, weight=0)
        self.checkbox_container.grid_columnconfigure(2, weight=0)

        self.create_styled_checkbox_in_frame(self.checkbox_container, "Цитаты", self.var_quotes, 0, 0, 1, 32)
        tk.Frame(self.checkbox_container, width=8, bg=COLOR_BACKGROUND).grid(row=0, column=1, sticky='ns')
        self.create_styled_checkbox_in_frame(self.checkbox_container, "Видео", self.var_video, 0, 2, 1, 4)
        row += 1
        
        # --------------------------------------------------------------------------
        # 6. Кнопки (ТРИ)
        # --------------------------------------------------------------------------
        button_container_1 = tk.Frame(main_frame, bg=COLOR_BACKGROUND, height=BUTTON_HEIGHT)
        button_container_1.grid(row=row, column=0, columnspan=4, padx=10, pady=(15, 10), sticky='ew')
        button_container_1.pack_propagate(False)

        self.canvas_gen = tk.Canvas(button_container_1, bd=0, highlightthickness=0, bg=COLOR_BACKGROUND)
        self.canvas_gen.pack(fill='both', expand=True)

        self.generate_button = tk.Button(state=tk.DISABLED) # Dummy
        
        self.canvas_gen.bind("<Configure>", lambda e: self.draw_button(self.canvas_gen, self.generate_button['state'], "Сгенерировать структуру"))
        self.canvas_gen.bind("<Button-1>", lambda e: self.generate_folders() if self.generate_button['state'] == tk.NORMAL else None)
        self.canvas_gen.config(cursor="hand2")
        
        row += 1
        
        # НОВАЯ КНОПКА 2
        button_container_2 = tk.Frame(main_frame, bg=COLOR_BACKGROUND, height=BUTTON_HEIGHT)
        button_container_2.grid(row=row, column=0, columnspan=4, padx=10, pady=(0, 10), sticky='ew')
        button_container_2.pack_propagate(False)

        self.canvas_copy_raw = tk.Canvas(button_container_2, bd=0, highlightthickness=0, bg=COLOR_BACKGROUND)
        self.canvas_copy_raw.pack(fill='both', expand=True)

        self.copy_raw_button = tk.Button(state=tk.DISABLED) # Dummy
        
        self.canvas_copy_raw.bind("<Configure>", lambda e: self.draw_button(self.canvas_copy_raw, self.copy_raw_button['state'], "Скопировать отобранные raw"))
        self.canvas_copy_raw.bind("<Button-1>", lambda e: self._copy_raw_files() if self.copy_raw_button['state'] == tk.NORMAL and not self.is_copying_raw else None)
        self.canvas_copy_raw.config(cursor="hand2")
        
        row += 1
        
        # КНОПКА 3
        button_container_3 = tk.Frame(main_frame, bg=COLOR_BACKGROUND, height=BUTTON_HEIGHT)
        button_container_3.grid(row=row, column=0, columnspan=4, padx=10, pady=(0, 15), sticky='ew')
        button_container_3.pack_propagate(False)

        self.canvas_sort = tk.Canvas(button_container_3, bd=0, highlightthickness=0, bg=COLOR_BACKGROUND)
        self.canvas_sort.pack(fill='both', expand=True)

        self.sort_button = tk.Button(state=tk.DISABLED) # Dummy
        
        self.canvas_sort.bind("<Configure>", lambda e: self.draw_button(self.canvas_sort, self.sort_button['state'], "Разложить JPG по папкам"))
        self.canvas_sort.bind("<Button-1>", lambda e: self._sort_jpgs_to_folders() if self.sort_button['state'] == tk.NORMAL else None)
        self.canvas_sort.config(cursor="hand2")
        
        row += 1

        # --------------------------------------------------------------------------
        # 8. Метка статуса (Внизу)
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
            
            # НОВОЕ: Автоматическое создание TXT-файла
            self._create_selection_file_template()
            
            # ДОБАВЛЕНИЕ: Гарантируем, что selection_file_path установлен корректно
            expected_path = self._get_expected_selection_file_path()
            if expected_path:
                self.selection_file_path = expected_path

        elif identifier == 'selection_file':
            self.selection_file_path = paths_or_path
            
        self.check_input_fields()

    def check_input_fields(self):
        """Проверяет заполнение полей и активирует/деактивирует кнопки."""
        order_num = self._sanitize_folder_name(self.entries["Номер заказа"].get())
        class_name = self._sanitize_folder_name(self.entries["Класс"].get())
        shooting_path_valid = self.shooting_path and os.path.isdir(self.shooting_path)
        
        selection_file_exists = self.selection_file_path and os.path.exists(self.selection_file_path)

        # --- КНОПКА 1: Сгенерировать структуру ---
        is_gen_complete = all([order_num, class_name]) and shooting_path_valid
        # Блокируем, если идет копирование
        new_state_gen = tk.DISABLED if self.is_copying_raw else (tk.NORMAL if is_gen_complete else tk.DISABLED)

        if self.generate_button.cget('state') != new_state_gen:
            self.generate_button.config(state=new_state_gen)
            self.master.after_idle(lambda: self.draw_button(self.canvas_gen , new_state_gen, "Сгенерировать структуру"))

        # --- КНОПКА 2: Скопировать RAW ---
        is_copy_complete = all([shooting_path_valid, selection_file_exists])
        # Блокируем, если идет копирование
        new_state_copy = tk.DISABLED if self.is_copying_raw else (tk.NORMAL if is_copy_complete else tk.DISABLED)
        
        if self.copy_raw_button.cget('state') != new_state_copy:
            self.copy_raw_button.config(state=new_state_copy)
            # Если идет копирование, draw_button отрисует "Копирование..."
            self.master.after_idle(lambda: self.draw_button(self.canvas_copy_raw, new_state_copy, "Скопировать отобранные raw"))
            
        # --- КНОПКА 3: Разложить JPG по папкам ---
        is_sort_complete = all([shooting_path_valid, selection_file_exists])
        # Блокируем, если идет копирование
        new_state_sort = tk.DISABLED if self.is_copying_raw else (tk.NORMAL if is_sort_complete else tk.DISABLED)

        if self.sort_button.cget('state') != new_state_sort:
            self.sort_button.config(state=new_state_sort)
            self.master.after_idle(lambda: self.draw_button(self.canvas_sort, new_state_sort, "Разложить JPG по папкам"))
            
        # Обновление статуса
        if self.is_copying_raw:
             # Не меняем статус, если он уже показывает прогресс
             pass
        elif not shooting_path_valid:
             self._update_status("Выберите Путь к съемке.", is_error=True)
        elif not selection_file_exists:
             self._update_status("Файл 'selected.txt' не найден (выберите Путь к съемке).", is_error=True)
        elif not order_num or not class_name:
             self._update_status("Введите Номер заказа и Класс.", is_error=True)
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
            else:
                 self._update_status(f"Файл отбора найден: {os.path.basename(selection_path)}.", is_error=False) 
            
        except Exception as e:
            self._update_status(f"Ошибка создания/обновления файла отбора: {e}", is_error=True)
            
        self.check_input_fields()

    # ИЗМЕНЕНИЕ: Кастомный селектор для TXT-файлов
    def _select_txt_file(self, selector_widget):
        """Открывает диалог выбора TXT-файла."""
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
                                         # i — это индекс позиции (0, 1, 2, 3, 4). Прочерки игнорируются при счете.
                                         # Фактически, нам нужен i, но с учетом, что прочерки не считаются числом
                                         # Лучше считать по порядку следования.
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
            messagebox.showerror("Ошибка чтения", f"Не удалось прочитать или разобрать файл отбора: {e}")
            return {}
            
        return selection_data

    # ====================================================================
    # ЭТАП 1: ГЕНЕРАЦИЯ СТРУКТУРЫ
    # ====================================================================
    
    def generate_folders(self):
        """Запускает генерацию структуры папок."""
        order_num = self._sanitize_folder_name(self.entries["Номер заказа"].get())
        if not order_num:
            messagebox.showerror("Ошибка", "Номер заказа не заполнен.")
            return
            
        self.output_path = self.shooting_path
        if not self.output_path or not os.path.isdir(self.output_path):
            messagebox.showerror("Ошибка", "Путь к съемке недействителен.")
            return

        # ИЗМЕНЕНИЕ: Читаем TXT, чтобы получить список учеников для папок
        # (Даже если TXT пуст, мы создаем папки)
        self.selection_data = self._read_selection_from_file()
        students_map = self.selection_data.get("Ученики", {})
        students = list(students_map.keys())
        
        # --- Создание структуры ---
        try:
            structure_text = self._build_structure(order_num, students)
            self._create_folders_from_structure(self.output_path, structure_text)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать структуру папок: {e}")
            return
            
        self._update_status(f"УСПЕХ! Структура папок '{order_num}' создана.", is_error=False)
        self.save_config() 
        
    # ====================================================================
    # ЭТАП 2: КОПИРОВАНИЕ RAW (С ИСПОЛЬЗОВАНИЕМ ПОТОКОВ)
    # ====================================================================

    def _copy_raw_files(self):
        """Запускает копирование RAW-файлов в отдельном потоке, чтобы не блокировать UI."""
        
        # 1. Проверка и подготовка (Остается в главном потоке)
        order_num = self._sanitize_folder_name(self.entries["Номер заказа"].get())
        if not order_num:
            messagebox.showerror("Ошибка", "Номер заказа не заполнен.")
            return
            
        # КРИТИЧНОЕ ИСПРАВЛЕНИЕ: Проверяем, что внутренняя переменная selection_file_path установлена
        if not self.selection_file_path or not os.path.exists(self.selection_file_path):
             messagebox.showerror("Ошибка", "Файл отбора не найден.")
             return
            
        self.output_path = self.shooting_path
        if not self.output_path or not os.path.isdir(self.output_path):
            messagebox.showerror("Ошибка", "Путь к съемке недействителен.")
            return
        
        # 2. Блокировка UI
        self.is_copying_raw = True # Установка флага
        self.check_input_fields() # Обновление состояния кнопок
        self.draw_button(self.canvas_copy_raw, tk.DISABLED, "Копирование...") # Принудительная перерисовка
        self.master.after(0, self._update_status, "Начало подготовки к копированию...", False)

        # 3. Запуск задачи в отдельном потоке
        copy_thread = threading.Thread(target=self._copy_raw_files_task, args=(order_num,))
        copy_thread.start()

    def _copy_raw_files_task(self, order_num):
        """Фоновая задача: Копирует отобранные RAW-файлы."""
        
        # Чтение данных 
        self.selection_data = self._read_selection_from_file()
        
        # Проверяем, что хотя бы ОДНА секция заполнена
        if not any(self.selection_data.values()):
             # Schedule error message on main thread
             self.master.after(0, self._on_copy_raw_complete, "Ошибка: Файл отбора пуст. Заполните TXT-файл.", True, order_num)
             return
            
        # --- 3. Копирование отобранных RAW-файлов ---
        raw_copy_count = 0
        
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Убеждаемся, что папка структуры создана
        # (на случай, если пользователь пропустил шаг 1)
        base_folder_path = os.path.join(self.output_path, order_num)
        target_raw_dir = os.path.join(base_folder_path, f"{order_num} дубли равы", "отобранный материал")

        if not os.path.isdir(target_raw_dir):
            try:
                os.makedirs(target_raw_dir, exist_ok=True)
            except Exception as e:
                self.master.after(0, self._on_copy_raw_complete, f"Ошибка создания папки 'отобранный материал': {e}", True, order_num)
                return
        
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
        # Статус 0%
        self.master.after(0, self._update_status, f"0%: Ожидание начала копирования ({total_files} RAW-файлов)...", False)

        for i, num in enumerate(unique_file_numbers):
            source_file = self._find_file_by_number(self.shooting_path, num)
            if source_file:
                try:
                    # Расчет прогресса (с округлением)
                    progress_percent = int(((i + 1) / total_files) * 100)
                    file_name = os.path.basename(source_file)
                    
                    # Thread-safe status update: % и имя файла
                    status_msg = f"{progress_percent}%: Копирование {file_name}..."
                    self.master.after(0, self._update_status, status_msg, False)
                    
                    shutil.copy2(source_file, target_raw_dir) 
                    raw_copy_count += 1
                except Exception as e:
                    print(f"Ошибка копирования {source_file}: {e}")
            else:
                not_found_files.append(str(num))
                        
        # --- Финальные обновления статуса и завершение ---
        if not_found_files:
             # Schedule warning messagebox display (messagebox is thread-safe on many OSes, but scheduling is safest)
             self.master.after(0, messagebox.showwarning, "Внимание", f"Не удалось найти следующие номера файлов: {', '.join(not_found_files)}")
            
        final_msg = f"УСПЕХ! Скопировано {raw_copy_count} RAW."
        self.master.after(0, self._on_copy_raw_complete, final_msg, False, order_num)

    def _on_copy_raw_complete(self, message, is_error, order_num):
        """Восстанавливает UI, показывает финальный статус и открывает папку (вызывается в основном потоке)."""
        
        # 1. Восстановление кнопок и статуса
        self.is_copying_raw = False # Снятие флага
        self.check_input_fields() # Восстановление состояния кнопок
        self.draw_button(self.canvas_copy_raw, tk.NORMAL, "Скопировать отобранные raw")
        self._update_status(message, is_error=is_error)

        # 2. Открытие папки (только при успехе)
        if not is_error:
            target_raw_dir = os.path.join(self.output_path, order_num, f"{order_num} дубли равы", "отобранный материал")
            
            # --- КРИТИЧЕСКАЯ ПРОВЕРКА ПУТИ ---
            if not os.path.isdir(target_raw_dir):
                 self.master.after(0, self._update_status, f"Ошибка: Целевая папка '{target_raw_dir}' не найдена для открытия.", True)
                 return
                 
            self._update_status(f"Открытие папки 'отобранный материал'...", is_error=False) 
            try:
                # УЛУЧШЕННЫЙ ВЫЗОВ ДЛЯ WINDOWS
                if sys.platform == "win32":
                    # Используем startfile, который более надежен для открытия папок по абсолютному пути
                    os.startfile(target_raw_dir)
                elif sys.platform == "darwin": # macOS
                    subprocess.Popen(["open", target_raw_dir])
                else: # Linux/UNIX
                    subprocess.Popen(["xdg-open", target_raw_dir])
            except Exception as e:
                print(f"Ошибка при попытке открыть папку: {e}")
                self.master.after(0, self._update_status, "Папка создана, но не открыта автоматически.", True)
        
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
            
            # Поиск в конце имени файла: ищем номер (до 5 цифр)
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
            
        if self.var_quotes.get():
            lines.append(f"{tab*5}цитаты")
        if self.var_video.get():
            lines.append(f"{tab*5}видео")
            
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
        
        # ИЗМЕНЕНИЕ: Обновляем список ключей, чтобы использовать "Файл отбора"
        keys_to_reset = ["Номер заказа", "Номер школы", "Класс", "Дата", "Файл отбора", "Выберите путь к съемке"]
        for key in keys_to_reset:
            if key in self.entries:
                entry_widget = self.entries[key].entry
                entry_widget.config(state='normal') # Разблокируем для сброса
                entry_widget.delete(0, tk.END)
                self.entries[key]._sink_label()
        
        # 2. Восстанавливаем текущую дату
        f_date = self.entries["Дата"]
        today_str = datetime.datetime.now().strftime("%d.%m.%Y")
        f_date.entry.insert(0, today_str)
        f_date._float_label(initial_call=True)

        # 3. Сбрасываем переменные состояния
        self.shooting_path = ""
        self.selection_file_path = None
        self.selection_data = {}
        
        # 4. Сбрасываем PathSelector (Путь к съемке)
        if self.path_shooting_sel:
             self.path_shooting_sel.entry.config(state='normal')
             self.path_shooting_sel.entry.delete(0, tk.END)
             self.path_shooting_sel.entry.config(state='readonly')
             self.path_shooting_sel._sink_label()

        # 5. Сбрасываем Чекбоксы
        self.var_quotes.set(False)
        self.var_video.set(False)
        
        self.check_input_fields()
        self._update_status("Сброс выполнен. Введите данные для нового заказа.", is_error=False)
        self.master.focus_set()


    # ====================================================================
    # ЭТАП 3: РАЗЛОЖИТЬ JPG ПО ПАПКАМ (СОРТИРОВКА)
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
            # Fallback для JPG без номеров в имени (редкий случай)
            return os.path.join(base_dir, "общая"), filename, False

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
        
        # --- 2. Fallback для файлов без номеров или без совпадений ---

        # Имитируем префиксы для (Здание)
        if filename.lower().startswith('зд_'):
            return os.path.join(base_dir, 'здание'), filename, False

        # --- 3. По умолчанию (если не найдено) ---
        return os.path.join(base_dir, "общая"), filename, False


    def _sort_jpgs_to_folders(self):
        """Запускает перемещение JPG-файлов из отобранного материала в целевые папки."""
        
        # ИЗМЕНЕНИЕ: Устанавливаем output_path = shooting_path
        self.output_path = self.shooting_path
        if not self.output_path or not os.path.isdir(self.output_path):
            messagebox.showerror("Ошибка", "Путь к съемке недействителен.")
            return

        order_num = self._sanitize_folder_name(self.entries["Номер заказа"].get())
        if not order_num:
            messagebox.showerror("Ошибка", "Номер заказа не заполнен.")
            return
            
        # ИЗМЕНЕНИЕ: Обновляем путь к файлу отбора
        self.selection_file_path = self.entries.get("Файл отбора").get()
        
        if not self.selection_file_path or not os.path.exists(self.selection_file_path):
             messagebox.showerror("Ошибка", "Файл отбора не найден.\n"
                                     "Убедитесь, что 'Номер заказа' верный и выберите 'Путь к съемке'.")
             return

        self.selection_data = self._read_selection_from_file()
        students_map = self.selection_data.get("Ученики", {})
        teachers_map = self.selection_data.get("Учителя", {})
        general_map = self.selection_data.get("Общая", {})
        group_map = self.selection_data.get("Групповые", {})
        font_map = self.selection_data.get("Фон", {}) # НОВАЯ СТРОКА

        if not students_map and not teachers_map and not general_map and not group_map and not font_map:
            messagebox.showerror("Ошибка", "Не найдены данные в файле отбора. Проверьте TXT-файл.")
            return

        # 1. Определяем базовый путь, куда будут перемещаться файлы (папка [Класс])
        school_num = self._sanitize_folder_name(self.entries["Номер школы"].get())
        date = self._sanitize_folder_name(self.entries["Дата"].get())
        class_name = self._sanitize_folder_name(self.entries["Класс"].get())

        base_target_dir = os.path.join(
            self.output_path, order_num, order_num, school_num, date, class_name
        )
        
        if not os.path.isdir(base_target_dir):
            messagebox.showerror("Ошибка", f"Базовая папка структуры не найдена. Сначала выполните 'Сгенерировать структуру': {base_target_dir}")
            return
            
        # 2. Определяем исходный путь, откуда будем ВЫРЕЗАТЬ JPG
        source_material_dir = os.path.join(self.output_path, order_num, f"{order_num} дубли равы", "отобранный материал")

        if not os.path.isdir(source_material_dir):
            messagebox.showerror("Ошибка", f"Папка 'отобранный материал' не найдена. Возможно, вы не выполнили 'Скопировать отобранные raw': {source_material_dir}")
            return
            
        # 3. Сканирование и перемещение
        moved_count = 0
        
        # ИЗМЕНЕНИЕ: Получаем список файлов ДО цикла для статуса
        jpg_files_to_move = [f for f in os.listdir(source_material_dir) if f.lower().endswith(('.jpg', '.jpeg'))]
        total_files = len(jpg_files_to_move)
        self._update_status(f"Сортировка 0/{total_files} JPG-файлов...", is_error=False)

        try:
            for i, filename in enumerate(jpg_files_to_move):
                source_path = os.path.join(source_material_dir, filename)
                
                # ИЗМЕНЕНИЕ: Обновляем статус
                self._update_status(f"Сортировка {i+1}/{total_files}: {filename}...", is_error=False)

                # Получаем целевую папку, НОВОЕ ИМЯ и ФЛАГ, является ли это фото друга
                target_folder, new_filename, is_friend_photo = self._get_target_directory(
                    base_target_dir, filename, 
                    students_map, teachers_map, general_map, group_map,
                    font_map
                )
                
                # Конечный путь для перемещения/копирования
                target_path = os.path.join(target_folder, new_filename)
                
                # Определяем операцию: копирование для общих файлов (друзей) или перемещение для уникальных
                operation = shutil.copy2 if is_friend_photo else shutil.move # NEW LINE
                
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
                    # Если файл не найден, но это фото друга, мы просто пропускаем. 
                    if is_friend_photo:
                         print(f"Предупреждение: Общий файл {filename} уже был обработан и отсутствует в источнике. Пропускаем.")
                    else:
                         # Если это уникальный файл (портрет, учитель) и его нет, это ошибка.
                         raise # Перебрасываем ошибку FileNotFoundError
                except Exception as e:
                     raise # Перебрасываем любую другую ошибку
                
            self._update_status(f"УСПЕХ! Перемещено/Скопировано {moved_count} JPG-файлов.", is_error=False)
            
        except Exception as e:
            self._update_status(f"Ошибка сортировки JPG: {e}", is_error=True)
            
        # ИЗМЕНЕНИЕ: Сбрасываем UI
        self._reset_ui() 
        self.save_config()

if __name__ == "__main__":
    root = tk.Tk()
    app = FolderGeneratorApp(root)
    root.mainloop()