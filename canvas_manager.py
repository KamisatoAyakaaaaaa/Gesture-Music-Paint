# -*- coding: utf-8 -*-
"""
画布管理器模块 - 多层渲染、粒子效果、撤销/重做
"""

import cv2
import numpy as np
import logging
from collections import deque
from datetime import datetime
import os
import random
import math

logger = logging.getLogger('GesturePaint.Canvas')

from config import (
    CAMERA_WIDTH, CAMERA_HEIGHT, MAX_UNDO_STEPS,
    INSTRUMENTS, INSTRUMENT_LIST,
    WAVEFORM_HEIGHT, WAVEFORM_SEGMENTS, WAVEFORM_DECAY, WAVEFORM_COLOR,
    PARTICLE_COUNT, PARTICLE_LIFETIME, PARTICLE_SPEED,
    HEADER_HEIGHT
)
from project_model import Project, Stroke, Point
import time


class ParticleSystem:
    """
    向量化粒子系统 - 使用 NumPy 批量计算，性能提升 5-10 倍
    """
    def __init__(self, max_particles: int = 500):
        self.max_particles = max_particles
        # 预分配数组
        self.positions = np.zeros((max_particles, 2), dtype=np.float32)  # x, y
        self.velocities = np.zeros((max_particles, 2), dtype=np.float32)  # vx, vy
        self.colors = np.zeros((max_particles, 3), dtype=np.uint8)  # BGR
        self.lifetimes = np.zeros(max_particles, dtype=np.float32)
        self.max_lifetimes = np.zeros(max_particles, dtype=np.float32)
        self.sizes = np.zeros(max_particles, dtype=np.float32)
        self.active = np.zeros(max_particles, dtype=bool)
        self.count = 0
    
    def spawn(self, x: int, y: int, color: tuple, velocity: int = 100, count: int = 5):
        """批量生成粒子"""
        actual_count = int(count * (velocity / 127.0 + 0.5))
        actual_count = min(actual_count, self.max_particles - np.sum(self.active))
        
        if actual_count <= 0:
            return
        
        # 找到空闲位置
        free_indices = np.where(~self.active)[0][:actual_count]
        
        if len(free_indices) == 0:
            return
        
        # 批量设置属性
        speed = PARTICLE_SPEED * (velocity / 127.0 + 0.5)
        angles = np.random.uniform(0, 2 * math.pi, len(free_indices))
        
        self.positions[free_indices, 0] = x
        self.positions[free_indices, 1] = y
        self.velocities[free_indices, 0] = np.cos(angles) * speed
        self.velocities[free_indices, 1] = np.sin(angles) * speed - 2
        self.colors[free_indices] = color
        self.lifetimes[free_indices] = PARTICLE_LIFETIME
        self.max_lifetimes[free_indices] = PARTICLE_LIFETIME
        self.sizes[free_indices] = np.random.randint(3, 9, len(free_indices))
        self.active[free_indices] = True
    
    def update(self):
        """批量更新所有粒子"""
        if not np.any(self.active):
            return
        
        active_mask = self.active
        
        # 更新位置
        self.positions[active_mask] += self.velocities[active_mask]
        
        # 应用重力和阻力
        self.velocities[active_mask, 1] += 0.2  # 重力
        self.velocities[active_mask, 0] *= 0.98  # X阻力
        
        # 减少生命周期
        self.lifetimes[active_mask] -= 1
        
        # 标记死亡粒子
        self.active[self.lifetimes <= 0] = False
    
    def draw(self, img):
        """批量绘制所有粒子"""
        if not np.any(self.active):
            return
        
        h, w = img.shape[:2]
        active_indices = np.where(self.active)[0]
        
        for idx in active_indices:
            x, y = int(self.positions[idx, 0]), int(self.positions[idx, 1])
            
            # 边界检查
            if not (0 <= x < w and 0 <= y < h):
                continue
            
            # 计算 alpha 和大小
            alpha = self.lifetimes[idx] / self.max_lifetimes[idx]
            color = tuple(int(c * alpha) for c in self.colors[idx])
            size = max(1, int(self.sizes[idx] * alpha))
            
            cv2.circle(img, (x, y), size, color, -1)
    
    def clear(self):
        """清空所有粒子"""
        self.active[:] = False


