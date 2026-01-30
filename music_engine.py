# -*- coding: utf-8 -*-
"""
音乐引擎模块 - 负责音符生成、播放、录制和音波可视化
"""

import numpy as np
import threading
import time
import os
import wave
import struct
import logging
from collections import deque
from datetime import datetime

logger = logging.getLogger('GesturePaint.Music')

try:
    import pygame
    import pygame.mixer
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logger.warning("pygame 未安装，音频功能将被禁用")

from config import (
    MIN_NOTE, MAX_NOTE, MIN_VOLUME, MAX_VOLUME,
    DEFAULT_NOTE_DURATION, BPM, BEAT_INTERVAL,
    INSTRUMENTS, INSTRUMENT_LIST, DEFAULT_INSTRUMENT,
    SCALE_TYPES, DEFAULT_SCALE, DEFAULT_ROOT,
    map_x_to_note, map_y_to_duration, map_thickness_to_volume,
    quantize_to_scale, RECORDING_FOLDER, WAVEFORM_SEGMENTS
)


class NoteEvent:
    """音符事件"""
    def __init__(self, note: int, velocity: int, duration: int, 
                 instrument: str, timestamp: float, x: int = 0, y: int = 0):
        self.note = note
        self.velocity = velocity
        self.duration = duration
        self.instrument = instrument
        self.timestamp = timestamp
        self.x = x
        self.y = y
    
    def to_dict(self):
        return {
            'note': self.note,
            'velocity': self.velocity,
            'duration': self.duration,
            'instrument': self.instrument,
            'timestamp': self.timestamp,
            'x': self.x,
            'y': self.y
        }


