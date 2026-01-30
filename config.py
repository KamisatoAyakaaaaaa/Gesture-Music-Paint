# -*- coding: utf-8 -*-
"""
配置模块 - 系统参数定义
"""

# 视觉采集配置
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_INDEX = 0

# 界面配置
HEADER_HEIGHT = 60
UI_PADDING = 15

# 音乐系统配置
MIN_NOTE = 48   # C3
MAX_NOTE = 84   # C6
MIN_NOTE_DURATION = 100
MAX_NOTE_DURATION = 500
DEFAULT_NOTE_DURATION = 200
MIN_VOLUME = 30
MAX_VOLUME = 127
BPM = 120
BEAT_INTERVAL = 60000 // BPM

# 乐器配置
INSTRUMENTS = {
    'piano': {
        'name': '钢琴',
        'name_en': 'Piano',
        'color': (255, 200, 100),
        'midi_program': 0,
        'wave_type': 'sine',
        'icon': 'piano'
    },
    'guitar': {
        'name': '吉他',
        'name_en': 'Guitar',
        'color': (100, 200, 255),
        'midi_program': 25,
        'wave_type': 'triangle',
        'icon': 'guitar'
    },
    'drums': {
        'name': '鼓',
        'name_en': 'Drums',
        'color': (100, 100, 255),
        'midi_program': 118,
        'wave_type': 'noise',
        'icon': 'drums'
    },
    'synth': {
        'name': '合成器',
        'name_en': 'Synth',
        'color': (255, 100, 200),
        'midi_program': 81,
        'wave_type': 'square',
        'icon': 'synth'
    },
    'strings': {
        'name': '弦乐',
        'name_en': 'Strings',
        'color': (100, 255, 150),
        'midi_program': 48,
        'wave_type': 'sawtooth',
        'icon': 'strings'
    }
}

INSTRUMENT_LIST = ['piano', 'guitar', 'drums', 'synth', 'strings']
DEFAULT_INSTRUMENT = 'piano'

# 画笔配置
MIN_BRUSH_THICKNESS = 3
MAX_BRUSH_THICKNESS = 30
DEFAULT_BRUSH_THICKNESS = 10
BRUSH_THICKNESS_OPTIONS = [5, 10, 15, 20, 25]

# 手势识别配置
DETECTION_CONFIDENCE = 0.7
TRACKING_CONFIDENCE = 0.5
MAX_HANDS = 1
SMOOTHING_FACTOR = 0.5
GESTURE_COOLDOWN = 3
FIST_COOLDOWN = 30
PEACE_COOLDOWN = 30
FIVE_COOLDOWN = 30

# 音波可视化配置
WAVEFORM_HEIGHT = 100
WAVEFORM_SEGMENTS = 64
WAVEFORM_DECAY = 0.95
WAVEFORM_COLOR = (255, 255, 0)
PARTICLE_COUNT = 50
PARTICLE_LIFETIME = 30
PARTICLE_SPEED = 5

# 撤销/重做系统
MAX_UNDO_STEPS = 20

# 录制系统配置
RECORDING_FOLDER = "Recordings"
MAX_RECORDING_TIME = 300
RECORDING_FPS = 30

# 状态显示配置
SHOW_STATUS = True
STATUS_FONT_SCALE = 0.6
STATUS_COLOR = (255, 255, 255)
STATUS_BG_COLOR = (30, 30, 35)

# 快捷键映射
KEY_ESC = 27
KEY_SPACE = 32
KEY_C = ord('c')
KEY_Z = ord('z')
KEY_Y = ord('y')
KEY_S = ord('s')
KEY_R = ord('r')
KEY_1 = ord('1')
KEY_2 = ord('2')
KEY_3 = ord('3')
KEY_4 = ord('4')
KEY_5 = ord('5')
KEY_TAB = 9
KEY_P = ord('p')

# 音阶配置
SCALE_TYPES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'pentatonic': [0, 2, 4, 7, 9],
    'blues': [0, 3, 5, 6, 7, 10],
    'chromatic': list(range(12)),
}

DEFAULT_SCALE = 'pentatonic'
DEFAULT_ROOT = 60


# 辅助函数

def map_x_to_note(x: int, width: int = CAMERA_WIDTH) -> int:
    """将X坐标映射到MIDI音符"""
    x = max(0, min(x, width - 1))
    note = int(MIN_NOTE + (x / width) * (MAX_NOTE - MIN_NOTE))
    return note


def map_y_to_duration(y: int, height: int = CAMERA_HEIGHT) -> int:
    """将Y坐标映射到音符时值（上快下慢）"""
    y = max(HEADER_HEIGHT, min(y, height - 1))
    effective_height = height - HEADER_HEIGHT
    ratio = (y - HEADER_HEIGHT) / effective_height
    duration = int(MIN_NOTE_DURATION + ratio * (MAX_NOTE_DURATION - MIN_NOTE_DURATION))
    return duration


def map_thickness_to_volume(thickness: int) -> int:
    """将画笔粗细映射到音量"""
    thickness = max(MIN_BRUSH_THICKNESS, min(thickness, MAX_BRUSH_THICKNESS))
    ratio = (thickness - MIN_BRUSH_THICKNESS) / (MAX_BRUSH_THICKNESS - MIN_BRUSH_THICKNESS)
    volume = int(MIN_VOLUME + ratio * (MAX_VOLUME - MIN_VOLUME))
    return volume


def quantize_to_scale(note: int, scale_type: str = DEFAULT_SCALE, root: int = DEFAULT_ROOT) -> int:
    """将音符量化到指定音阶"""
    scale = SCALE_TYPES.get(scale_type, SCALE_TYPES['pentatonic'])
    relative = (note - root) % 12
    octave = (note - root) // 12
    closest = min(scale, key=lambda s: abs(s - relative))
    return root + octave * 12 + closest
