# -*- coding: utf-8 -*-
"""
project_model.py 单元测试
"""

import json
import tempfile
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from project_model import Point, Stroke, Project, quantize_time, time_to_beat, beat_to_time


class TestPoint:
    """Point 数据类测试"""
    
    def test_point_creation(self):
        """测试 Point 创建"""
        p = Point(x=100, y=200, t=1.5, thickness=10)
        assert p.x == 100
        assert p.y == 200
        assert p.t == 1.5
        assert p.thickness == 10
    
    def test_point_to_dict(self):
        """测试 Point 序列化"""
        p = Point(x=100, y=200, t=1.5, thickness=10)
        d = p.to_dict()
        assert d == {'x': 100, 'y': 200, 't': 1.5, 'thickness': 10}
    
    def test_point_from_dict(self):
        """测试 Point 反序列化"""
        d = {'x': 100, 'y': 200, 't': 1.5, 'thickness': 10}
        p = Point.from_dict(d)
        assert p.x == 100
        assert p.y == 200


class TestStroke:
    """Stroke 数据类测试"""
    
    def test_stroke_creation(self):
        """测试 Stroke 创建"""
        s = Stroke(instrument='piano', color=(255, 200, 100))
        assert s.instrument == 'piano'
        assert s.color == (255, 200, 100)
        assert len(s.points) == 0
    
    def test_stroke_add_point(self):
        """测试添加点"""
        s = Stroke(instrument='piano', color=(255, 200, 100))
        s.add_point(100, 200, 10, 0.5)
        s.add_point(150, 220, 12, 1.0)
        
        assert len(s.points) == 2
        assert s.points[0].x == 100
        assert s.points[1].x == 150
    
    def test_stroke_serialization(self):
        """测试 Stroke 序列化/反序列化"""
        s = Stroke(instrument='guitar', color=(100, 200, 255), start_t=0.0)
        s.add_point(100, 200, 10, 0.5)
        s.add_point(150, 220, 12, 1.0)
        
        d = s.to_dict()
        s2 = Stroke.from_dict(d)
        
        assert s2.instrument == 'guitar'
        assert len(s2.points) == 2


class TestProject:
    """Project 数据类测试"""
    
    def test_project_creation(self):
        """测试 Project 创建"""
        p = Project(name="测试项目", bpm=100)
        assert p.name == "测试项目"
        assert p.bpm == 100
        assert len(p.strokes) == 0
    
    def test_project_add_stroke(self):
        """测试添加 Stroke"""
        p = Project()
        s = Stroke(instrument='piano', color=(255, 200, 100))
        s.add_point(100, 200, 10, 0.5)
        
        p.add_stroke(s)
        assert len(p.strokes) == 1
    
    def test_project_json_roundtrip(self):
        """测试 Project JSON 序列化/反序列化"""
        p = Project(name="测试", bpm=120)
        s = Stroke(instrument='piano', color=(255, 200, 100))
        s.add_point(100, 200, 10, 0.5)
        p.add_stroke(s)
        
        # 序列化
        json_str = p.to_json()
        
        # 反序列化
        p2 = Project.from_json(json_str)
        
        assert p2.name == "测试"
        assert p2.bpm == 120
        assert len(p2.strokes) == 1
    
    def test_project_save_load(self):
        """测试 Project 文件保存/加载"""
        p = Project(name="文件测试", bpm=90)
        s = Stroke(instrument='synth', color=(255, 100, 200))
        s.add_point(50, 100, 8, 0.2)
        p.add_stroke(s)
        
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name
        
        try:
            p.save(filepath)
            
            # 加载
            p2 = Project.load(filepath)
            
            assert p2.name == "文件测试"
            assert p2.bpm == 90
            assert p2.strokes[0].instrument == 'synth'
        finally:
            os.unlink(filepath)


class TestQuantizeFunctions:
    """量化函数测试"""
    
    def test_time_to_beat(self):
        """测试时间到节拍转换"""
        # BPM=120 时，1秒=2拍
        beat = time_to_beat(1.0, 120)
        assert beat == 2.0
        
        # BPM=60 时，1秒=1拍
        beat = time_to_beat(1.0, 60)
        assert beat == 1.0
    
    def test_beat_to_time(self):
        """测试节拍到时间转换"""
        # BPM=120 时，1拍=0.5秒
        t = beat_to_time(1.0, 120)
        assert t == 0.5
    
    def test_quantize_time_eighth(self):
        """测试八分音符量化"""
        # BPM=120, 1/8 = 0.25秒
        t = quantize_time(0.3, 120, "1/8")
        assert t == 0.25 or t == 0.5  # 最近的八分音符位置
    
    def test_quantize_time_quarter(self):
        """测试四分音符量化"""
        # BPM=120, 1/4 = 0.5秒
        t = quantize_time(0.6, 120, "1/4")
        assert t == 0.5 or t == 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
