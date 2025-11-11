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
from pathlib import Path

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
COLOR_ACCENT_PINK = '#e53965' # Основной цвет (красный)
COLOR_LINE_INACTIVE = '#ccc'
COLOR_BUTTON_DISABLED = '#444' 
COLOR_BUTTON_DISABLED_LIGHT = '#EAEAEA' 
COLOR_BUTTON_TEXT_DISABLED = '#ccc' 
COLOR_CHECKBOX_BORDER = '#AEAEAE' 
COLOR_STATUS_ERROR = '#D32F2F' # Красный для ошибок
COLOR_STATUS_NORMAL = '#2E7D32' # Зеленый для успеха
COLOR_STATUS_INFO = '#888' # Серый для информационных сообщений

# НОВОЕ: Красный цвет для активных чекбоксов
COLOR_CHECKBOX_ACTIVE = '#e53965' 
COLOR_BUTTON_DARK = '#333333' # Темно-серый для кнопки Генерации (для имитации макета)

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
    0: "Виньетка", 
    1: "ЛР_Портрет1", 
    2: "ЛС_Портрет2", 
    3: "Друг1",       
    4: "Друг2"       
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
# КЛАСС FloatingLabelEntry (Оставлен для PathSelector)
# ====================================================================
class FloatingLabelEntry(tk.Frame):
    def __init__(self, master, label_text, font_family, initial_value="", on_change_callback=None, **kwargs):
        super().__init__(master, bg=COLOR_BACKGROUND) 
        self.label_text = label_text
        self.font_family = font_family
        self.on_change_callback = on_change_callback
        self.is_floating = False
        self.animating = False

        self.entry_container = tk.Frame(self, bg=COLOR_BACKGROUND, height=45)
        self.entry_container.pack(fill='x', expand=True)
        self.entry_container.pack_propagate(False)

        self.entry = tk.Entry(self.entry_container, bd=0, relief=tk.FLAT,
                              highlightthickness=0, 
                              font=(font_family, 12), bg=COLOR_BACKGROUND, 
                              fg=COLOR_TEXT_NORMAL, insertbackground=COLOR_ACCENT_PINK, 
                              insertwidth=1, 
                              readonlybackground=COLOR_BACKGROUND, 
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
             self.entry.config(fg=COLOR_TEXT_NORMAL)
    
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
# КЛАСС PathFileSelector (Оставлен для PathSelector)
# ====================================================================
class PathFileSelector(FloatingLabelEntry):
    def __init__(self, master, label_text, font_family, select_dir=True, allow_multiple=False, initial_value="", on_select_callback=None, **kwargs):
        self.select_dir = select_dir
        self.allow_multiple = allow_multiple 
        self.on_select_callback = on_select_callback
        
        super().__init__(master, label_text, font_family, initial_value=initial_value, on_change_callback=None, state='readonly', **kwargs)
        
        self.entry.config(cursor="hand2")
        self.entry.unbind("<KeyRelease>")
        self.entry.unbind("<Key>")

        self.entry.bind("<Button-1>", lambda e: self.select_path_or_file(e))
        self.label.bind("<Button-1>", lambda e: self.select_path_or_file(e))
        
        self.entry.config(state='normal')
        if initial_value:
             self.entry.insert(0, initial_value)
             self._float_label(initial_call=True)
             self.entry.config(fg=COLOR_TEXT_NORMAL)
        self.entry.config(state='readonly')

    def select_path_or_file(self, event=None):
        initial_dir = os.path.expanduser('~')
        current_val = self.get().strip()
        
        if (not self.allow_multiple or ',' not in current_val) and current_val:
            first_path_guess = current_val.split(',')[0].strip()
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
                filetypes=[("Text files", "*.txt")] 
            )
            
        if paths_selected:
            self.entry.config(state='normal')
            self.entry.delete(0, tk.END)
            
            display_text = ""
            if isinstance(paths_selected, (list, tuple)):
                if len(paths_selected) > 0:
                    filenames = [os.path.basename(p) for p in paths_selected]
                    display_text = ", ".join(filenames)
            else:
                display_text = paths_selected 

            self.entry.insert(0, display_text)
            self.entry.config(state='readonly')
            self._float_label(initial_call=True)
            
            if self.on_select_callback:
                self.on_select_callback(paths_selected)

