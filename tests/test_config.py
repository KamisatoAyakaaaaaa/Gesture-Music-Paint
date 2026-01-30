# -*- coding: utf-8 -*-
"""
config.py 单元测试 - 测试辅助函数
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from config import (
    map_x_to_note,
    map_y_to_duration,
    map_thickness_to_volume,
    quantize_to_scale,
    MIN_NOTE,
    MAX_NOTE,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
)


class TestMapXToNote:
    """X 坐标到音符映射测试"""
    
    def test_left_edge(self):
        """左边缘应为最低音"""
        note = map_x_to_note(0, CAMERA_WIDTH)
        assert note == MIN_NOTE
    
    def test_right_edge(self):
        """右边缘应为最高音"""
        note = map_x_to_note(CAMERA_WIDTH - 1, CAMERA_WIDTH)
        assert note <= MAX_NOTE
    
    def test_middle(self):
        """中间应为中间音"""
        note = map_x_to_note(CAMERA_WIDTH // 2, CAMERA_WIDTH)
        mid_note = (MIN_NOTE + MAX_NOTE) // 2
        assert abs(note - mid_note) <= 2
    
    def test_out_of_bounds(self):
        """超出范围应被限制"""
        note = map_x_to_note(-100, CAMERA_WIDTH)
        assert note == MIN_NOTE
        
        note = map_x_to_note(CAMERA_WIDTH + 100, CAMERA_WIDTH)
        assert note <= MAX_NOTE


class TestMapYToDuration:
    """Y 坐标到时值映射测试"""
    
    def test_top_is_short(self):
        """顶部应为短音符"""
        from config import MIN_NOTE_DURATION, HEADER_HEIGHT
        duration = map_y_to_duration(HEADER_HEIGHT, CAMERA_HEIGHT)
        assert duration == MIN_NOTE_DURATION
    
    def test_bottom_is_long(self):
        """底部应为长音符"""
        from config import MAX_NOTE_DURATION
        duration = map_y_to_duration(CAMERA_HEIGHT - 1, CAMERA_HEIGHT)
        # 应该接近最大时值
        assert duration >= MAX_NOTE_DURATION * 0.9


class TestMapThicknessToVolume:
    """粗细到音量映射测试"""
    
    def test_thin_is_quiet(self):
        """细线应为低音量"""
        from config import MIN_BRUSH_THICKNESS, MIN_VOLUME
        volume = map_thickness_to_volume(MIN_BRUSH_THICKNESS)
        assert volume == MIN_VOLUME
    
    def test_thick_is_loud(self):
        """粗线应为高音量"""
        from config import MAX_BRUSH_THICKNESS, MAX_VOLUME
        volume = map_thickness_to_volume(MAX_BRUSH_THICKNESS)
        assert volume == MAX_VOLUME
    
    def test_clamping(self):
        """超出范围应被限制"""
        from config import MIN_VOLUME, MAX_VOLUME
        volume = map_thickness_to_volume(0)
        assert volume == MIN_VOLUME
        
        volume = map_thickness_to_volume(100)
        assert volume == MAX_VOLUME


class TestQuantizeToScale:
    """音阶量化测试"""
    
    def test_major_scale(self):
        """大调音阶量化"""
        # C4 (60) 在大调中应保持不变
        note = quantize_to_scale(60, 'major', 60)
        assert note == 60
        
        # C#4 (61) 应量化到 C4 (60) 或 D4 (62)
        note = quantize_to_scale(61, 'major', 60)
        assert note in [60, 62]
    
    def test_pentatonic_scale(self):
        """五声音阶量化"""
        # 五声音阶: C, D, E, G, A (0, 2, 4, 7, 9)
        # F (65) 应量化到 E (64) 或 G (67)
        note = quantize_to_scale(65, 'pentatonic', 60)
        assert note in [64, 67]
    
    def test_octave_handling(self):
        """跨八度量化"""
        # 高八度的 C (72) 应量化到 72
        note = quantize_to_scale(72, 'major', 60)
        assert note == 72


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