class MusicEngine:
    """
    音乐引擎 - 负责音符生成、播放和录制
    """
    
    # 音符名称映射
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    def __init__(self):
        # 音频系统
        self.audio_initialized = False
        self._init_audio()
        
        # 当前乐器
        self.current_instrument = DEFAULT_INSTRUMENT
        self.instrument_index = INSTRUMENT_LIST.index(DEFAULT_INSTRUMENT)
        
        # 音阶设置
        self.scale_type = DEFAULT_SCALE
        self.root_note = DEFAULT_ROOT
        
        # 播放状态
        self.is_playing = True  # 是否允许播放音符
        self.is_recording = False
        
        # 音符缓冲（防止重复播放）
        self.last_note = -1
        self.last_note_time = 0
        self.min_note_interval = 0.02  # 最小音符间隔（秒）- 降低延迟
        
        # Preview 音控制（时间+距离阈值）
        self.last_preview_x = 0
        self.last_preview_y = 0
        self.last_preview_time = 0
        self.preview_min_interval = 0.08    # Preview 最小时间间隔（秒）
        self.preview_min_distance = 30      # Preview 最小移动距离（像素）
        
        # 录制数据
        self.recorded_notes = []
        self.recording_start_time = 0
        
        # 音波数据（用于可视化）
        self.waveform_data = np.zeros(WAVEFORM_SEGMENTS)
        self.waveform_lock = threading.Lock()
        
        # 活跃音符（用于可视化）
        self.active_notes = deque(maxlen=20)
        
        # 音乐性增强（可开关）
        self.drum_enabled = False           # 鼓点开关
        self.bass_enabled = False           # 低音开关
        self.chord_enabled = False          # 和弦开关
        
        # 鼓点节奏
        self.drum_patterns = {
            'basic': [1, 0, 0, 0, 1, 0, 0, 0],      # 基础四拍
            'rock': [1, 0, 1, 0, 1, 0, 1, 0],        # 摇滚
            'hihat': [1, 1, 1, 1, 1, 1, 1, 1]        # 踩镲
        }
        self.current_drum_pattern = 'basic'
        self.drum_beat_index = 0
        self.last_drum_time = 0
        
        # 低音参数
        self.bass_interval = 0.5            # 低音间隔（秒）
        self.last_bass_time = 0
        self.bass_note = 36                 # 默认低音（C2）
        
        # 和弦缓存
        self.chord_cache = {}
        
        # 节拍器
        self.metronome_enabled = False
        self.metronome_volume = 0.5
        self.last_metronome_time = 0
        self.metronome_beat_index = 0
        
        # 伴奏强度 (off, low, high)
        self.accompaniment_level = 'off'
        
        # 预生成的音符音频缓存
        self.note_cache = {}
        self._pregenerate_notes()
        self._pregenerate_drums()
        self._pregenerate_bass()
        self._pregenerate_metronome()
    
    def _init_audio(self):
        """初始化音频系统"""
        if not PYGAME_AVAILABLE:
            return
        
        try:
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=256)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)  # 增加通道数
            self.audio_initialized = True
            logger.info("音频系统初始化完成")
            
            # 预热音频系统：播放一个静音来激活
            self._warmup_audio()
        except Exception as e:
            logger.error(f"音频初始化失败: {e}")
            self.audio_initialized = False
    
    def _warmup_audio(self):
        """预热音频系统，避免首次播放延迟"""
        try:
            # 生成一个极短的静音并播放
            silent = np.zeros(100, dtype=np.int16)
            sound = pygame.sndarray.make_sound(np.column_stack([silent, silent]))
            sound.set_volume(0)
            sound.play()
            logger.debug("音频系统预热完成")
        except Exception as e:
            logger.warning(f"音频预热失败: {e}")
    
    def _pregenerate_notes(self):
        """预生成常用音符的音频"""
        if not self.audio_initialized:
            return
        
        logger.info("正在预生成音符音频...")
        
        for instrument_key in INSTRUMENT_LIST:
            instrument = INSTRUMENTS[instrument_key]
            wave_type = instrument['wave_type']
            
            for note in range(MIN_NOTE, MAX_NOTE + 1):
                freq = self._note_to_freq(note)
                sound = self._generate_tone(freq, 0.3, wave_type)
                if sound:
                    cache_key = f"{instrument_key}_{note}"
                    self.note_cache[cache_key] = sound
        
        logger.info(f"预生成完成，共 {len(self.note_cache)} 个音符")
        
        # 预热所有乐器：静音播放一个音符激活缓存
        self._warmup_instruments()
    
    def _warmup_instruments(self):
        """预热所有乐器，避免首次切换延迟"""
        try:
            for instrument_key in INSTRUMENT_LIST:
                cache_key = f"{instrument_key}_60"  # 中央 C
                sound = self.note_cache.get(cache_key)
                if sound:
                    sound.set_volume(0)  # 静音
                    sound.play()
                    sound.stop()
            logger.debug("所有乐器预热完成")
        except Exception as e:
            logger.warning(f"乐器预热失败: {e}")
    
    def _pregenerate_drums(self):
        """预生成鼓音色"""
        if not self.audio_initialized:
            return
        
        try:
            # 底鼓
            kick = self._generate_drum_sound('kick')
            if kick:
                self.note_cache['drum_kick'] = kick
            
            # 军鼓
            snare = self._generate_drum_sound('snare')
            if snare:
                self.note_cache['drum_snare'] = snare
            
            # 踩镲
            hihat = self._generate_drum_sound('hihat')
            if hihat:
                self.note_cache['drum_hihat'] = hihat
            
            logger.debug("鼓音色预生成完成")
        except Exception as e:
            logger.warning(f"鼓音色生成失败: {e}")
    
    def _generate_drum_sound(self, drum_type: str):
        """生成鼓音色"""
        sample_rate = 44100
        
        if drum_type == 'kick':
            # 底鼓：低频正弦波 + 快速衰减
            duration = 0.3
            t = np.linspace(0, duration, int(sample_rate * duration))
            freq = 60 * np.exp(-t * 10)  # 频率下降
            wave = np.sin(2 * np.pi * freq * t)
            envelope = np.exp(-t * 8)
            wave = wave * envelope
            
        elif drum_type == 'snare':
            # 军鼓：噪声 + 短正弦
            duration = 0.2
            t = np.linspace(0, duration, int(sample_rate * duration))
            noise = np.random.uniform(-1, 1, len(t))
            tone = np.sin(2 * np.pi * 200 * t)
            wave = noise * 0.7 + tone * 0.3
            envelope = np.exp(-t * 15)
            wave = wave * envelope
            
        elif drum_type == 'hihat':
            # 踩镲：高频噪声
            duration = 0.1
            t = np.linspace(0, duration, int(sample_rate * duration))
            noise = np.random.uniform(-1, 1, len(t))
            # 高通滤波（简化版）
            wave = np.diff(noise, prepend=noise[0]) * 0.5 + noise * 0.5
            envelope = np.exp(-t * 30)
            wave = wave * envelope
        else:
            return None
        
        # 归一化
        wave = wave / np.max(np.abs(wave)) * 0.7
        wave_int = (wave * 32767).astype(np.int16)
        stereo = np.column_stack((wave_int, wave_int))
        
        try:
            return pygame.mixer.Sound(buffer=stereo.tobytes())
        except:
            return None
    
    def _pregenerate_bass(self):
        """预生成低音音色"""
        if not self.audio_initialized:
            return
        
        try:
            # 生成 C1 到 C3 的低音
            for note in range(24, 49):
                freq = self._note_to_freq(note)
                sound = self._generate_bass_tone(freq)
                if sound:
                    self.note_cache[f'bass_{note}'] = sound
            logger.debug("低音音色预生成完成")
        except Exception as e:
            logger.warning(f"低音生成失败: {e}")
    
    def _generate_bass_tone(self, freq: float):
        """生成低音音色"""
        sample_rate = 44100
        duration = 0.5
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 基础正弦波 + 少量谐波
        wave = np.sin(2 * np.pi * freq * t) * 0.8
        wave += np.sin(2 * np.pi * freq * 2 * t) * 0.15
        wave += np.sin(2 * np.pi * freq * 3 * t) * 0.05
        
        # ADSR 包络
        attack = int(0.01 * sample_rate)
        decay = int(0.05 * sample_rate)
        release = int(0.1 * sample_rate)
        
        envelope = np.ones(len(t))
        envelope[:attack] = np.linspace(0, 1, attack)
        envelope[attack:attack+decay] = np.linspace(1, 0.7, decay)
        envelope[-release:] = np.linspace(0.7, 0, release)
        
        wave = wave * envelope
        wave = wave / np.max(np.abs(wave)) * 0.6
        wave_int = (wave * 32767).astype(np.int16)
        stereo = np.column_stack((wave_int, wave_int))
        
        try:
            return pygame.mixer.Sound(buffer=stereo.tobytes())
        except:
            return None
    
    def _pregenerate_metronome(self):
        """预生成节拍器音色"""
        if not self.audio_initialized:
            return
        
        try:
            # 强拍（高音）
            tick_high = self._generate_metronome_tick(1200, 0.05)
            if tick_high:
                self.note_cache['metronome_high'] = tick_high
            
            # 弱拍（低音）
            tick_low = self._generate_metronome_tick(800, 0.04)
            if tick_low:
                self.note_cache['metronome_low'] = tick_low
            
            logger.debug("节拍器音色预生成完成")
        except Exception as e:
            logger.warning(f"节拍器生成失败: {e}")
    
    def _generate_metronome_tick(self, freq: float, duration: float):
        """生成节拍器滴答声"""
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 正弦波 + 快速衰减
        wave = np.sin(2 * np.pi * freq * t)
        envelope = np.exp(-t * 50)  # 快速衰减
        wave = wave * envelope
        
        wave = wave / np.max(np.abs(wave)) * 0.8
        wave_int = (wave * 32767).astype(np.int16)
        stereo = np.column_stack((wave_int, wave_int))
        
        try:
            return pygame.mixer.Sound(buffer=stereo.tobytes())
        except:
            return None
    
    # 音乐性增强控制
    
    def set_metronome_enabled(self, enabled: bool):
        """开关节拍器"""
        self.metronome_enabled = enabled
        self.metronome_beat_index = 0
        self.last_metronome_time = 0
    
    def set_metronome_volume(self, volume: float):
        """设置节拍器音量 (0.0-1.0)"""
        self.metronome_volume = max(0.0, min(1.0, volume))
    
    def set_accompaniment_level(self, level: str):
        """
        设置伴奏强度
        level: 'off', 'low', 'high'
        """
        self.accompaniment_level = level
        if level == 'off':
            self.drum_enabled = False
            self.bass_enabled = False
            self.chord_enabled = False
        elif level == 'low':
            self.drum_enabled = True
            self.bass_enabled = False
            self.chord_enabled = False
        elif level == 'high':
            self.drum_enabled = True
            self.bass_enabled = True
            self.chord_enabled = False
    
    def play_metronome_tick(self, bpm: int = 120, beats_per_bar: int = 4):
        """播放节拍器（按 BPM）"""
        if not self.metronome_enabled or not self.audio_initialized:
            return False
        
        current_time = time.time()
        beat_interval = 60.0 / bpm
        
        if current_time - self.last_metronome_time < beat_interval * 0.9:
            return False
        
        # 强拍（第一拍）或弱拍
        is_downbeat = self.metronome_beat_index % beats_per_bar == 0
        tick_key = 'metronome_high' if is_downbeat else 'metronome_low'
        
        tick = self.note_cache.get(tick_key)
        if tick:
            tick.set_volume(self.metronome_volume)
            tick.play()
        
        self.metronome_beat_index += 1
        self.last_metronome_time = current_time
        return True
    
    def set_drum_enabled(self, enabled: bool):
        """开关鼓点"""
        self.drum_enabled = enabled
        self.drum_beat_index = 0
    
    def set_bass_enabled(self, enabled: bool):
        """开关低音"""
        self.bass_enabled = enabled
    
    def set_chord_enabled(self, enabled: bool):
        """开关和弦"""
        self.chord_enabled = enabled
    
    def play_drum_beat(self, bpm: int = 120):
        """播放鼓点（根据 BPM 自动节拍）"""
        if not self.drum_enabled or not self.audio_initialized:
            return
        
        current_time = time.time()
        beat_interval = 60.0 / bpm / 2  # 八分音符间隔
        
        if current_time - self.last_drum_time < beat_interval:
            return
        
        pattern = self.drum_patterns.get(self.current_drum_pattern, [1, 0, 0, 0])
        
        if pattern[self.drum_beat_index % len(pattern)]:
            # 底鼓
            kick = self.note_cache.get('drum_kick')
            if kick:
                kick.set_volume(0.6)
                kick.play()
        
        # 踩镲（每拍）
        if self.drum_beat_index % 2 == 0:
            hihat = self.note_cache.get('drum_hihat')
            if hihat:
                hihat.set_volume(0.3)
                hihat.play()
        
        self.drum_beat_index += 1
        self.last_drum_time = current_time
    
    def play_bass_note(self, root_note: int = None):
        """播放低音（跟随根音）"""
        if not self.bass_enabled or not self.audio_initialized:
            return
        
        current_time = time.time()
        if current_time - self.last_bass_time < self.bass_interval:
            return
        
        # 使用当前音阶的根音
        if root_note is None:
            root_note = self.root_note
        
        # 低两个八度
        bass_note = (root_note % 12) + 24
        
        sound = self.note_cache.get(f'bass_{bass_note}')
        if sound:
            sound.set_volume(0.5)
            sound.play()
        
        self.last_bass_time = current_time
    
    def play_chord(self, root_note: int, velocity: int = 80):
        """播放和弦（根音 + 三度 + 五度）"""
        if not self.chord_enabled or not self.audio_initialized:
            return
        
        # 简单大三和弦
        chord_notes = [root_note, root_note + 4, root_note + 7]
        
        for note in chord_notes:
            cache_key = f"{self.current_instrument}_{note}"
            sound = self.note_cache.get(cache_key)
            if sound:
                sound.set_volume(velocity / 127.0 * 0.5)  # 和弦音量减半
                sound.play()
    
    def _note_to_freq(self, note: int) -> float:
        """将MIDI音符转换为频率（Hz）"""
        # A4 (MIDI 69) = 440 Hz
        return 440.0 * (2.0 ** ((note - 69) / 12.0))
    
    def _generate_tone(self, freq: float, duration: float, wave_type: str = 'sine') -> 'pygame.mixer.Sound':
        """
        生成指定波形的音调
        
        Args:
            freq: 频率（Hz）
            duration: 持续时间（秒）
            wave_type: 波形类型 (sine, triangle, square, sawtooth, noise)
        """
        if not self.audio_initialized:
            return None
        
        sample_rate = 44100
        n_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, n_samples, False)
        
        # 生成波形
        if wave_type == 'sine':
            wave = np.sin(2 * np.pi * freq * t)
        elif wave_type == 'triangle':
            wave = 2 * np.abs(2 * (t * freq - np.floor(t * freq + 0.5))) - 1
        elif wave_type == 'square':
            wave = np.sign(np.sin(2 * np.pi * freq * t))
        elif wave_type == 'sawtooth':
            wave = 2 * (t * freq - np.floor(t * freq + 0.5))
        elif wave_type == 'noise':
            # 带音高的噪声（用于鼓）
            wave = np.random.uniform(-1, 1, n_samples)
            # 添加一点音高
            wave = wave * 0.5 + 0.5 * np.sin(2 * np.pi * freq * 0.5 * t)
        else:
            wave = np.sin(2 * np.pi * freq * t)
        
        # ADSR包络
        attack = int(0.01 * sample_rate)
        decay = int(0.05 * sample_rate)
        sustain_level = 0.7
        release = int(0.1 * sample_rate)
        
        envelope = np.ones(n_samples)
        
        # Attack
        if attack > 0:
            envelope[:attack] = np.linspace(0, 1, attack)
        
        # Decay
        if decay > 0 and attack + decay < n_samples:
            envelope[attack:attack+decay] = np.linspace(1, sustain_level, decay)
        
        # Sustain（保持）
        sustain_start = attack + decay
        sustain_end = n_samples - release
        if sustain_end > sustain_start:
            envelope[sustain_start:sustain_end] = sustain_level
        
        # Release
        if release > 0:
            envelope[-release:] = np.linspace(sustain_level, 0, release)
        
        # 应用包络
        wave = wave * envelope
        
        # 归一化
        wave = wave / np.max(np.abs(wave)) * 0.8
        
        # 转换为16位整数
        wave_int = (wave * 32767).astype(np.int16)
        
        # 立体声
        stereo = np.column_stack((wave_int, wave_int))
        
        try:
            sound = pygame.mixer.Sound(buffer=stereo.tobytes())
            return sound
        except Exception as e:
            logger.error(f"生成音调失败: {e}")
            return None
    
    def play_note(self, x: int, y: int, thickness: int, width: int = 1280, height: int = 720):
        """
        根据坐标和粗细播放音符
        
        Args:
            x: X坐标（控制音高）
            y: Y坐标（控制时值/节奏）
            thickness: 画笔粗细（控制音量）
            width: 画面宽度
            height: 画面高度
        """
        if not self.is_playing or not self.audio_initialized:
            return
        
        current_time = time.time()
        
        # 防止重复播放（太频繁）
        if current_time - self.last_note_time < self.min_note_interval:
            return
        
        # 映射坐标到音乐参数
        raw_note = map_x_to_note(x, width)
        note = quantize_to_scale(raw_note, self.scale_type, self.root_note)
        
        # 如果音符没变化，不重复播放
        if note == self.last_note and current_time - self.last_note_time < 0.2:
            return
        
        duration = map_y_to_duration(y, height)
        velocity = map_thickness_to_volume(thickness)
        
        # 获取缓存的音符
        cache_key = f"{self.current_instrument}_{note}"
        sound = self.note_cache.get(cache_key)
        
        if sound:
            # 设置音量
            volume = velocity / 127.0
            sound.set_volume(volume)
            
            # 播放
            sound.play()
            
            # 更新状态
            self.last_note = note
            self.last_note_time = current_time
            
            # 添加到活跃音符列表
            self.active_notes.append({
                'note': note,
                'velocity': velocity,
                'time': current_time,
                'x': x,
                'y': y
            })
            
            # 更新音波数据
            self._update_waveform(note, velocity)
            
            # 录制
            if self.is_recording:
                event = NoteEvent(
                    note=note,
                    velocity=velocity,
                    duration=duration,
                    instrument=self.current_instrument,
                    timestamp=current_time - self.recording_start_time,
                    x=x,
                    y=y
                )
                self.recorded_notes.append(event)
    
    def play_preview_note(self, x: int, y: int, thickness: int, width: int = 640, height: int = 480) -> bool:
        """
        播放 Preview 音（带时间+距离阈值控制）
        
        Returns:
            是否成功触发音符
        """
        if not self.is_playing or not self.audio_initialized:
            return False
        
        current_time = time.time()
        
        # 计算距离
        dx = x - self.last_preview_x
        dy = y - self.last_preview_y
        distance = (dx * dx + dy * dy) ** 0.5
        
        # 计算时间间隔
        time_elapsed = current_time - self.last_preview_time
        
        # 触发条件：时间足够长 OR 移动距离足够远
        should_trigger = (time_elapsed >= self.preview_min_interval) or \
                        (distance >= self.preview_min_distance and time_elapsed >= 0.02)
        
        if not should_trigger:
            return False
        
        # 映射坐标到音乐参数
        raw_note = map_x_to_note(x, width)
        note = quantize_to_scale(raw_note, self.scale_type, self.root_note)
        
        # 如果音符相同且时间太短，跳过
        if note == self.last_note and time_elapsed < 0.15:
            return False
        
        velocity = map_thickness_to_volume(thickness)
        
        # 获取缓存的音符
        cache_key = f"{self.current_instrument}_{note}"
        sound = self.note_cache.get(cache_key)
        
        if sound:
            volume = velocity / 127.0
            sound.set_volume(volume)
            sound.play()
            
            # 更新状态
            self.last_note = note
            self.last_note_time = current_time
            self.last_preview_x = x
            self.last_preview_y = y
            self.last_preview_time = current_time
            
            # 重要修复：如果正在录制，保存到 recorded_notes
            if self.is_recording:
                duration = map_y_to_duration(y, height)
                event = NoteEvent(
                    note=note,
                    velocity=velocity,
                    duration=duration,
                    instrument=self.current_instrument,
                    timestamp=current_time - self.recording_start_time,
                    x=x,
                    y=y
                )
                self.recorded_notes.append(event)
                logger.debug(f"录制预览音符: {note}, 时间: {event.timestamp:.3f}s")
            
            # 更新音波数据
            self._update_waveform(note, velocity)
            
            return True
        
        return False
    
    def reset_preview_state(self):
        """重置 Preview 状态（开始新笔画时调用）"""
        self.last_preview_x = 0
        self.last_preview_y = 0
        self.last_preview_time = 0
        self.last_note = -1
    
    def _update_waveform(self, note: int, velocity: int):
        """更新音波可视化数据"""
        with self.waveform_lock:
            # 基于音符和音量生成音波数据
            freq_factor = (note - MIN_NOTE) / (MAX_NOTE - MIN_NOTE)
            amp_factor = velocity / 127.0
            
            # 生成新的波形数据
            x = np.linspace(0, 4 * np.pi, WAVEFORM_SEGMENTS)
            new_wave = np.sin(x * (1 + freq_factor * 3)) * amp_factor
            
            # 混合到当前波形
            self.waveform_data = self.waveform_data * 0.7 + new_wave * 0.3
    
    def get_waveform_data(self):
        """获取当前音波数据"""
        with self.waveform_lock:
            return self.waveform_data.copy()
    
    def decay_waveform(self, factor: float = 0.95):
        """衰减音波数据"""
        with self.waveform_lock:
            self.waveform_data *= factor
    
    def switch_instrument(self, direction: int = 1):
        """
        切换乐器
        
        Args:
            direction: 1=下一个, -1=上一个
            
        Returns:
            新乐器名称
        """
        self.instrument_index = (self.instrument_index + direction) % len(INSTRUMENT_LIST)
        self.current_instrument = INSTRUMENT_LIST[self.instrument_index]
        return self.get_instrument_info()
    
    def set_instrument(self, instrument_key: str):
        """设置指定乐器"""
        if instrument_key in INSTRUMENT_LIST:
            self.instrument_index = INSTRUMENT_LIST.index(instrument_key)
            self.current_instrument = instrument_key
    
    def get_instrument_info(self):
        """获取当前乐器信息"""
        instrument = INSTRUMENTS[self.current_instrument]
        return {
            'key': self.current_instrument,
            'name': instrument['name'],
            'name_en': instrument['name_en'],
            'color': instrument['color']
        }
    
    def toggle_play(self):
        """切换播放/停止状态"""
        self.is_playing = not self.is_playing
        return self.is_playing
    
    def start_recording(self):
        """开始录制"""
        self.recorded_notes = []
        self.recording_start_time = time.time()
        self.is_recording = True
        logger.info("开始录制...")
    
    def stop_recording(self):
        """停止录制"""
        self.is_recording = False
        duration = time.time() - self.recording_start_time
        logger.info(f"录制完成，共 {len(self.recorded_notes)} 个音符，时长 {duration:.1f} 秒")
        return self.recorded_notes
    
    def toggle_recording(self):
        """切换录制状态"""
        if self.is_recording:
            return self.stop_recording(), False
        else:
            self.start_recording()
            return None, True
    
    def save_recording(self, filename: str = None):
        """
        保存录制的音符序列
        
        Args:
            filename: 文件名（可选）
            
        Returns:
            保存的文件路径
        """
        if not self.recorded_notes:
            logger.warning("没有可保存的录制数据")
            return None
        
        os.makedirs(RECORDING_FOLDER, exist_ok=True)
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"music_{timestamp}.txt"
        
        filepath = os.path.join(RECORDING_FOLDER, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("# Gesture Music Paint Recording\n")
                f.write(f"# Notes: {len(self.recorded_notes)}\n")
                f.write(f"# Scale: {self.scale_type}\n")
                f.write("# Format: timestamp,note,velocity,duration,instrument,x,y\n")
                f.write("#" + "=" * 50 + "\n")
                
                for event in self.recorded_notes:
                    line = f"{event.timestamp:.3f},{event.note},{event.velocity},"
                    line += f"{event.duration},{event.instrument},{event.x},{event.y}\n"
                    f.write(line)
            
            logger.info(f"录制已保存: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"保存失败: {e}")
            return None
    
    def playback_recording(self, notes: list = None):
        """
        回放录制的音符
        
        Args:
            notes: 音符列表（可选，默认使用当前录制）
        """
        if notes is None:
            notes = self.recorded_notes
        
        if not notes:
            logger.warning("没有可回放的数据")
            return
        
        def _playback_thread():
            start_time = time.time()
            note_index = 0
            
            while note_index < len(notes) and self.is_playing:
                current_time = time.time() - start_time
                event = notes[note_index]
                
                if current_time >= event.timestamp:
                    # 播放音符
                    cache_key = f"{event.instrument}_{event.note}"
                    sound = self.note_cache.get(cache_key)
                    if sound:
                        volume = event.velocity / 127.0
                        sound.set_volume(volume)
                        sound.play()
                    
                    note_index += 1
                else:
                    time.sleep(0.01)
            
            logger.info("回放完成")
        
        thread = threading.Thread(target=_playback_thread, daemon=True)
        thread.start()
    
    def get_note_name(self, note: int) -> str:
        """获取音符名称"""
        octave = note // 12 - 1
        name = self.NOTE_NAMES[note % 12]
        return f"{name}{octave}"
    
    def set_scale(self, scale_type: str):
        """设置音阶"""
        if scale_type in SCALE_TYPES:
            self.scale_type = scale_type
    
    def export_audio(self, filename: str = None, notes: list = None) -> str:
        """
        将录制的音符序列导出为 WAV 音频文件
        
        Args:
            filename: 输出文件名（可选）
            notes: 音符列表（可选，默认使用当前录制）
            
        Returns:
            保存的文件路径
        """
        if notes is None:
            notes = self.recorded_notes
        
        if not notes:
            logger.warning("没有可导出的音符数据")
            return None
        
        os.makedirs(RECORDING_FOLDER, exist_ok=True)
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"music_{timestamp}.wav"
        
        # 确保文件扩展名为 .wav
        if not filename.lower().endswith('.wav'):
            filename = filename.rsplit('.', 1)[0] + '.wav'
        
        filepath = os.path.join(RECORDING_FOLDER, filename)
        
        try:
            # 音频参数
            sample_rate = 44100
            channels = 2
            
            # 计算总时长（最后一个音符的时间戳 + 其持续时间 + 缓冲）
            if notes:
                last_note = notes[-1]
                total_duration = last_note.timestamp + (last_note.duration / 1000.0) + 0.5
            else:
                total_duration = 1.0
            
            total_samples = int(sample_rate * total_duration)
            
            # 创建音频缓冲区（立体声）
            audio_buffer = np.zeros((total_samples, channels), dtype=np.float32)
            
            logger.info(f"正在渲染音频... 时长: {total_duration:.2f}秒, 音符数: {len(notes)}")
            
            # 渲染每个音符
            for event in notes:
                note_audio = self._render_note_to_audio(
                    note=event.note,
                    velocity=event.velocity,
                    duration=event.duration / 1000.0,  # 转换为秒
                    instrument=event.instrument,
                    sample_rate=sample_rate
                )
                
                # 计算起始采样点
                start_sample = int(event.timestamp * sample_rate)
                end_sample = start_sample + len(note_audio)
                
                # 确保不越界
                if end_sample > total_samples:
                    end_sample = total_samples
                    note_audio = note_audio[:end_sample - start_sample]
                
                # 混合到缓冲区
                if start_sample < total_samples and len(note_audio) > 0:
                    audio_buffer[start_sample:start_sample + len(note_audio)] += note_audio
            
            # 归一化，防止削波
            max_val = np.max(np.abs(audio_buffer))
            if max_val > 0:
                audio_buffer = audio_buffer / max_val * 0.9
            
            # 转换为 16 位整数
            audio_int16 = (audio_buffer * 32767).astype(np.int16)
            
            # 写入 WAV 文件
            with wave.open(filepath, 'w') as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_int16.tobytes())
            
            logger.info(f"音频已导出: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"音频导出失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _render_note_to_audio(self, note: int, velocity: int, duration: float, 
                               instrument: str, sample_rate: int = 44100) -> np.ndarray:
        """
        将单个音符渲染为音频数据
        
        Args:
            note: MIDI音符号
            velocity: 音量 (0-127)
            duration: 持续时间（秒）
            instrument: 乐器键名
            sample_rate: 采样率
            
        Returns:
            立体声音频数组 (samples, 2)
        """
        # 获取乐器波形类型
        wave_type = INSTRUMENTS.get(instrument, INSTRUMENTS['piano'])['wave_type']
        
        # 计算频率
        freq = self._note_to_freq(note)
        
        # 生成采样点
        n_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, n_samples, False)
        
        # 生成波形
        if wave_type == 'sine':
            wave = np.sin(2 * np.pi * freq * t)
        elif wave_type == 'triangle':
            wave = 2 * np.abs(2 * (t * freq - np.floor(t * freq + 0.5))) - 1
        elif wave_type == 'square':
            wave = np.sign(np.sin(2 * np.pi * freq * t))
        elif wave_type == 'sawtooth':
            wave = 2 * (t * freq - np.floor(t * freq + 0.5))
        elif wave_type == 'noise':
            wave = np.random.uniform(-1, 1, n_samples)
            wave = wave * 0.5 + 0.5 * np.sin(2 * np.pi * freq * 0.5 * t)
        else:
            wave = np.sin(2 * np.pi * freq * t)
        
        # ADSR 包络
        attack = int(0.02 * sample_rate)
        decay = int(0.05 * sample_rate)
        sustain_level = 0.7
        release = int(0.15 * sample_rate)
        
        envelope = np.ones(n_samples)
        
        if attack > 0 and attack < n_samples:
            envelope[:attack] = np.linspace(0, 1, attack)
        
        if decay > 0 and attack + decay < n_samples:
            envelope[attack:attack+decay] = np.linspace(1, sustain_level, decay)
        
        sustain_start = attack + decay
        sustain_end = n_samples - release
        if sustain_end > sustain_start:
            envelope[sustain_start:sustain_end] = sustain_level
        
        if release > 0 and release < n_samples:
            envelope[-release:] = np.linspace(sustain_level, 0, release)
        
        # 应用包络和音量
        volume = velocity / 127.0
        wave = wave * envelope * volume
        
        # 转换为立体声
        stereo = np.column_stack((wave, wave)).astype(np.float32)
        
        return stereo
    
    def cleanup(self):
        """清理资源"""
        if self.audio_initialized:
            pygame.mixer.quit()