# ====================================================================
# ОСНОВНОЙ КЛАСС ПРИЛОЖЕНИЯ
# ====================================================================
class FolderGeneratorApp:
    
    def _center_window(self, width=380, height=700): 
        """Центрирует окно приложения на экране."""
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
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
        self.selection_file_path = None 
        
        # НОВОЕ: Словарь для хранения параметров заказа (вместо UI полей)
        self.order_params = {}
        self.selection_data = {} 
        
        self.entries = {} # Содержит только PathSelector и Dummy Entry для совместимости
        
        # ЧЕКБОКСЫ
        self.var_jpg_exported = tk.BooleanVar(value=False)
        self.var_copy_raw_selected = tk.BooleanVar(value=True) 
        self.var_copy_all_files = tk.BooleanVar(value=True)   
        
        self.generate_button = None 
        self.sort_button = None 
        self.logo_image = None
        self.status_label = None
        self.canvas_gen = None 
        self.canvas_sort = None
        
        self.path_shooting_sel = None
        self.checkbox_container = None
        
        self.is_copying = False 
        self.is_sorting_jpg = False 
        self.is_moving_all_raw = False 
        self.is_moving_all_jpg = False # НОВЫЙ ФЛАГ ДЛЯ ПЕРЕМЕЩЕНИЯ JPG

        # --- Загрузка и инициализация ---
        self.config_data = self._load_config()
        self._init_variables_from_config()
        
        self.setup_ui()
        self.set_default_path()
        
        # ИЗМЕНЕНИЕ: Уменьшена высота окна до макета
        self._center_window(width=380, height=550) 
        
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
        """Инициализирует переменные из загруженной конфигурации и заполняет order_params."""
        data = self.config_data
        
        self.shooting_path = data.get('last_shooting_base_path', "") 
        self.output_path = "" 
        
        # Чекбоксы копирования
        self.var_copy_raw_selected.set(data.get('copy_raw_selected_default', True))
        self.var_copy_all_files.set(data.get('copy_all_files_default', True))
        
        # НОВОЕ: Загрузка параметров заказа в словарь (вместо полей UI)
        today = datetime.datetime.now().strftime("%d.%m.%Y")
        self.order_params = {
            "Номер заказа": data.get('order_number', ""), # ИСПРАВЛЕНИЕ: Пусто по умолчанию
            "Дата": data.get('date', today),
            "Номер школы": data.get('school_number', ""), # ИСПРАВЛЕНИЕ: Пусто по умолчанию
            "Класс": data.get('class_name', ""), # ИСПРАВЛЕНИЕ: Пусто по умолчанию
        }

        # НОВОЕ: Создаем Dummy Entry для совместимости с кодом, который вызывает self.entries["Ключ"].get()
        for key, value in self.order_params.items():
             self.entries[key] = self._create_dummy_entry(value)
        
    def _create_dummy_entry(self, initial_value):
        """Создает фиктивный объект с методом get()."""
        class DummyEntry:
            def __init__(self, value):
                self._value = value
            def get(self):
                return self._value
        return DummyEntry(initial_value)

    def save_config(self):
        """Сохраняет текущие настройки в файл .vyipusk_config.json."""
        last_shooting_dir = ""
        if self.shooting_path:
             last_shooting_dir = os.path.dirname(self.shooting_path)

        config_data = {
            'last_shooting_base_path': last_shooting_dir,
            'copy_raw_selected_default': self.var_copy_raw_selected.get(),
            'copy_all_files_default': self.var_copy_all_files.get(),
            # Сохраняем значения параметров заказа из словаря
            'order_number': self.order_params.get("Номер заказа", ""),
            'school_number': self.order_params.get("Номер школы", ""),
            'class_name': self.order_params.get("Класс", ""),
            'date': self.order_params.get("Дата", ""),
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

    def _update_status(self, message, is_error=False, color=None):
        """Обновляет метку статуса внизу."""
        final_color = color if color is not None else COLOR_STATUS_INFO 
        if is_error:
             final_color = COLOR_STATUS_ERROR 
             
        if self.status_label:
            self.status_label.config(text=message, fg=final_color)
            self.master.update_idletasks() 
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
            color = COLOR_BUTTON_DARK if canvas == self.canvas_gen else COLOR_BACKGROUND 
            text_color = "white" if canvas == self.canvas_gen else COLOR_BUTTON_DARK 
            cursor = "hand2"
            outline_color = COLOR_BACKGROUND if canvas == self.canvas_gen else COLOR_BUTTON_DARK 
        else:
            if self.is_copying and canvas == self.canvas_gen:
                 color = COLOR_ACCENT_PINK
                 text_color = "white"
                 text = "Копирование/Перемещение..."
            elif self.is_sorting_jpg and canvas == self.canvas_sort: 
                 color = COLOR_ACCENT_PINK
                 text_color = "white"
                 text = "Сортировка JPG..."
            elif self.is_moving_all_raw and canvas == self.canvas_sort: 
                 color = COLOR_ACCENT_PINK
                 text_color = "white"
                 text = "Перемещение RAW..."
            else:
                 color = COLOR_BUTTON_DISABLED_LIGHT
                 text_color = COLOR_BUTTON_TEXT_DISABLED
            cursor = "arrow" 
            outline_color = COLOR_BUTTON_DISABLED_LIGHT

        self.create_rounded_rectangle(canvas, 1, 1, width-1, height-1, radius, 
                                      fill_color=color, outline_color=outline_color, width=1, tags="button_bg") 
        
        canvas.create_text(width/2, height/2, text=text, 
                           font=(FONT_FAMILY, 14, 'bold'), fill=text_color, tags="button_text")
        
        canvas.config(cursor=cursor)

    def create_styled_checkbox_in_frame(self, master, text, variable, row, col, columnspan, label_right_pad=4, checkbox_type='normal'):
        """
        Создает стилизованный чекбокс.
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
            
            if variable.get():
                active_color = COLOR_ACCENT_PINK
                
                self.create_rounded_rectangle(canvas, x1, y1, x2, y2, checkbox_radius, 
                                              fill_color=active_color, tags="checkbox_outer_border")
                offset_white = 2
                w_x1, w_y1 = x1 + offset_white, y1 + offset_white
                w_x2, w_y2 = x2 - offset_white, y2 - offset_white
                self.create_rounded_rectangle(canvas, w_x1, w_y1, w_x2, w_y2, 
                                              checkbox_radius, fill_color=COLOR_BACKGROUND, tags="checkbox_white_fill")
                offset_pink = 4
                p_x1, p_y1 = x1 + offset_pink, y1 + offset_pink
                p_x2, p_y2 = x2 - offset_pink, y2 - offset_pink
                self.create_rounded_rectangle(canvas, p_x1, p_y1, p_x2, p_y2, 
                                              checkbox_radius, fill_color=active_color, tags="checkbox_inner_fill")
            else:
                outline_color = COLOR_CHECKBOX_BORDER
                self.create_rounded_rectangle(canvas, x1, y1, x2, y2, checkbox_radius, 
                                              fill_color=COLOR_BACKGROUND, outline_color=outline_color, width=1, tags="checkbox_border")
            
        label = tk.Label(internal_frame, text=text, bg=COLOR_BACKGROUND, fg=COLOR_TEXT_NORMAL,
                             font=(FONT_FAMILY, 12), cursor="hand2")
        label.pack(side=tk.LEFT, anchor='w', padx=(0, label_right_pad))

        def toggle_state(event=None):
            variable.set(not variable.get())
            self.check_input_fields() 
        
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
        # ИЗМЕНЕНИЕ: Уменьшена высота до 550
        self._center_window(width=380, height=550) 
        
        main_frame = tk.Frame(self.master, bg=COLOR_BACKGROUND)
        main_frame.pack(pady=20, padx=20, fill="both", expand=True)
        for i in range(4):
            main_frame.grid_columnconfigure(i, weight=1)
            
        # ЛОГОТИП И ЗАГОЛОВОК
        header_frame = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        header_frame.grid(row=1, column=0, columnspan=4, sticky='w', padx=10, pady=(10, 20))
        
        try:
            # ИМИТАЦИЯ ЛОГОТИПА
            logo_label = tk.Label(header_frame, text="ВЫПУСК",
                       font=(FONT_FAMILY, 24, 'bold'),
                       fg=COLOR_ACCENT_PINK, bg=COLOR_BACKGROUND)
            logo_label.pack(side=tk.LEFT)
        except:
            tk.Label(header_frame, text="ВЫПУСК",
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
        self.path_shooting_sel.grid(row=row, column=0, columnspan=4, padx=10, pady=(20, 0), sticky='ew')
        row += 1
        
        # --------------------------------------------------------------------------
        # 2. Файл отчета (ОТОБРАЖЕНИЕ)
        # --------------------------------------------------------------------------
        # ИСПРАВЛЕНИЕ: Поле пустое при старте
        f_selection_file = PathFileSelector(main_frame, "Файл отчета", FONT_FAMILY, 
                                               select_dir=False, 
                                               allow_multiple=False, 
                                               initial_value="", 
                                               on_select_callback=lambda path: self._update_paths_and_check_fields(path, 'selection_file'))
        
        f_selection_file.select_path_or_file = lambda event=None: self._select_txt_file(f_selection_file)

        self.entries["Файл отчета"] = f_selection_file 
        f_selection_file.grid(row=row, column=0, columnspan=4, padx=10, pady=(20, 0), sticky='ew')
        row += 1
        
        # --------------------------------------------------------------------------
        # 3. ПОЛЯ ДАННЫХ УДАЛЕНЫ ИЗ UI
        # --------------------------------------------------------------------------
        
        # --------------------------------------------------------------------------
        # 4. ЧЕКБОКСЫ КОПИРОВАНИЯ
        # --------------------------------------------------------------------------
        copy_checkbox_container = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        copy_checkbox_container.grid(row=row, column=0, columnspan=4, sticky='w', padx=10, pady=(15, 10))
        
        # 4.1 Скопировать отобранные raw
        self.create_styled_checkbox_in_frame(copy_checkbox_container, "Скопировать отобранные raw", self.var_copy_raw_selected, 0, 0, 3, 4, 'copy')
        
        # 4.2 Скопировать все raw и jpg со съемки
        self.create_styled_checkbox_in_frame(copy_checkbox_container, "Скопировать все raw и jpg со съемки", self.var_copy_all_files, 1, 0, 3, 4, 'copy')
        
        row += 1
        
        # --------------------------------------------------------------------------
        # 5. КНОПКА ГЕНЕРАЦИИ (Темная)
        # --------------------------------------------------------------------------
        button_container_1 = tk.Frame(main_frame, bg=COLOR_BACKGROUND, height=BUTTON_HEIGHT)
        button_container_1.grid(row=row, column=0, columnspan=4, padx=10, pady=(10, 20), sticky='ew')
        button_container_1.pack_propagate(False)

        self.canvas_gen = tk.Canvas(button_container_1, bd=0, highlightthickness=0, bg=COLOR_BACKGROUND)
        self.canvas_gen.pack(fill='both', expand=True)

        self.generate_button = tk.Button(state=tk.DISABLED) 
        
        self.canvas_gen.bind("<Configure>", lambda e: self.draw_button(self.canvas_gen, self.generate_button['state'], "Сгенерировать структуру"))
        self.canvas_gen.bind("<Button-1>", lambda e: self._handle_generate_and_copy() if self.generate_button['state'] == tk.NORMAL and not self.is_copying else None)
        self.canvas_gen.config(cursor="hand2")
        
        row += 1
        
        # --------------------------------------------------------------------------
        # 6. ЧЕКБОКС: Я вывел JPG файлы
        # --------------------------------------------------------------------------
        jpg_export_container = tk.Frame(main_frame, bg=COLOR_BACKGROUND)
        jpg_export_container.grid(row=row, column=0, columnspan=4, sticky='w', padx=10, pady=(0, 10))
        
        self.create_styled_checkbox_in_frame(jpg_export_container, "Я вывел jpg файлы", self.var_jpg_exported, 0, 0, 3, 4, 'copy')
        
        row += 1
        
        # --------------------------------------------------------------------------
        # 7. КНОПКА СОРТИРОВКИ (Разложить JPG)
        # --------------------------------------------------------------------------
        button_container_3 = tk.Frame(main_frame, bg=COLOR_BACKGROUND, height=BUTTON_HEIGHT)
        button_container_3.grid(row=row, column=0, columnspan=4, padx=10, pady=(0, 15), sticky='ew')
        button_container_3.pack_propagate(False)

        self.canvas_sort = tk.Canvas(button_container_3, bd=0, highlightthickness=0, bg=COLOR_BACKGROUND)
        self.canvas_sort.pack(fill='both', expand=True)

        self.sort_button = tk.Button(state=tk.DISABLED) # Dummy
        
        self.canvas_sort.bind("<Configure>", lambda e: self.draw_button(self.canvas_sort, self.sort_button['state'], "Разложить jpg по папкам"))
        self.canvas_sort.bind("<Button-1>", lambda e: self._handle_sort_and_move_all_raw() if self.sort_button['state'] == tk.NORMAL and not self.is_sorting_jpg and not self.is_moving_all_raw else None)
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
        desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        if os.path.exists(desktop_path):
            self.output_path = desktop_path
        else:
            self.output_path = os.path.expanduser('~')
        
    def _select_txt_file(self, file_selector_widget):
        """Обработчик выбора TXT файла."""
        initial_dir = os.path.expanduser('~')
        # Если путь к съемке задан, начинаем оттуда
        if self.shooting_path and os.path.exists(self.shooting_path):
             initial_dir = self.shooting_path
             
        # Открываем диалог для выбора файла TXT
        path_selected = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="Выберите файл отчета",
            filetypes=[("Текстовые файлы", "*.txt")]
        )
        
        if path_selected:
            # Обновляем виджет и запускаем колбэк
            file_selector_widget.entry.config(state='normal')
            file_selector_widget.entry.delete(0, tk.END)
            file_selector_widget.entry.insert(0, os.path.basename(path_selected))
            file_selector_widget.entry.config(state='readonly')
            file_selector_widget._float_label(initial_call=True)
            self._update_paths_and_check_fields(path_selected, 'selection_file')

    def _update_paths_and_check_fields(self, path, path_type):
        """Обновляет внутренние переменные и проверяет поля."""
        if path_type == 'shooting_path':
            self.shooting_path = path
            # ИСПРАВЛЕНИЕ: Гарантируем вызов создания/обновления отчета
            self._create_selection_file_template()
        elif path_type == 'selection_file':
            self.selection_file_path = path
            self._process_selection_file(path) 

        self.check_input_fields()

    def _process_selection_file(self, file_path):
        """Обрабатывает TXT файл отчета и заполняет self.selection_data и self.order_params."""
        self.selection_data = self._read_selection_from_file(file_path)
        
        # Обновляем order_params из прочитанных данных для формирования пути
        if self.selection_data.get("ПАРАМЕТРЫ ЗАКАЗА"):
            params = self.selection_data["ПАРАМЕТРЫ ЗАКАЗА"]
            
            order_num_read = params.get("Номер заказа", "").strip()
            date_str_read = params.get("Дата", "").strip()
            is_partial_update = not order_num_read or not date_str_read

            for key, value in params.items():
                self.order_params[key] = value.strip()
                if key in self.entries:
                    self.entries[key] = self._create_dummy_entry(value.strip())
            
            if is_partial_update:
                self._update_status("Отчет загружен, но проверьте Номер заказа и Дату.", is_error=False, color=COLOR_STATUS_INFO)
            else:
                self._update_status(f"Отчет загружен. Параметры заказа: {self.order_params['Номер заказа']}, {self.order_params['Дата']}.", is_error=False)
        
        else:
             self._update_status(f"Отчет загружен, но раздел 'ПАРАМЕТРЫ ЗАКАЗА' не найден.", is_error=False, color=COLOR_STATUS_INFO)
        
    def check_input_fields(self):
        """
        Проверяет заполненность обязательных полей и активирует кнопки.
        ИСПРАВЛЕНА ЛОГИКА: Кнопки активны, если ЕСТЬ путь и ЕСТЬ файл.
        Проверка *содержимого* файла (is_order_ready) происходит при НАЖАТИИ.
        """
        
        # 1. Проверка пути к съемке
        is_path_valid = self.shooting_path and os.path.isdir(self.shooting_path)
        
        # Проверка отчета
        report_exists = self.selection_file_path and os.path.exists(self.selection_file_path)

        # 2. Проверка параметров (ТОЛЬКО для статуса, НЕ для блокировки кнопок)
        order_num = self.order_params.get("Номер заказа", "").strip()
        date_str = self.order_params.get("Дата", "").strip()
        is_order_ready_in_memory = order_num and date_str
             
        # 3. Активация кнопки Генерации
        can_copy_or_move = self.var_copy_raw_selected.get() or self.var_copy_all_files.get()
        new_state_gen = tk.DISABLED
        
        # ИСПРАВЛЕНИЕ: Убрана проверка 'is_order_ready'
        if is_path_valid and report_exists: 
             if self.is_copying:
                 new_state_gen = tk.DISABLED 
             elif can_copy_or_move:
                 if self.var_copy_raw_selected.get() and not report_exists:
                     new_state_gen = tk.DISABLED
                 else:
                     new_state_gen = tk.NORMAL
             else:
                 new_state_gen = tk.NORMAL 
        
        # ИСПРАВЛЕНИЕ: Этот дублирующий блок также исправлен
        if is_path_valid and report_exists:
            new_state_gen = tk.NORMAL if not self.is_copying else tk.DISABLED

        if self.generate_button.cget('state') != new_state_gen:
            self.generate_button.config(state=new_state_gen)
            self.master.after_idle(lambda: self.draw_button(self.canvas_gen , new_state_gen, "Сгенерировать структуру"))

        # 4. Активация кнопки Сортировки
        # ИСПРАВЛЕНИЕ: Здесь также убрана проверка 'is_order_ready'
        can_sort_logic = self.var_jpg_exported.get() and is_path_valid and report_exists
        new_state_sort = tk.DISABLED
        
        if can_sort_logic and not self.is_sorting_jpg and not self.is_moving_all_raw:
            new_state_sort = tk.NORMAL
        
        if self.sort_button.cget('state') != new_state_sort:
            self.sort_button.config(state=new_state_sort)
            self.master.after_idle(lambda: self.draw_button(self.canvas_sort, new_state_sort, "Разложить jpg по папкам"))
            
        # 5. Обновляем статус
        if not self.is_copying and not self.is_sorting_jpg and not self.is_moving_all_raw:
             if not is_path_valid:
                 self._update_status("Выберите Путь к съемке.", is_error=True)
             elif not report_exists:
                 self._update_status("Файл отчета не найден (выберите Путь к съемке).", is_error=True)
             elif not is_order_ready_in_memory:
                 # Эта проверка теперь нужна ТОЛЬКО для статуса
                 self._update_status("Заполните файл отчета.", is_error=False, color=COLOR_STATUS_INFO) 
             elif self.var_copy_raw_selected.get() and not report_exists:
                 self._update_status("Активировано копирование 'отобранных raw', но Отчет не найден.", is_error=True)
             elif new_state_gen == tk.NORMAL or new_state_sort == tk.NORMAL:
                 self._update_status("Готово к работе.", is_error=False)


    def _get_expected_selection_file_path(self):
        """Формирует ожидаемый путь к файлу отчета."""
        if not self.shooting_path or not os.path.isdir(self.shooting_path):
            return None
        filename = "selected.txt"
        return os.path.join(self.shooting_path, filename)

    # ИЗМЕНЕНИЕ: Автоматическое создание TXT-файла
    def _create_selection_file_template(self):
        """Создает ПУСТОЙ TXT-шаблон со всеми секциями и ИНСТРУКЦИЯМИ."""
        
        if not self.shooting_path or not os.path.isdir(self.shooting_path):
             return

        selection_path = self._get_expected_selection_file_path()
        self.selection_file_path = selection_path
        
        today = datetime.datetime.now().strftime("%d.%m.%Y")
        
        # ИСПРАВЛЕНИЕ: Поля пустые по умолчанию, чтобы пользователь их ввел
        mock_data = f"""# ИНСТРУКЦИЯ: Заполните этот файл вручную.
#
# ==================================================
ПАРАМЕТРЫ ЗАКАЗА
# --------------------------------------------------
Номер заказа: 
Дата: {today}
Номер школы: 
Класс: 
# ==================================================

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
            file_was_created = not os.path.exists(selection_path)
            
            if file_was_created: 
                with open(selection_path, 'w', encoding='utf-8') as f:
                    f.write(mock_data)
            
            entry_widget = self.entries.get("Файл отчета")
            if entry_widget:
                entry_widget.entry.config(state='normal')
                entry_widget.entry.delete(0, tk.END)
                entry_widget.entry.insert(0, os.path.basename(selection_path))
                entry_widget.entry.config(state='readonly')
                entry_widget._float_label(initial_call=True)

            
            if file_was_created:
                try:
                    if sys.platform == "win32": subprocess.Popen(['notepad.exe', selection_path])
                    elif sys.platform == "darwin": subprocess.Popen(["open", selection_path])
                    else: subprocess.Popen(["xdg-open", selection_path])
                    
                    self._update_status(f"Отчет создан и открыт: {os.path.basename(selection_path)}.", is_error=False) 
                except Exception as open_e:
                    print(f"Ошибка при попытке открыть файл: {open_e}")
                    self._update_status(f"Отчет найден, но не открыт: {os.path.basename(selection_path)}.", is_error=True) 
            else:
                 self._update_status(f"Отчет найден: {os.path.basename(selection_path)}.", is_error=False) 
            
            self._process_selection_file(selection_path)
            
        except Exception as e:
            self._update_status(f"Ошибка создания/обновления отчета: {e}", is_error=True)
            
        self.check_input_fields()

    def _read_selection_from_file(self, file_path=None):
        """Читает и парсит данные из TXT-файла отчета, включая параметры заказа."""
        path_to_read = file_path if file_path else self.selection_file_path
        
        if not path_to_read or not os.path.exists(path_to_read):
            return {} 

        selection_data = {
            "ПАРАМЕТРЫ ЗАКАЗА": {},
            "Ученики": {}, "Учителя": {}, "Общая": {}, "Групповые": {}, "Фон": {} 
        }
        current_category = None
        
        try:
            # ИСПРАВЛЕНИЕ: Используем utf-8-sig для обработки BOM (метка Блокнота)
            with open(path_to_read, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    
                    if line.startswith('#') or line.startswith('-') or line.startswith('='):
                        continue
                        
                    if not line:
                        continue

                    # --- 1. Определение категории ---
                    if "ПАРАМЕТРЫ ЗАКАЗА" in line:
                        current_category = "ПАРАМЕТРЫ ЗАКАЗА"
                        continue
                    elif "УЧЕНИКИ" in line:
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
                    elif "ФОН" in line: 
                        current_category = "Фон"
                        continue

                    # --- 2. Парсинг: параметры заказа (КЛЮЧ: ЗНАЧЕНИЕ)
                    if current_category == "ПАРАМЕТРЫ ЗАКАЗА":
                        if ':' in line:
                            key, value = line.split(':', 1)
                            # ИСПРАВЛЕНИЕ: Гарантируем удаление всех пробелов и скрытых символов
                            selection_data[current_category][key.strip()] = value.strip()
                        continue
                    
                    # --- 3. Парсинг: Остальные категории (НОМЕРА ФАЙЛОВ)
                    if current_category:
                        match = re.search(r'\d+', line)
                        
                        if not match:
                            continue 

                        name_part = line[:match.start()].strip()
                        num_part = line[match.start():].strip()
                        
                        if not name_part and current_category not in ["Ученики", "Учителя"]:
                            name_part = current_category.lower()

                        numbers = [int(n) for n in re.findall(r'\d+', num_part) if int(n) > 0]
                        
                        if not numbers: continue 

                        if current_category == "Ученики":
                            student_name = self._sanitize_folder_name(name_part)
                            if student_name:
                                raw_line_parts = re.split(r'[\s-]+', line)
                                name_words_count = len(student_name.split())
                                number_parts = raw_line_parts[name_words_count:]
                                
                                position_map = {} 
                                current_pos = 0 
                                for part in number_parts:
                                    if part.isdigit() and int(part) > 0:
                                         if current_pos < 5: 
                                            position_map[int(part)] = current_pos 
                                         current_pos += 1
                                    elif part == '-':
                                       pass
                                
                                if position_map:
                                    selection_data["Ученики"][student_name] = position_map
                                
                        else:
                            description = self._sanitize_folder_name(name_part) 
                            if description:
                                if description in selection_data[current_category]:
                                     selection_data[current_category][description].extend(numbers)
                                else:
                                     selection_data[current_category][description] = numbers
                            
        except Exception as e:
            messagebox.showerror("Ошибка чтения", f"Не удалось прочитать или разобрать файл отчета: {e}")
            return {}
            
        return selection_data

    # ====================================================================
    # НОВАЯ ФУНКЦИЯ ВАЛИДАЦИИ (ПО ЗАПРОСУ)
    # ====================================================================

    def _validate_order_params(self):
        """
        Проверяет, что все КРИТИЧНЫЕ поля из 'ПАРАМЕТРЫ ЗАКАЗА' заполнены.
        Вызывается ПРИ НАЖАТИИ кнопки.
        """
        # 1. Сначала читаем/обновляем данные из файла
        try:
            # _process_selection_file обновит self.order_params
            self._process_selection_file(self.selection_file_path) 
        except Exception as e:
             self._update_status(f"Ошибка чтения файла отчета: {e}", is_error=True)
             messagebox.showerror("Ошибка", f"Не удалось прочитать файл отчета: {e}")
             return False
             
        # 2. Список обязательных полей
        required_fields = ["Номер заказа", "Дата", "Номер школы", "Класс"]
        
        # 3. Проверка
        for field in required_fields:
            value = self.order_params.get(field, "").strip()
            if not value:
                error_msg = f"Ошибка: Не заполнено поле '{field}' в файле отчета."
                self._update_status(error_msg, is_error=True)
                messagebox.showerror("Ошибка валидации", f"{error_msg}\n\nПожалуйста, заполните файл {os.path.basename(self.selection_file_path)} и попробуйте снова.")
                return False # Остановка процесса
        
        # 4. Все поля на месте
        return True

    # ====================================================================
    # ЭТАП 1: СГЕНЕРИРОВАТЬ СТРУКТУРУ (КОПИРОВАНИЕ и ПЕРЕМЕЩЕНИЕ)
    # ====================================================================
    
    def generate_folders(self):
        """Синхронная часть: Генерация структуры папок."""
        # Используем данные из order_params (они УЖЕ проверены и загружены)
        order_num = self._sanitize_folder_name(self.order_params.get("Номер заказа", ""))
        
        self.output_path = self.shooting_path
        
        # self.selection_data и self.order_params УЖЕ должны быть загружены
        # _validate_order_params -> _process_selection_file
        
        if not self.selection_data:
             self._process_selection_file(self.selection_file_path)

        students_map = self.selection_data.get("Ученики", {})
        students = list(students_map.keys())
        
        # --- Создание структуры ---
        # ИСПРАВЛЕНИЕ: Используем self.master.after для обновления UI из потока
        self.master.after(0, self._update_status, "Создание структуры папок...", False)
        self.output_path, target_folder_path, _ = self._get_folder_paths(order_num)
        self._create_folder_structure(target_folder_path, students)
        
        # ИСПРАВЛЕНИЕ: Используем self.master.after для обновления UI из потока
        self.master.after(0, self._update_status, f"УСПЕХ! Структура папок '{target_folder_path.name}' создана.", False)
        self.save_config() 
        return target_folder_path

    def _handle_generate_and_copy(self):
        """Обрабатывает нажатие кнопки Генерация + Копирование/Перемещение."""
        if self.is_copying:
            return 
            
        # 1. НОВАЯ ВАЛИДАЦИЯ (по запросу)
        if not self._validate_order_params():
            return # Ошибка уже показана, процесс остановлен

        # 2. Проверка пути (остается)
        if not self.shooting_path or not self.selection_file_path:
            self._update_status("Пожалуйста, выберите путь к съемке и Отчет.", is_error=True)
            return

        # Валидация пройдена, используем загруженные параметры
        order_num = self.order_params.get("Номер заказа", "").strip()
        
        # 3. Подготовка к потоковому копированию/перемещению
        copy_selected = self.var_copy_raw_selected.get()
        copy_all = self.var_copy_all_files.get()
        
        if copy_selected or copy_all:
             self.is_copying = True
             self.generate_button['state'] = tk.DISABLED
             self.draw_button(self.canvas_gen, tk.DISABLED, "Сгенерировать структуру")
             self.master.after(0, self._update_status, "Начало подготовки к копированию/перемещению...", False)
             
             shooting_path = Path(self.shooting_path)

             # 4. ЛОГИКА КОПИРОВАНИЯ/ПЕРЕМЕЩЕНИЯ (в новом потоке):
             threading.Thread(target=self._copy_move_files_task_wrapper, 
                               args=(order_num, shooting_path)).start()
        
        # 5. Если копирование не выбрано (только генерация структуры)
        else:
             try:
                 self.generate_folders()
             except Exception as e:
                 self._update_status(f"Ошибка при создании структуры папок: {e}", is_error=True)
             self.check_input_fields()


    def _copy_move_files_task_wrapper(self, order_num, shooting_path):
        """
        Обёртка для потокового выполнения задач КОПИРОВАНИЯ/ПЕРЕМЕЩЕНИЯ (Фаза 1).
        """
        
        # ИСПРАВЛЕНИЕ: Генерация папок теперь происходит ВНУТРИ потока
        try:
            target_folder_path = self.generate_folders()
        except Exception as e:
            self.master.after(0, self._update_status, f"Ошибка при создании структуры папок: {e}", is_error=True)
            self.is_copying = False
            self.master.after(0, self.check_input_fields)
            return
            
        copy_selected = self.var_copy_raw_selected.get()
        copy_all = self.var_copy_all_files.get()
        
        total_stages = 0
        if copy_selected: total_stages += 1
        if copy_all: total_stages += 2 

        current_stage = 0

        # 1. --- ЭТАП 1/3: КОПИРОВАНИЕ ОТОБРАННЫХ RAW ---
        if copy_selected:
            current_stage += 1
            # self.selection_data уже загружен в generate_folders()
            self._process_files_by_type(order_num, target_folder_path, shooting_path, stage_num=current_stage, total_stages=total_stages, file_type="selected_raw", operation=shutil.copy2)
        
        # 2. --- ЭТАП 2/3: ПЕРЕМЕЩЕНИЕ ВСЕХ RAW ---
        if copy_all:
             current_stage += 1
             self._process_files_by_type(order_num, target_folder_path, shooting_path, stage_num=current_stage, total_stages=total_stages, file_type="all_raw", operation=shutil.move)

        # 3. --- ЭТАП 3/3: ПЕРЕМЕЩЕНИЕ ВСЕХ JPG ---
        if copy_all:
             current_stage += 1
             self._process_files_by_type(order_num, target_folder_path, shooting_path, stage_num=current_stage, total_stages=total_stages, file_type="all_jpg", operation=shutil.move)

        # 4. Завершение
        self.is_copying = False
        self.master.after(0, self.check_input_fields)
        self.master.after(0, self.draw_button, self.canvas_gen, self.generate_button['state'], "Сгенерировать структуру")
        self.master.after(0, self._on_copy_complete_open_folder, order_num, copy_selected)

    def _process_files_by_type(self, order_num, target_folder_path, shooting_path, stage_num, total_stages, file_type, operation):
        """
        Универсальная функция для выполнения одного этапа КОПИРОВАНИЯ/ПЕРЕМЕЩЕНИЯ.
        ИСПРАВЛЕНА: Добавлены статусы "Поиск...".
        """
        
        # 1. Определение источников и назначений
        if file_type == "selected_raw":
            # ИСПРАВЛЕНИЕ: Немедленное обновление статуса
            self.master.after(0, self._update_status, f"[Этап {stage_num}/{total_stages}] Поиск отобранных RAW...", color=COLOR_STATUS_INFO)
            
            target_dir = Path(target_folder_path) / f"{order_num} дубли равы" / "отобранный материал"
            stage_name = "RAW (Отбор)"
            
            selected_numbers = []
            for category, items in self.selection_data.items():
                if category in ["Ученики", "Учителя", "Общая", "Групповые", "Фон"]:
                    for description, numbers_or_map in items.items():
                        if isinstance(numbers_or_map, dict):
                            selected_numbers.extend(numbers_or_map.keys())
                        else:
                            selected_numbers.extend(numbers_or_map)
            
            unique_file_numbers = sorted(list(set(selected_numbers))) 
            files_to_process = [self._find_file_by_number(shooting_path, num) for num in unique_file_numbers if self._find_file_by_number(shooting_path, num)]
            files_to_copy = [os.path.basename(f) for f in files_to_process if f]

        elif file_type == "all_raw":
            # ИСПРАВЛЕНИЕ: Немедленное обновление статуса
            self.master.after(0, self._update_status, f"[Этап {stage_num}/{total_stages}] Поиск ВСЕХ RAW...", color=COLOR_STATUS_INFO)
            
            target_dir = Path(target_folder_path) / f"{order_num} дубли равы" / "дубли"
            stage_name = "RAW (Все)"
            files_to_copy = [f for f in os.listdir(shooting_path) if Path(f).suffix.lower() in RAW_EXTENSIONS and Path(shooting_path / f).is_file()]

        elif file_type == "all_jpg":
            # ИСПРАВЛЕНИЕ: Немедленное обновление статуса
            self.master.after(0, self._update_status, f"[Этап {stage_num}/{total_stages}] Поиск ВСЕХ JPG...", color=COLOR_STATUS_INFO)
            
            target_dir = Path(target_folder_path) / f"{order_num} дубли"
            stage_name = "JPG (Все)"
            files_to_copy = [f for f in os.listdir(shooting_path) if Path(f).suffix.lower() in ['.jpg', '.jpeg'] and Path(shooting_path / f).is_file()]
        else:
             return

        # 2. Выполнение операции
        processed_count = 0
        total_files = len(files_to_copy)
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        operation_name = "Копирование" if operation == shutil.copy2 else "Перемещение"
        
        for i, filename in enumerate(files_to_copy):
            if not self.is_copying: break 
            
            source_path = Path(shooting_path) / filename
            target_path = Path(target_dir) / filename
            
            if source_path.is_file():
                try:
                    if operation == shutil.move:
                        if target_path.exists():
                           target_path.unlink() 
                           
                    operation(source_path, target_path)
                    processed_count += 1
                except Exception as e:
                    self.master.after(0, self._update_status, f"[{stage_num}/{total_stages}] Ошибка {operation_name} {filename}: {e}", is_error=True)
            
            # Обновляем статус только каждые N файлов, чтобы не тормозить UI
            if i % 5 == 0 or (i + 1) == total_files:
                progress = int((i + 1) / total_files * 100)
                self.master.after(0, self._update_status, f"[Этап {stage_num}/{total_stages}] {operation_name} {stage_name}: {progress}% ({i+1}/{total_files} файлов)", color=COLOR_STATUS_INFO)
        
        self.master.after(0, self._update_status, f"{operation_name} {stage_name} завершено ({processed_count} файлов).", is_error=False)


    def _on_copy_complete_open_folder(self, order_num, open_selected_raw_folder):
        """Восстанавливает UI и открывает папку."""
        
        self.is_copying = False
        self.check_input_fields()
        
        if open_selected_raw_folder:
            # Открываем папку с отобранным материалом, если было выбрано
            order_path_name = self._get_folder_paths(order_num)[1]
            target_raw_dir = order_path_name / f"{order_num} дубли равы" / "отобранный материал"
            
            if target_raw_dir.is_dir():
                 self.master.after(0, self._update_status, f"Открытие папки 'отобранный материал'...", is_error=False) 
                 try:
                     if sys.platform == "win32":
                         os.startfile(target_raw_dir)
                     elif sys.platform == "darwin": 
                         subprocess.Popen(["open", target_raw_dir])
                     else: 
                         subprocess.Popen(["xdg-open", target_raw_dir])
                 except Exception as e:
                     print(f"Ошибка при попытке открыть папку: {e}")
                     self.master.after(0, self._update_status, "Папка создана, но не открыта автоматически.", True)
        
    def _find_file_by_number(self, directory, number):
        """
        Ищет файл в директории по номеру, игнорируя расширение, но ПРЕДПОЧИТАЯ RAW.
        ИСПРАВЛЕНА ОШИБКА REGEX
        """
        if not directory or not os.path.isdir(directory):
            return None
            
        target_filename_part = str(number)
        
        for filename in os.listdir(directory):
            name_without_ext, ext = os.path.splitext(filename)
            ext_lower = ext.lower()
            
            if ext_lower not in RAW_EXTENSIONS:
                 continue
                 
            # ИСПРАВЛЕНИЕ: Ищем 1+ цифр (\d+), а не 1-5 (\d{1,5})
            match = re.search(r'(\d+)$', name_without_ext) 
            
            if match:
                 found_number = match.group(1)
                 
                 if int(found_number) == number:
                     return os.path.join(directory, filename)
                     
                 if found_number.lstrip('0') == target_filename_part:
                     return os.path.join(directory, filename)
                     
            if name_without_ext.endswith(target_filename_part):
                idx = name_without_ext.rfind(target_filename_part)
                if idx == 0 or not name_without_ext[idx-1].isdigit():
                     return os.path.join(directory, filename)
                     
            for z in [3, 4, 5]:
                padded_num = target_filename_part.zfill(z)
                if name_without_ext.endswith(padded_num):
                    return os.path.join(directory, filename)
                    
        return None

    # ====================================================================
    # ФУНКЦИИ СТРУКТУРЫ ПАПОК (ВОССТАНОВЛЕННАЯ ЛОГИКА)
    # ====================================================================

    def _get_folder_paths(self, order_num):
        """Возвращает пути для генерации структуры (ВОССТАНОВЛЕННАЯ ЛОГИКА)."""
        
        output_base_dir = Path(self.output_path)
        
        # ИСПРАВЛЕНИЕ: Главная папка - только номер заказа
        target_folder_path = output_base_dir / self._sanitize_folder_name(order_num)
        
        # Внутренняя папка заказа (для сортировки)
        date_str = self.order_params.get("Дата", "").strip()
        school_str = self.order_params.get("Номер школы", "").strip()
        class_str = self.order_params.get("Класс", "").strip()
        
        # Путь к папке, куда будут сортироваться JPG
        sort_target_base = target_folder_path / order_num / school_str / date_str / class_str

        return output_base_dir, target_folder_path, sort_target_base

    def _create_folder_structure(self, target_folder_path, students):
        """Создает необходимую структуру папок (ВОССТАНОВЛЕННАЯ ЛОГИКА)."""
        
        target_folder_path.mkdir(parents=True, exist_ok=True)
        
        # Используем параметры из словаря
        order_num = self.order_params.get("Номер заказа", "").strip()
        school_num = self.order_params.get("Номер школы", "").strip()
        date = self.order_params.get("Дата", "").strip()
        class_name = self.order_params.get("Класс", "").strip()

        # Создаем вложенную структуру
        base_material_folder = Path(target_folder_path) / order_num / school_num / date / class_name
        
        (base_material_folder / "доки").mkdir(parents=True, exist_ok=True)
        (base_material_folder / "здание").mkdir(parents=True, exist_ok=True)
        (base_material_folder / "общая").mkdir(parents=True, exist_ok=True)
        (base_material_folder / "репортаж").mkdir(parents=True, exist_ok=True)
        (base_material_folder / "учителя").mkdir(parents=True, exist_ok=True)
        (base_material_folder / "фон").mkdir(parents=True, exist_ok=True)
        
        # Папки учеников
        student_folder = base_material_folder / "ученики"
        student_folder.mkdir(parents=True, exist_ok=True)
        for s in students:
            (student_folder / s).mkdir(exist_ok=True)

        # Папки для дубликатов (в корневой папке заказа)
        Path(target_folder_path / f"{order_num} дубли").mkdir(exist_ok=True) 
        Path(target_folder_path / f"{order_num} дубли равы" / "дубли").mkdir(parents=True, exist_ok=True) 
        Path(target_folder_path / f"{order_num} дубли равы" / "отобранный материал").mkdir(parents=True, exist_ok=True) 
        
        # ИСПРАВЛЕНИЕ: Используем self.master.after для обновления UI из потока
        self.master.after(0, self._update_status, "Структура папок создана успешно.", False)


    # ====================================================================
    # ЭТАП 2: РАЗЛОЖИТЬ JPG ПО ПАПКАМ (СОРТИРОВКА)
    # ====================================================================

    def _handle_sort_and_move_all_raw(self):
        """Обрабатывает нажатие кнопки Сортировка JPG."""
        if self.is_sorting_jpg or self.is_moving_all_raw:
            return

        # 1. НОВАЯ ВАЛИДАЦИЯ (по запросу)
        if not self._validate_order_params():
            return # Ошибка уже показана, процесс остановлен

        # Валидация пройдена, используем загруженные параметры
        order_num = self.order_params.get("Номер заказа", "").strip()
        
        # ИСПРАВЛЕНИЕ: Используем _get_folder_paths для получения правильного пути
        _, main_order_folder, _ = self._get_folder_paths(order_num)
        
        if not main_order_folder.is_dir():
             messagebox.showerror("Ошибка", f"Основная папка заказа не найдена. Сначала выполните 'Сгенерировать структуру'.")
             self._update_status("Сортировка отменена.", is_error=True)
             return

        source_material_dir = main_order_folder / f"{order_num} дубли равы" / "отобранный материал"
        
        if not source_material_dir.is_dir():
             messagebox.showerror("Ошибка", "Папка 'отобранный материал' не найдена. Убедитесь, что вы выполнили копирование.")
             self._update_status("Сортировка отменена.", is_error=True)
             return

        jpg_files_to_move = [f for f in os.listdir(source_material_dir) if Path(f).suffix.lower() in ['.jpg', '.jpeg']]
        
        if not jpg_files_to_move:
             messagebox.showwarning("Внимание", "В папке 'отобранный материал' не найдены JPG файлы. Сортировка невозможна.")
             self._update_status("Сортировка отменена: JPG файлы не найдены.", is_error=True)
             return


        # 3. Загружаем данные для сортировки (selection_data уже загружен)
        if not any(self.selection_data.values()):
             self._update_status("Отчет пуст. Невозможно выполнить сортировку.", is_error=True)
             return

        # 4. Получение путей
        self.output_path, target_folder_path, _ = self._get_folder_paths(order_num)

        # 5. ЛОГИКА ПЕРЕМЕЩЕНИЯ (в потоке)
        self.is_sorting_jpg = True
        self.check_input_fields()

        threading.Thread(target=self._sort_jpg_files_task, args=(target_folder_path,)).start()
        
    def _sort_jpg_files_task(self, target_folder_path):
        """Задача: Сортировка JPG файлов и их переименование (ПЕРЕМЕЩЕНИЕ)."""
        
        sorted_count = 0
        
        try:
            order_num = self.order_params.get("Номер заказа", "").strip()
            # ИСПРАВЛЕНИЕ: Целевая папка для сортировки (старая структура)
            base_sort_dir = Path(target_folder_path) / order_num / self.order_params.get("Номер школы", "").strip() / self.order_params.get("Дата", "").strip() / self.order_params.get("Класс", "").strip()
            
            source_material_dir = Path(target_folder_path) / f"{order_num} дубли равы" / "отобранный материал"

            jpg_files_to_move = [f for f in os.listdir(source_material_dir) if Path(f).suffix.lower() in ['.jpg', '.jpeg']]
            total_files = len(jpg_files_to_move)
            
            # self.selection_data уже загружен
            students_map = self.selection_data.get("Ученики", {})
            teachers_map = self.selection_data.get("Учителя", {})
            general_map = self.selection_data.get("Общая", {})
            group_map = self.selection_data.get("Групповые", {})
            font_map = self.selection_data.get("Фон", {})
            
            for i, filename in enumerate(jpg_files_to_move):
                if not self.is_sorting_jpg: break 
                
                source_path = source_material_dir / filename
                
                progress_percent = int(((i + 1) / total_files) * 100)
                self.master.after(0, self._update_status, f"Сортировка JPG: {progress_percent}% ({filename})...", False)

                target_sub_dir, new_filename, is_friend_photo = self._get_target_directory(
                    base_sort_dir, filename, 
                    students_map, teachers_map, general_map, group_map, font_map
                )
                
                final_target_path = Path(target_sub_dir) / new_filename
                Path(target_sub_dir).mkdir(parents=True, exist_ok=True)
                
                # Операция: Перемещение/Вырезание (shutil.move)
                
                try:
                    shutil.move(source_path, final_target_path)
                    sorted_count += 1
                except FileNotFoundError:
                     print(f"Предупреждение: Файл {filename} уже перемещен или не существует.")
                except Exception as e:
                    self.master.after(0, messagebox.showerror, "Ошибка сортировки", f"Не удалось переместить {filename}: {e}")
                    print(f"Ошибка перемещения {filename}: {e}")
            
            self.master.after(0, self._update_status, f"Сортировка JPG завершена. Перемещено {sorted_count} файлов.", is_error=False)
            
        except Exception as e:
            self.master.after(0, self._update_status, f"Критическая ошибка при сортировке JPG: {e}", is_error=True)
        finally:
            self.is_sorting_jpg = False
            self.check_input_fields()
            
            self.master.after(0, self._update_status, f"Разложить JPG по папкам завершено.", is_error=False)


    def _get_target_directory(self, base_dir, filename, students_map, teachers_map, general_map, group_map, font_map):
        """
        Определяет целевую папку и новое имя для файла.
        Возвращает (target_folder, new_filename, is_friend_photo: bool).
        """
        
        original_filename_no_ext = os.path.splitext(filename)[0]
        
        # 1. Извлекаем номер из имени JPG-файла
        match_num = re.search(r'(\d+)(?!.*\d)', original_filename_no_ext)
        file_number = int(match_num.group(1)) if match_num else None
        
        if not file_number:
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
                teacher_description = self._sanitize_folder_name(teacher_key)
                original_ext = os.path.splitext(filename)[1]
                new_filename = f"{teacher_description}{original_ext}" 
                return os.path.join(base_dir, 'учителя'), new_filename, False

        # --- 1.3. Поиск по ОБЩАЯ/РЕПОРТАЖ/ФОН ---
        for category_name, category_map in {
            "общая": general_map, 
            "репортаж": group_map, 
            "фон": font_map
        }.items():
            for description, numbers in category_map.items():
                 if file_number in numbers:
                     new_filename = f"{description}_{filename}" 
                     return os.path.join(base_dir, category_name), new_filename, False
        
        # --- 2. Fallback для файлов без номеров или без совпадений ---
        if filename.lower().startswith('зд_'):
            return os.path.join(base_dir, 'здание'), filename, False

        # --- 3. По умолчанию (если не найдено) ---
        return os.path.join(base_dir, "общая"), filename, False


    def _get_renamed_path_and_folder(self, base_dir, filename, student_name, file_number, position_map):
        """
        Определяет целевую папку и НОВОЕ ИМЯ для файла ученика.
        Возвращает (target_folder, new_filename).
        """
        position_index = position_map.get(file_number)
        original_ext = os.path.splitext(filename)[1]
        
        target_folder = os.path.join(base_dir, "ученики", student_name)
        new_filename = filename # Default: оригинальное имя

        if position_index is not None:
            if 0 <= position_index <= 2:
                type_key = STUDENT_POSITIONS[position_index]
                
                if type_key == "Виньетка":
                    new_filename = f"{student_name}{original_ext}"
                elif type_key.startswith("ЛР"):
                    new_filename = f"ЛР_{student_name}{original_ext}"
                elif type_key.startswith("ЛС"):
                    new_filename = f"ЛС_{student_name}{original_ext}"
                
            elif position_index in [3, 4]:
                new_filename = filename 
                
        return target_folder, new_filename

if __name__ == "__main__":
    if not os.path.exists(resource_path("assets/logo.png")):
        try:
            from PIL import Image
            dummy_img = Image.new('RGB', (100, 38), color = COLOR_ACCENT_PINK)
        except ImportError:
            pass

    root = tk.Tk()
    app = FolderGeneratorApp(root)
    root.mainloop()