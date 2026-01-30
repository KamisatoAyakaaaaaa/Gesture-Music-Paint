# -*- coding: utf-8 -*-
"""
项目数据模型 - Point/Stroke/Project 数据结构定义
"""

import json
import time
import logging

logger = logging.getLogger('GesturePaint.Model')
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class Point:
    """绘制点 - 最小数据单元"""
    x: int                      # X 坐标
    y: int                      # Y 坐标
    t: float                    # 相对时间戳（秒，相对于笔画开始）
    thickness: int = 10         # 画笔粗细
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Point':
        return cls(**data)


@dataclass
class Stroke:
    """笔画 - 一次连续绘制"""
    instrument: str             # 乐器标识
    color: tuple                # BGR 颜色
    points: List[Point] = field(default_factory=list)
    start_t: float = 0.0        # 开始时间（相对于项目开始）
    end_t: float = 0.0          # 结束时间
    stroke_id: str = ""         # 唯一标识
    
    def __post_init__(self):
        if not self.stroke_id:
            self.stroke_id = f"stroke_{int(time.time() * 1000)}"
    
    def add_point(self, x: int, y: int, thickness: int, relative_t: float):
        """添加一个点"""
        self.points.append(Point(x=x, y=y, t=relative_t, thickness=thickness))
        if not self.points or len(self.points) == 1:
            self.start_t = relative_t
        self.end_t = relative_t
    
    def get_duration(self) -> float:
        """获取笔画持续时间"""
        return self.end_t - self.start_t
    
    def get_average_x(self) -> float:
        """获取平均 X 坐标（用于音高计算）"""
        if not self.points:
            return 0
        return sum(p.x for p in self.points) / len(self.points)
    
    def get_average_y(self) -> float:
        """获取平均 Y 坐标"""
        if not self.points:
            return 0
        return sum(p.y for p in self.points) / len(self.points)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'instrument': self.instrument,
            'color': list(self.color) if isinstance(self.color, tuple) else self.color,
            'points': [p.to_dict() for p in self.points],
            'start_t': self.start_t,
            'end_t': self.end_t,
            'stroke_id': self.stroke_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Stroke':
        points = [Point.from_dict(p) for p in data.get('points', [])]
        color = tuple(data.get('color', [255, 255, 255]))
        return cls(
            instrument=data.get('instrument', 'piano'),
            color=color,
            points=points,
            start_t=data.get('start_t', 0.0),
            end_t=data.get('end_t', 0.0),
            stroke_id=data.get('stroke_id', '')
        )


@dataclass
class Project:
    """项目 - 完整作品"""
    name: str = "未命名作品"
    bpm: int = 120              # 节拍速度
    quantize: str = "1/8"       # 量化精度
    scale: str = "pentatonic"   # 音阶类型
    root_note: int = 60         # 根音（MIDI）
    width: int = 640            # 画布宽度
    height: int = 480           # 画布高度
    strokes: List[Stroke] = field(default_factory=list)
    created_at: str = ""
    duration: float = 0.0       # 总时长（秒）
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def add_stroke(self, stroke: Stroke):
        """添加笔画"""
        self.strokes.append(stroke)
        self._update_duration()
    
    def _update_duration(self):
        """更新总时长"""
        if self.strokes:
            self.duration = max(s.end_t for s in self.strokes)
    
    def get_strokes_at_time(self, t: float, tolerance: float = 0.1) -> List[Stroke]:
        """获取指定时间点的笔画"""
        return [s for s in self.strokes if s.start_t <= t <= s.end_t + tolerance]
    
    def get_points_in_x_range(self, x_start: int, x_end: int) -> List[tuple]:
        """获取 X 范围内的所有点（用于扫描回放）"""
        result = []
        for stroke in self.strokes:
            for point in stroke.points:
                if x_start <= point.x <= x_end:
                    result.append((point, stroke))
        return result
    
    def clear(self):
        """清空项目"""
        self.strokes = []
        self.duration = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'bpm': self.bpm,
            'quantize': self.quantize,
            'scale': self.scale,
            'root_note': self.root_note,
            'width': self.width,
            'height': self.height,
            'strokes': [s.to_dict() for s in self.strokes],
            'created_at': self.created_at,
            'duration': self.duration
        }
    
    def to_json(self, indent: int = 2) -> str:
        """导出为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    def save(self, filepath: str) -> bool:
        """保存到文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.to_json())
            return True
        except Exception as e:
            logger.error(f"保存项目失败: {e}")
            return False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        strokes = [Stroke.from_dict(s) for s in data.get('strokes', [])]
        return cls(
            name=data.get('name', '未命名作品'),
            bpm=data.get('bpm', 120),
            quantize=data.get('quantize', '1/8'),
            scale=data.get('scale', 'pentatonic'),
            root_note=data.get('root_note', 60),
            width=data.get('width', 640),
            height=data.get('height', 480),
            strokes=strokes,
            created_at=data.get('created_at', ''),
            duration=data.get('duration', 0.0)
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Project':
        """从 JSON 字符串加载"""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    @classmethod
    def load(cls, filepath: str) -> Optional['Project']:
        """从文件加载"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return cls.from_json(f.read())
        except Exception as e:
            logger.error(f"加载项目失败: {e}")
            return None


# 辅助函数

def quantize_time(t: float, bpm: int, quantize: str = "1/8") -> float:
    """
    将时间量化到节拍网格
    
    Args:
        t: 原始时间（秒）
        bpm: 每分钟节拍数
        quantize: 量化精度（"1/4", "1/8", "1/16"）
    
    Returns:
        量化后的时间
    """
    beat_duration = 60.0 / bpm  # 一拍的时长（秒）
    
    # 解析量化精度
    if quantize == "1/4":
        grid = beat_duration
    elif quantize == "1/8":
        grid = beat_duration / 2
    elif quantize == "1/16":
        grid = beat_duration / 4
    else:
        grid = beat_duration / 2  # 默认 1/8
    
    # 量化到最近的网格
    return round(t / grid) * grid


def time_to_beat(t: float, bpm: int) -> float:
    """将时间转换为节拍数"""
    return t * bpm / 60.0


def beat_to_time(beat: float, bpm: int) -> float:
    """将节拍数转换为时间"""
    return beat * 60.0 / bpm