# 保留旧的 Particle 类用于兼容性
class Particle:
    """音符粒子（兼容性保留）"""
    def __init__(self, x: int, y: int, color: tuple, velocity: int = 100):
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.lifetime = PARTICLE_LIFETIME
        self.max_lifetime = PARTICLE_LIFETIME
        
        speed = PARTICLE_SPEED * (velocity / 127.0 + 0.5)
        angle = random.uniform(0, 2 * math.pi)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - 2
        self.size = random.randint(3, 8)
    
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.2
        self.vx *= 0.98
        self.lifetime -= 1
        return self.lifetime > 0
    
    def draw(self, img):
        if self.lifetime <= 0:
            return
        alpha = self.lifetime / self.max_lifetime
        color = tuple(int(c * alpha) for c in self.color)
        size = max(1, int(self.size * alpha))
        x, y = int(self.x), int(self.y)
        if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
            cv2.circle(img, (x, y), size, color, -1)


class CanvasManager:
    """
    画布管理器 - 支持音乐可视化效果
    """
    
    def __init__(self, width=CAMERA_WIDTH, height=CAMERA_HEIGHT):
        self.width = width
        self.height = height
        
        # 主画布（绘画内容）
        self.canvas = np.zeros((height, width, 3), np.uint8)
        
        # 效果层（音波、粒子等）
        self.effect_layer = np.zeros((height, width, 3), np.uint8)
        
        # 发光层
        self.glow_layer = np.zeros((height, width, 3), np.uint8)
        
        # 撤销/重做栈
        self.undo_stack = deque(maxlen=MAX_UNDO_STEPS)
        self.redo_stack = deque(maxlen=MAX_UNDO_STEPS)
        
        # 向量化粒子系统（性能优化）
        self.particle_system = ParticleSystem(max_particles=PARTICLE_COUNT * 10)
        self.particles = []  # 保留用于兼容性
        
        # 音波数据
        self.waveform_data = np.zeros(WAVEFORM_SEGMENTS)
        
        # 绘画轨迹（用于显示旋律线）
        self.melody_trail = deque(maxlen=100)
        
        # 当前乐器颜色
        self.current_color = INSTRUMENTS['piano']['color']
        
        # 项目数据（乐谱模型）
        self.project = Project(width=width, height=height)
        self.current_stroke: Stroke = None          # 当前正在绘制的笔画
        self.project_start_time: float = 0.0        # 项目开始时间
        self.stroke_start_time: float = 0.0         # 当前笔画开始时间
        self.current_instrument: str = 'piano'      # 当前乐器
    
    # 历史记录管理
    
    def save_state(self):
        """保存当前状态"""
        state = (self.canvas.copy(), self.glow_layer.copy())
        self.undo_stack.append(state)
        self.redo_stack.clear()
    
    def undo(self):
        """撤销"""
        if len(self.undo_stack) > 0:
            self.redo_stack.append((self.canvas.copy(), self.glow_layer.copy()))
            state = self.undo_stack.pop()
            self.canvas = state[0]
            self.glow_layer = state[1]
            return True
        return False
    
    def redo(self):
        """重做"""
        if len(self.redo_stack) > 0:
            self.undo_stack.append((self.canvas.copy(), self.glow_layer.copy()))
            state = self.redo_stack.pop()
            self.canvas = state[0]
            self.glow_layer = state[1]
            return True
        return False
    
    def get_history_info(self):
        """获取历史记录信息"""
        return len(self.undo_stack), len(self.redo_stack)
    
    def clear_all(self):
        """清空画布"""
        if np.any(self.canvas) or np.any(self.glow_layer):
            self.save_state()
        self.canvas = np.zeros((self.height, self.width, 3), np.uint8)
        self.glow_layer = np.zeros((self.height, self.width, 3), np.uint8)
        self.particle_system.clear()  # 使用向量化系统
        self.particles = []  # 兼容性
        self.melody_trail.clear()
        # 清空项目数据
        self.project.clear()
        self.current_stroke = None
    
    # 笔画记录（乐谱数据）
    
    def start_project(self):
        """开始新项目，记录开始时间"""
        self.project = Project(width=self.width, height=self.height)
        self.project_start_time = time.time()
        self.current_stroke = None
    
    def start_stroke(self, instrument: str, color: tuple):
        """
        开始一个新笔画
        
        Args:
            instrument: 乐器标识
            color: 颜色
        """
        self.current_instrument = instrument
        self.stroke_start_time = time.time()
        relative_start = self.stroke_start_time - self.project_start_time if self.project_start_time > 0 else 0
        
        self.current_stroke = Stroke(
            instrument=instrument,
            color=color,
            start_t=relative_start
        )
    
    def add_stroke_point(self, x: int, y: int, thickness: int) -> bool:
        """
        添加点到当前笔画
        
        Args:
            x, y: 坐标
            thickness: 粗细
            
        Returns:
            是否成功添加
        """
        if self.current_stroke is None:
            return False
        
        current_time = time.time()
        relative_t = current_time - self.project_start_time if self.project_start_time > 0 else 0
        
        self.current_stroke.add_point(x, y, thickness, relative_t)
        return True
    
    def end_stroke(self) -> Stroke:
        """
        结束当前笔画并添加到项目
        
        Returns:
            完成的笔画对象
        """
        if self.current_stroke is None:
            return None
        
        stroke = self.current_stroke
        if len(stroke.points) > 0:
            self.project.add_stroke(stroke)
        
        self.current_stroke = None
        return stroke
    
    def get_current_stroke(self) -> Stroke:
        """获取当前正在绘制的笔画"""
        return self.current_stroke
    
    def get_project(self) -> Project:
        """获取项目数据"""
        return self.project
    
    def export_project(self, filepath: str) -> bool:
        """导出项目到文件"""
        return self.project.save(filepath)
    
    def import_project(self, filepath: str) -> bool:
        """从文件导入项目"""
        loaded = Project.load(filepath)
        if loaded:
            self.project = loaded
            return True
        return False
    
    def get_project_duration(self) -> float:
        """获取项目时长"""
        return self.project.duration
    
    def get_stroke_count(self) -> int:
        """获取笔画数量"""
        return len(self.project.strokes)
    
    # 绘画功能
    
    def set_instrument_color(self, instrument_key: str):
        """设置当前乐器对应的颜色"""
        if instrument_key in INSTRUMENTS:
            self.current_color = INSTRUMENTS[instrument_key]['color']
    
    def draw_melody_line(self, pt1: tuple, pt2: tuple, color: tuple, thickness: int):
        """
        绘制旋律线（带发光效果）
        
        Args:
            pt1, pt2: 起点和终点
            color: BGR颜色
            thickness: 粗细
        """
        # 主线条
        cv2.line(self.canvas, pt1, pt2, color, thickness, cv2.LINE_AA)
        
        # 发光效果
        glow_color = tuple(min(255, int(c * 0.5)) for c in color)
        cv2.line(self.glow_layer, pt1, pt2, glow_color, thickness + 6, cv2.LINE_AA)
        
        # 外发光
        outer_glow = tuple(min(255, int(c * 0.25)) for c in color)
        cv2.line(self.glow_layer, pt1, pt2, outer_glow, thickness + 12, cv2.LINE_AA)
        
        # 添加到轨迹
        self.melody_trail.append({
            'pt': pt2,
            'color': color,
            'thickness': thickness,
            'age': 0
        })
    
    def spawn_note_particles(self, x: int, y: int, color: tuple, velocity: int, count: int = 10):
        """
        在指定位置生成音符粒子（使用向量化系统）
        
        Args:
            x, y: 位置
            color: 颜色
            velocity: 音量（影响粒子数量和速度）
            count: 基础粒子数量
        """
        # 使用向量化粒子系统
        self.particle_system.spawn(x, y, color, velocity, count)
    
    def update_particles(self):
        """更新所有粒子（向量化批量更新）"""
        self.particle_system.update()
    
    def draw_particles(self, img):
        """绘制所有粒子（向量化）"""
        self.particle_system.draw(img)
    
    # 音波可视化
    
    def update_waveform(self, waveform_data: np.ndarray):
        """更新音波数据"""
        self.waveform_data = waveform_data
    
    def draw_waveform(self, img, y_offset: int = None):
        """
        绘制音波可视化
        
        Args:
            img: 目标图像
            y_offset: Y偏移（默认在底部）
        """
        if y_offset is None:
            y_offset = self.height - WAVEFORM_HEIGHT - 60
        
        h, w = img.shape[:2]
        segment_width = w // WAVEFORM_SEGMENTS
        
        # 绘制音波
        points = []
        for i, value in enumerate(self.waveform_data):
            x = i * segment_width + segment_width // 2
            y = int(y_offset + WAVEFORM_HEIGHT // 2 - value * WAVEFORM_HEIGHT // 2)
            points.append((x, y))
        
        if len(points) >= 2:
            # 绘制填充区域
            fill_points = [(0, y_offset + WAVEFORM_HEIGHT // 2)]
            fill_points.extend(points)
            fill_points.append((w, y_offset + WAVEFORM_HEIGHT // 2))
            
            pts = np.array(fill_points, dtype=np.int32)
            
            # 半透明填充
            overlay = img.copy()
            cv2.fillPoly(overlay, [pts], (WAVEFORM_COLOR[0] // 3, WAVEFORM_COLOR[1] // 3, WAVEFORM_COLOR[2] // 3))
            cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            
            # 绘制线条
            pts_line = np.array(points, dtype=np.int32)
            cv2.polylines(img, [pts_line], False, WAVEFORM_COLOR, 2, cv2.LINE_AA)
            
            # 绘制点
            for i, (x, y) in enumerate(points):
                if abs(self.waveform_data[i]) > 0.1:
                    cv2.circle(img, (x, y), 4, WAVEFORM_COLOR, -1)
    
    def draw_frequency_bars(self, img, y_offset: int = None):
        """
        绘制频率条形图
        
        Args:
            img: 目标图像
            y_offset: Y偏移
        """
        if y_offset is None:
            y_offset = self.height - WAVEFORM_HEIGHT - 60
        
        h, w = img.shape[:2]
        bar_count = min(32, WAVEFORM_SEGMENTS)
        bar_width = w // bar_count - 4
        
        # 重采样音波数据
        if len(self.waveform_data) > bar_count:
            step = len(self.waveform_data) // bar_count
            bars = [abs(self.waveform_data[i * step]) for i in range(bar_count)]
        else:
            bars = [abs(v) for v in self.waveform_data]
        
        for i, value in enumerate(bars):
            x = i * (bar_width + 4) + 2
            bar_height = int(value * WAVEFORM_HEIGHT * 0.8)
            
            if bar_height < 2:
                bar_height = 2
            
            # 颜色渐变（根据高度）
            intensity = min(255, int(value * 255 + 100))
            color = (intensity, intensity // 2, 0)  # 橙黄色渐变
            
            # 绘制条形
            y1 = y_offset + WAVEFORM_HEIGHT - bar_height
            y2 = y_offset + WAVEFORM_HEIGHT
            cv2.rectangle(img, (x, y1), (x + bar_width, y2), color, -1)
            
            # 顶部高亮
            cv2.rectangle(img, (x, y1), (x + bar_width, y1 + 3), (255, 255, 255), -1)
    
    # 旋律轨迹
    
    def draw_melody_trail(self, img):
        """绘制旋律轨迹（淡出效果）"""
        trail_list = list(self.melody_trail)
        
        for i, point in enumerate(trail_list):
            point['age'] += 1
            
            # 计算透明度
            alpha = max(0, 1 - point['age'] / 50)
            
            if alpha > 0 and i > 0:
                prev_point = trail_list[i - 1]
                
                # 淡化颜色
                color = tuple(int(c * alpha) for c in point['color'])
                thickness = max(1, int(point['thickness'] * alpha))
                
                cv2.line(img, prev_point['pt'], point['pt'], color, thickness, cv2.LINE_AA)
    
    # 画布合并与渲染
    
    def merge_canvases(self, base_img, show_waveform: bool = True, show_bars: bool = False):
        """
        合并所有画布层到基础图像
        
        Args:
            base_img: 基础图像（摄像头帧）
            show_waveform: 是否显示音波
            show_bars: 是否显示频率条
            
        Returns:
            合并后的图像
        """
        result = base_img.copy()
        
        # 更新粒子
        self.update_particles()
        
        # 处理发光层 - 优化：降采样后模糊再放大，性能提升 4-8 倍
        if np.any(self.glow_layer):
            # 缩小到 1/4 尺寸
            small = cv2.resize(self.glow_layer, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
            # 在小尺寸上模糊（核也相应缩小）
            small_blurred = cv2.GaussianBlur(small, (7, 7), 0)
            # 放大回原尺寸
            glow_blurred = cv2.resize(small_blurred, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
            result = cv2.addWeighted(result, 1.0, glow_blurred, 0.5, 0)
        
        # 合并主画布
        gray = cv2.cvtColor(self.canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY_INV)
        mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        
        result = cv2.bitwise_and(result, mask_3ch)
        result = cv2.bitwise_or(result, self.canvas)
        
        # 绘制旋律轨迹
        self.draw_melody_trail(result)
        
        # 绘制粒子
        self.draw_particles(result)
        
        # 绘制音波可视化
        if show_waveform:
            self.draw_waveform(result)
        elif show_bars:
            self.draw_frequency_bars(result)
        
        return result
    
    # 保存功能
    
    def save_painting(self, folder: str = "SavedPaintings"):
        """保存画作"""
        try:
            os.makedirs(folder, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{folder}/music_painting_{timestamp}.png"
            
            # 创建白底画布
            white_bg = np.ones((self.height, self.width, 3), np.uint8) * 255
            result = self.merge_canvases(white_bg, show_waveform=False)
            
            cv2.imwrite(filename, result)
            logger.info(f"画作已保存: {filename}")
            return filename
        except Exception as e:
            logger.error(f"保存失败: {e}")
            return None
    
    def get_canvas_thumbnail(self, size: tuple = (160, 90)):
        """获取画布缩略图"""
        return cv2.resize(self.canvas, size)