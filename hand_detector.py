# -*- coding: utf-8 -*-
"""
手势检测模块 - MediaPipe 手势识别
"""

import cv2
import numpy as np
import os
import logging
from collections import deque
from functools import lru_cache

logger = logging.getLogger('GesturePaint.Detector')

from config import (
    DETECTION_CONFIDENCE, TRACKING_CONFIDENCE, MAX_HANDS,
    SMOOTHING_FACTOR, GESTURE_COOLDOWN, HEADER_HEIGHT,
    FIST_COOLDOWN, PEACE_COOLDOWN, FIVE_COOLDOWN
)

# 模型文件路径
MODEL_PATH = "hand_landmarker.task"

# 性能优化配置
USE_GPU = True  # 尝试使用 GPU
LITE_MODE = False  # 轻量模式（降低精度换取速度）


def check_model():
    """检查模型文件是否存在"""
    if not os.path.exists(MODEL_PATH):
        logger.error(f"错误：找不到模型文件 {MODEL_PATH}")
        logger.error("请手动下载并放在项目目录")
        return False
    return True


class GestureType:
    """手势类型枚举"""
    NONE = "none"
    DRAW = "draw"
    SELECT = "select"
    FIST = "fist"
    PEACE = "peace"
    FIVE = "five"


class HandDetector:
    """
    手势检测器 - 优化版本
    
    性能优化：
        - 支持 GPU 加速
        - 预分配内存
        - 手势识别缓存
        - 坐标平滑优化
    """
    
    # 手指指尖 ID（类常量）
    TIP_IDS = (4, 8, 12, 16, 20)
    
    # 手部连接（预定义）
    CONNECTIONS = (
        (0,1),(1,2),(2,3),(3,4),
        (0,5),(5,6),(6,7),(7,8),
        (0,9),(9,10),(10,11),(11,12),
        (0,13),(13,14),(14,15),(15,16),
        (0,17),(17,18),(18,19),(19,20),
        (5,9),(9,13),(13,17)
    )
    
    def __init__(self, mode=False, max_hands=MAX_HANDS, 
                 detection_con=DETECTION_CONFIDENCE, track_con=TRACKING_CONFIDENCE):
        self.mode = mode
        self.max_hands = max_hands
        self.detection_con = detection_con
        self.track_con = track_con
        
        # 延迟初始化
        self.detector = None
        self._initialized = False
        
        # 检测结果缓存
        self.lm_list = []
        self.detection_result = None
        self._cached_fingers = None
        self._fingers_valid = False
        
        # 坐标平滑（优化：使用 numpy）
        self.smooth_pos = None
        
        # 手势稳定性
        self.gesture_history = deque(maxlen=GESTURE_COOLDOWN)
        self.current_gesture = GestureType.NONE
        
        # 手势冷却计时器
        self.cooldowns = {
            'fist': 0,
            'peace': 0,
            'five': 0
        }
        
        # 手势触发标志
        self.triggers = {
            'fist': False,
            'peace': False,
            'five': False
        }
        
        # 预分配绘制用的点列表
        self._points_buffer = [(0, 0)] * 21
    
    def _init_detector(self):
        """初始化 MediaPipe HandLandmarker（优化版）"""
        if self._initialized:
            return
        
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
            
            if not check_model():
                raise FileNotFoundError("模型文件不存在")
            
            # 配置选项
            base_options = mp_python.BaseOptions(
                model_asset_path=MODEL_PATH,
                delegate=mp_python.BaseOptions.Delegate.GPU if USE_GPU else mp_python.BaseOptions.Delegate.CPU
            )
            
            # 优化的检测参数
            options = mp_vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.IMAGE,
                num_hands=self.max_hands,
                min_hand_detection_confidence=self.detection_con,
                min_tracking_confidence=self.track_con
            )
            
            self.detector = mp_vision.HandLandmarker.create_from_options(options)
            self._initialized = True
            
            delegate_name = "GPU" if USE_GPU else "CPU"
            logger.info(f"MediaPipe 手势检测器初始化完成 (使用 {delegate_name})")
            
        except Exception as e:
            # GPU 不可用时回退到 CPU
            if USE_GPU:
                logger.warning(f"GPU 初始化失败，回退到 CPU: {e}")
                self._init_detector_cpu()
            else:
                logger.error(f"初始化错误: {e}")
                raise
    
    def _init_detector_cpu(self):
        """CPU 模式初始化"""
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
            
            base_options = mp_python.BaseOptions(
                model_asset_path=MODEL_PATH,
                delegate=mp_python.BaseOptions.Delegate.CPU
            )
            
            options = mp_vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.IMAGE,
                num_hands=self.max_hands,
                min_hand_detection_confidence=self.detection_con,
                min_tracking_confidence=self.track_con
            )
            
            self.detector = mp_vision.HandLandmarker.create_from_options(options)
            self._initialized = True
            logger.info("MediaPipe 手势检测器初始化完成 (使用 CPU)")
            
        except Exception as e:
            logger.error(f"CPU 初始化错误: {e}")
            raise
    
    def find_hands(self, img, draw=True):
        """
        检测手部（优化版）
        
        Args:
            img: BGR图像
            draw: 是否绘制
            
        Returns:
            处理后的图像
        """
        if not self._initialized:
            self._init_detector()
        
        h, w = img.shape[:2]
        
        # 优化：直接使用 numpy 数组转换，避免额外复制
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 创建 MediaPipe Image
        import mediapipe as mp
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img_rgb))
        
        # 检测
        self.detection_result = self.detector.detect(mp_image)
        
        # 失效手指缓存
        self._fingers_valid = False
        
        # 绘制结果
        if draw and self.detection_result.hand_landmarks:
            for hand_landmarks in self.detection_result.hand_landmarks:
                self._draw_landmarks_optimized(img, hand_landmarks, h, w)
        
        return img
    
    def _draw_landmarks_optimized(self, img, landmarks, h, w):
        """绘制手部关键点（优化版）"""
        # 更新点缓冲区
        for i, lm in enumerate(landmarks):
            self._points_buffer[i] = (int(lm.x * w), int(lm.y * h))
        
        # 批量绘制连线
        for start, end in self.CONNECTIONS:
            pt1 = self._points_buffer[start]
            pt2 = self._points_buffer[end]
            cv2.line(img, pt1, pt2, (255, 200, 0), 2, cv2.LINE_AA)
        
        # 批量绘制关键点
        for i, (cx, cy) in enumerate(self._points_buffer):
            color = (0, 255, 128) if i in self.TIP_IDS else (255, 100, 0)
            cv2.circle(img, (cx, cy), 5, color, -1)
    
    def find_position(self, img, hand_no=0, draw=False):
        """
        获取手部关键点位置（优化版）
        
        Returns:
            lm_list: [[id, x, y], ...]
            bbox: (xmin, ymin, xmax, ymax)
            within: 手是否在有效区域内
        """
        self.lm_list = []
        bbox = ()
        within = True
        
        if not (self.detection_result and self.detection_result.hand_landmarks):
            return self.lm_list, bbox, within
        
        if hand_no >= len(self.detection_result.hand_landmarks):
            return self.lm_list, bbox, within
        
        hand = self.detection_result.hand_landmarks[hand_no]
        h, w = img.shape[:2]
        
        x_min, x_max = w, 0
        y_min, y_max = h, 0
        
        for idx, lm in enumerate(hand):
            cx, cy = int(lm.x * w), int(lm.y * h)
            
            # 边界检查
            if cx < 0 or cx > w or cy < HEADER_HEIGHT or cy > h:
                within = False
            
            # 更新边界框
            x_min = min(x_min, cx)
            x_max = max(x_max, cx)
            y_min = min(y_min, cy)
            y_max = max(y_max, cy)
            
            self.lm_list.append([idx, cx, cy])
            
            if draw:
                cv2.circle(img, (cx, cy), 6, (255, 0, 255), -1)
        
        if self.lm_list:
            bbox = (x_min, y_min, x_max, y_max)
        
        # 失效手指缓存
        self._fingers_valid = False
        
        return self.lm_list, bbox, within
    
    def fingers_up(self):
        """
        检测伸直的手指（带缓存）
        
        Returns:
            [拇指, 食指, 中指, 无名指, 小指] - 1=伸直, 0=弯曲
        """
        # 使用缓存
        if self._fingers_valid and self._cached_fingers is not None:
            return self._cached_fingers
        
        if not self.lm_list or len(self.lm_list) < 21:
            return [0, 0, 0, 0, 0]
        
        fingers = []
        
        # 拇指：比较x坐标
        thumb_tip_x = self.lm_list[self.TIP_IDS[0]][1]
        thumb_ip_x = self.lm_list[self.TIP_IDS[0] - 1][1]
        fingers.append(1 if thumb_tip_x < thumb_ip_x else 0)
        
        # 其他四指：比较y坐标
        for idx in range(1, 5):
            tip_y = self.lm_list[self.TIP_IDS[idx]][2]
            pip_y = self.lm_list[self.TIP_IDS[idx] - 2][2]
            fingers.append(1 if tip_y < pip_y else 0)
        
        # 缓存结果
        self._cached_fingers = fingers
        self._fingers_valid = True
        
        return fingers
    
    def detect_gesture(self):
        """
        检测当前手势类型（优化版）
        
        Returns:
            GestureType: 手势类型
            bool: 是否为新触发
        """
        # 更新冷却计时器
        for key in self.cooldowns:
            if self.cooldowns[key] > 0:
                self.cooldowns[key] -= 1
        
        if not self.lm_list or len(self.lm_list) < 21:
            self.current_gesture = GestureType.NONE
            return GestureType.NONE, False
        
        fingers = self.fingers_up()
        total_fingers = sum(fingers)
        
        new_trigger = False
        
        # 五指张开 = 切换乐器
        if total_fingers == 5:
            self.current_gesture = GestureType.FIVE
            if self.cooldowns['five'] == 0 and not self.triggers['five']:
                self.triggers['five'] = True
                self.cooldowns['five'] = FIVE_COOLDOWN
                new_trigger = True
            return GestureType.FIVE, new_trigger
        else:
            self.triggers['five'] = False
        
        # 握拳 = 播放/停止
        if total_fingers == 0:
            self.current_gesture = GestureType.FIST
            if self.cooldowns['fist'] == 0 and not self.triggers['fist']:
                self.triggers['fist'] = True
                self.cooldowns['fist'] = FIST_COOLDOWN
                new_trigger = True
            return GestureType.FIST, new_trigger
        else:
            self.triggers['fist'] = False
        
        # 比耶 ✌️ = 录制/保存
        if (fingers[1] == 1 and fingers[2] == 1 and 
            fingers[0] == 0 and fingers[3] == 0 and fingers[4] == 0):
            self.current_gesture = GestureType.PEACE
            if self.cooldowns['peace'] == 0 and not self.triggers['peace']:
                self.triggers['peace'] = True
                self.cooldowns['peace'] = PEACE_COOLDOWN
                new_trigger = True
            return GestureType.PEACE, new_trigger
        else:
            self.triggers['peace'] = False
        
        # 单指 = 绘制
        if fingers[1] == 1 and fingers[2] == 0:
            self.current_gesture = GestureType.DRAW
            return GestureType.DRAW, False
        
        # 双指 = 选择模式
        if (fingers[1] == 1 and fingers[2] == 1 and 
            fingers[3] == 0 and fingers[4] == 0):
            self.current_gesture = GestureType.SELECT
            return GestureType.SELECT, False
        
        self.current_gesture = GestureType.NONE
        return GestureType.NONE, False
    
    def get_finger_position(self, finger_id=8):
        """获取指定手指的位置"""
        if self.lm_list and len(self.lm_list) > finger_id:
            return self.lm_list[finger_id][1], self.lm_list[finger_id][2]
        return None
    
    def get_smoothed_position(self, x, y):
        """
        获取平滑后的坐标（优化版：使用 numpy）
        
        Args:
            x, y: 原始坐标
            
        Returns:
            平滑后的 (x, y)
        """
        current = np.array([x, y], dtype=np.float32)
        
        if self.smooth_pos is None:
            self.smooth_pos = current
        else:
            self.smooth_pos = self.smooth_pos * (1 - SMOOTHING_FACTOR) + current * SMOOTHING_FACTOR
        
        return int(self.smooth_pos[0]), int(self.smooth_pos[1])
    
    def get_distance(self, p1, p2, img=None, draw=True):
        """计算两点距离"""
        if not self.lm_list or p1 >= len(self.lm_list) or p2 >= len(self.lm_list):
            return 0, img, []
        
        x1, y1 = self.lm_list[p1][1], self.lm_list[p1][2]
        x2, y2 = self.lm_list[p2][1], self.lm_list[p2][2]
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        
        if img is not None and draw:
            cv2.line(img, (x1, y1), (x2, y2), (255, 0, 255), 3)
            cv2.circle(img, (x1, y1), 8, (255, 0, 255), -1)
            cv2.circle(img, (x2, y2), 8, (255, 0, 255), -1)
            cv2.circle(img, (cx, cy), 8, (0, 255, 255), -1)
        
        distance = np.hypot(x2 - x1, y2 - y1)
        return distance, img, [x1, y1, x2, y2, cx, cy]
    
    def reset_smoothing(self):
        """重置平滑缓存"""
        self.smooth_pos = None
        self._fingers_valid = False
        self._cached_fingers = None
