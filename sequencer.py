# -*- coding: utf-8 -*-
"""
音序器模块 - Master 回放控制
"""

import threading
import time
from typing import List, Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum

from project_model import Project, Stroke, Point, quantize_time, time_to_beat
from config import (
    MIN_NOTE, MAX_NOTE, MIN_VOLUME, MAX_VOLUME,
    map_x_to_note, map_thickness_to_volume, quantize_to_scale
)


class PlaybackMode(Enum):
    """回放模式"""
    SCAN = "scan"           # 扫描回放（从左到右）
    TIMELINE = "timeline"   # 时间轴回放（按录制顺序）


@dataclass
class SequenceEvent:
    """音序事件"""
    time: float             # 触发时间（秒）
    note: int               # MIDI 音符
    velocity: int           # 音量
    duration: float         # 持续时间
    instrument: str         # 乐器
    x: int = 0              # 原始 X 坐标（用于可视化）
    y: int = 0              # 原始 Y 坐标


class Sequencer:
    """
    音序器 - 负责 Master 回放
    
    支持两种回放模式：
    1. 扫描回放：扫描线从左到右，与笔画相交时触发音符
    2. 时间轴回放：按录制时间顺序播放量化后的音符
    """
    
    def __init__(self, music_engine=None):
        self.music_engine = music_engine
        self.project: Project = None
        
        # 回放状态
        self.is_playing = False
        self.is_paused = False
        self.current_time = 0.0
        self.playback_speed = 1.0
        
        # 回放参数
        self.bpm = 120
        self.quantize = "1/8"
        self.mode = PlaybackMode.SCAN
        
        # 扫描回放参数
        self.scan_duration = 4.0    # 扫描一次的时长（秒）
        self.scan_position = 0      # 当前扫描位置（X 坐标）
        self.scan_width = 640       # 画布宽度
        
        # 事件队列
        self.events: List[SequenceEvent] = []
        self.event_index = 0
        
        # 回放线程
        self._playback_thread: threading.Thread = None
        self._stop_event = threading.Event()
        
        # 回调函数
        self.on_note_play: Callable[[SequenceEvent], None] = None
        self.on_scan_position: Callable[[int], None] = None
        self.on_playback_end: Callable[[], None] = None
    
    def set_project(self, project: Project):
        """设置要回放的项目"""
        self.project = project
        self.scan_width = project.width if project else 640
        self.bpm = project.bpm if project else 120
    
    def set_music_engine(self, engine):
        """设置音乐引擎"""
        self.music_engine = engine
    
    def generate_scan_events(self) -> List[SequenceEvent]:
        """
        生成扫描回放的事件列表
        
        扫描线从 X=0 扫到 X=width，当与笔画点相交时触发音符
        """
        if not self.project or not self.project.strokes:
            return []
        
        events = []
        beat_duration = 60.0 / self.bpm
        
        # 收集所有点并按 X 坐标排序
        all_points = []
        for stroke in self.project.strokes:
            for point in stroke.points:
                all_points.append({
                    'x': point.x,
                    'y': point.y,
                    'thickness': point.thickness,
                    'instrument': stroke.instrument
                })
        
        # 按 X 坐标排序
        all_points.sort(key=lambda p: p['x'])
        
        # 生成事件
        last_note = -1
        last_x = -1
        min_x_gap = self.scan_width // 32  # 最小 X 间隔
        
        for p in all_points:
            # 跳过太近的点
            if last_x >= 0 and abs(p['x'] - last_x) < min_x_gap:
                continue
            
            # 计算触发时间（X 坐标映射到时间）
            t = (p['x'] / self.scan_width) * self.scan_duration
            
            # 量化时间到节拍网格
            t = quantize_time(t, self.bpm, self.quantize)
            
            # 计算音符
            note = map_x_to_note(p['x'], self.scan_width)
            note = quantize_to_scale(note, self.project.scale, self.project.root_note)
            
            # 跳过重复音符
            if note == last_note and len(events) > 0 and abs(t - events[-1].time) < 0.1:
                continue
            
            velocity = map_thickness_to_volume(p['thickness'])
            
            events.append(SequenceEvent(
                time=t,
                note=note,
                velocity=velocity,
                duration=beat_duration / 2,
                instrument=p['instrument'],
                x=p['x'],
                y=p['y']
            ))
            
            last_note = note
            last_x = p['x']
        
        return events
    
    def generate_timeline_events(self) -> List[SequenceEvent]:
        """
        生成时间轴回放的事件列表
        
        按录制时间顺序，量化到节拍网格
        """
        if not self.project or not self.project.strokes:
            return []
        
        events = []
        beat_duration = 60.0 / self.bpm
        
        for stroke in self.project.strokes:
            # 采样笔画点（不是每个点都生成事件）
            sample_interval = max(1, len(stroke.points) // 8)
            
            for i, point in enumerate(stroke.points):
                if i % sample_interval != 0:
                    continue
                
                # 量化时间
                t = quantize_time(point.t, self.bpm, self.quantize)
                
                # 计算音符
                note = map_x_to_note(point.x, self.project.width)
                note = quantize_to_scale(note, self.project.scale, self.project.root_note)
                
                velocity = map_thickness_to_volume(point.thickness)
                
                events.append(SequenceEvent(
                    time=t,
                    note=note,
                    velocity=velocity,
                    duration=beat_duration / 2,
                    instrument=stroke.instrument,
                    x=point.x,
                    y=point.y
                ))
        
        # 按时间排序
        events.sort(key=lambda e: e.time)
        return events
    
    def prepare_playback(self, mode: PlaybackMode = None):
        """准备回放"""
        if mode:
            self.mode = mode
        
        if self.mode == PlaybackMode.SCAN:
            self.events = self.generate_scan_events()
        else:
            self.events = self.generate_timeline_events()
        
        self.event_index = 0
        self.current_time = 0.0
        self.scan_position = 0
    
    def start(self):
        """开始回放"""
        if self.is_playing:
            return
        
        self.prepare_playback()
        self.is_playing = True
        self.is_paused = False
        self._stop_event.clear()
        
        self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._playback_thread.start()
    
    def pause(self):
        """暂停回放"""
        self.is_paused = not self.is_paused
    
    def stop(self):
        """停止回放"""
        self.is_playing = False
        self.is_paused = False
        self._stop_event.set()
        
        if self._playback_thread:
            self._playback_thread.join(timeout=1.0)
        
        self.current_time = 0.0
        self.event_index = 0
        self.scan_position = 0
    
    def _playback_loop(self):
        """回放循环"""
        start_time = time.time()
        
        while self.is_playing and not self._stop_event.is_set():
            if self.is_paused:
                time.sleep(0.05)
                start_time = time.time() - self.current_time
                continue
            
            # 更新当前时间
            self.current_time = (time.time() - start_time) * self.playback_speed
            
            # 更新扫描位置
            if self.mode == PlaybackMode.SCAN:
                self.scan_position = int((self.current_time / self.scan_duration) * self.scan_width)
                self.scan_position = min(self.scan_position, self.scan_width)
                
                if self.on_scan_position:
                    self.on_scan_position(self.scan_position)
            
            # 触发到期的事件
            while self.event_index < len(self.events):
                event = self.events[self.event_index]
                
                if event.time <= self.current_time:
                    self._trigger_event(event)
                    self.event_index += 1
                else:
                    break
            
            # 检查是否结束
            max_time = self.scan_duration if self.mode == PlaybackMode.SCAN else \
                       (self.events[-1].time + 1.0 if self.events else 0)
            
            if self.current_time >= max_time:
                self.is_playing = False
                if self.on_playback_end:
                    self.on_playback_end()
                break
            
            time.sleep(0.01)  # 10ms 精度
    
    def _trigger_event(self, event: SequenceEvent):
        """触发音符事件"""
        if self.music_engine:
            # 切换乐器
            if event.instrument != self.music_engine.current_instrument:
                self.music_engine.set_instrument(event.instrument)
            
            # 播放音符
            cache_key = f"{event.instrument}_{event.note}"
            sound = self.music_engine.note_cache.get(cache_key)
            
            if sound:
                volume = event.velocity / 127.0
                sound.set_volume(volume)
                sound.play()
                
                # 更新音波数据
                self.music_engine._update_waveform(event.note, event.velocity)
        
        # 回调
        if self.on_note_play:
            self.on_note_play(event)
    
    def get_playback_info(self) -> Dict[str, Any]:
        """获取回放状态信息"""
        return {
            'is_playing': self.is_playing,
            'is_paused': self.is_paused,
            'current_time': self.current_time,
            'scan_position': self.scan_position,
            'mode': self.mode.value,
            'bpm': self.bpm,
            'total_events': len(self.events),
            'current_event': self.event_index
        }
