# -*- coding: utf-8 -*-
"""
Web 服务器模块 - Flask + WebSocket 实现
"""

from flask import Flask, render_template, Response, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
import cv2
import numpy as np
import base64
import threading
import time
import os
import json
import logging
from datetime import datetime

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gesture_paint.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('GesturePaint')

from config import (
    CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_INDEX, HEADER_HEIGHT,
    INSTRUMENTS, INSTRUMENT_LIST, DEFAULT_INSTRUMENT,
    BRUSH_THICKNESS_OPTIONS, DEFAULT_BRUSH_THICKNESS,
    WAVEFORM_DECAY, map_thickness_to_volume
)
from hand_detector import HandDetector, GestureType
from music_engine import MusicEngine
from canvas_manager import CanvasManager
from settings_manager import get_settings
from gallery_manager import get_gallery
from sequencer import Sequencer, PlaybackMode

# 创建 Flask 应用
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'gesture-music-paint-dev-key')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# WebSocket
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局状态
class AppState:
    def __init__(self):
        self.cap = None
        self.detector = None
        self.music_engine = None
        self.canvas_manager = None
        self.sequencer = None  # Master 回放音序器
        
        self.is_running = False
        self.is_playing = True
        self.is_recording = False
        self.drawing_paused = False
        self.master_playing = False  # Master 回放状态
        
        self.prev_x, self.prev_y = 0, 0
        self.is_drawing = False
        self.brush_thickness = DEFAULT_BRUSH_THICKNESS
        self.current_instrument = DEFAULT_INSTRUMENT
        
        self.fps = 0
        self.frame_count = 0
        self.fps_start_time = time.time()
        
        # 性能指标
        self.detection_time_ms = 0      # 手势检测耗时
        self.render_time_ms = 0         # 渲染耗时
        self.note_latency_ms = 0        # 音符触发延迟
        self.last_gesture_time = 0      # 上次手势检测时间
        
        self.lock = threading.Lock()

state = AppState()


# 路由

@app.route('/')
def index():
    """官网主页（落地页）"""
    return render_template('landing.html')


@app.route('/app')
def app_page():
    """Web 应用（手势音乐绘画控制台）"""
    return render_template('index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    """静态文件"""
    return send_from_directory('static', filename)


@app.route('/api/instruments')
def get_instruments():
    """获取乐器列表"""
    instruments = []
    for key in INSTRUMENT_LIST:
        inst = INSTRUMENTS[key]
        instruments.append({
            'key': key,
            'name': inst['name'],
            'name_en': inst['name_en'],
            'color': f"rgb({inst['color'][2]}, {inst['color'][1]}, {inst['color'][0]})"
        })
    return jsonify(instruments)


@app.route('/api/thickness_options')
def get_thickness_options():
    """获取粗细选项"""
    return jsonify(BRUSH_THICKNESS_OPTIONS)


@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """获取用户设置"""
    settings = get_settings()
    return jsonify(settings.get_all())


@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    """更新用户设置"""
    settings = get_settings()
    data = request.get_json()
    
    if not data:
        return jsonify({'error': '无效的请求数据'}), 400
    
    updated = []
    failed = []
    
    for key, value in data.items():
        if settings.set(key, value, save=False):
            updated.append(key)
        else:
            failed.append(key)
    
    # 统一保存
    if updated:
        settings._save_settings()
    
    return jsonify({
        'updated': updated,
        'failed': failed,
        'success': len(failed) == 0
    })


@app.route('/api/settings/reset', methods=['POST'])
def api_reset_settings():
    """重置设置"""
    settings = get_settings()
    key = request.get_json().get('key') if request.get_json() else None
    
    if settings.reset(key):
        return jsonify({'success': True, 'settings': settings.get_all()})
    return jsonify({'success': False}), 400


@app.route('/api/tutorial/complete', methods=['POST'])
def api_complete_tutorial():
    """标记教程完成"""
    settings = get_settings()
    settings.mark_tutorial_completed()
    return jsonify({'success': True})


@app.route('/api/tutorial/status')
def api_tutorial_status():
    """获取教程状态"""
    settings = get_settings()
    return jsonify({
        'should_show': settings.should_show_tutorial(),
        'completed': settings.get('tutorial_completed', False)
    })


# 作品管理 API

@app.route('/api/gallery')
def api_get_gallery():
    """获取作品列表"""
    gallery = get_gallery()
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    works = gallery.get_works(limit=limit, offset=offset)
    total = gallery.get_total_count()
    
    return jsonify({
        'works': works,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@app.route('/api/gallery/<work_id>')
def api_get_work(work_id):
    """获取单个作品信息"""
    gallery = get_gallery()
    work = gallery.get_work(work_id)
    
    if work:
        return jsonify(work)
    return jsonify({'error': '作品不存在'}), 404


@app.route('/api/gallery/<work_id>/thumbnail')
def api_get_thumbnail(work_id):
    """获取作品缩略图"""
    gallery = get_gallery()
    path = gallery.get_thumbnail_path(work_id)
    
    if path and os.path.exists(path):
        return send_from_directory(os.path.dirname(path), os.path.basename(path))
    return jsonify({'error': '缩略图不存在'}), 404


@app.route('/api/gallery/<work_id>/image')
def api_get_work_image(work_id):
    """获取作品图片"""
    gallery = get_gallery()
    path = gallery.get_work_image_path(work_id)
    
    if path and os.path.exists(path):
        return send_from_directory(os.path.dirname(path), os.path.basename(path))
    return jsonify({'error': '图片不存在'}), 404


@app.route('/api/gallery/<work_id>/project')
def api_get_work_project(work_id):
    """获取作品的项目数据（用于回放和导出）"""
    gallery = get_gallery()
    project_data = gallery.get_project_data(work_id)
    
    if project_data:
        return jsonify(project_data)
    return jsonify({'error': '项目数据不存在'}), 404


@app.route('/api/examples')
def api_get_examples():
    """获取示例项目列表"""
    examples_dir = os.path.join(os.path.dirname(__file__), 'examples')
    examples = []
    
    if os.path.exists(examples_dir):
        for filename in os.listdir(examples_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(examples_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        examples.append({
                            'id': filename.replace('.json', ''),
                            'name': data.get('name', filename),
                            'bpm': data.get('bpm', 120),
                            'stroke_count': len(data.get('strokes', [])),
                            'duration': data.get('duration', 0)
                        })
                except Exception as e:
                    logger.error(f"加载示例 {filename} 失败: {e}")
    
    return jsonify(examples)


@app.route('/api/examples/<example_id>')
def api_get_example(example_id):
    """获取示例项目数据"""
    examples_dir = os.path.join(os.path.dirname(__file__), 'examples')
    filepath = os.path.join(examples_dir, f'{example_id}.json')
    
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': '示例不存在'}), 404


@app.route('/api/gallery/<work_id>', methods=['DELETE'])
def api_delete_work(work_id):
    """删除作品"""
    gallery = get_gallery()
    
    if gallery.delete_work(work_id):
        return jsonify({'success': True})
    return jsonify({'error': '删除失败'}), 400


@app.route('/gallery')
def gallery_page():
    """作品库页面"""
    return render_template('gallery.html')


# 视频流

def generate_frames():
    """生成视频帧 - 低延迟优化版"""
    while state.is_running:
        # 快速检查摄像头状态
        if state.cap is None or not state.cap.isOpened():
            time.sleep(0.1)
            continue
        
        # 读取帧（不持锁，减少阻塞）
        success, frame = state.cap.read()
        if not success:
            time.sleep(0.001)
            continue
        
        # 镜像翻转
        frame = cv2.flip(frame, 1)
        
        # 处理帧（持锁保护状态访问）
        with state.lock:
            frame = process_frame(frame)
        
        # 编码为 JPEG（锁外执行，减少锁持有时间）
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # 最小延迟，让出 CPU
        time.sleep(0.001)


@app.route('/video_feed')
def video_feed():
    """视频流端点"""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


def process_frame(frame):
    """处理单帧"""
    if state.detector is None:
        return frame
    
    # 性能计时 - 手势检测
    detection_start = time.time()
    
    # 手势检测
    frame = state.detector.find_hands(frame, draw=True)
    lm_list, bbox, within = state.detector.find_position(frame, draw=False)
    
    state.detection_time_ms = (time.time() - detection_start) * 1000
    
    current_gesture = GestureType.NONE
    hand_detected = len(lm_list) > 0
    
    if hand_detected:
        x1, y1 = lm_list[8][1:]
        gesture, new_trigger = state.detector.detect_gesture()
        current_gesture = gesture
        handle_gesture(frame, gesture, new_trigger, x1, y1, within)
        
        # 发送手势状态（节流：每 5 帧发送一次）
        if state.frame_count % 5 == 0:
            gesture_names = {
                GestureType.NONE: 'none',
                GestureType.DRAW: 'draw',
                GestureType.SELECT: 'select',
                GestureType.FIST: 'fist',
                GestureType.PEACE: 'peace',
                GestureType.FIVE: 'five'
            }
            socketio.emit('gesture_detected', {
                'gesture': gesture_names.get(gesture, 'none'),
                'hand_detected': True,
                'position': {'x': x1, 'y': y1}
            })
    else:
        if state.is_drawing:
            state.is_drawing = False
            state.canvas_manager.end_stroke()  # 结束当前笔画
            state.prev_x, state.prev_y = 0, 0
        
        # 通知手离开
        if state.frame_count % 10 == 0:
            socketio.emit('gesture_detected', {
                'gesture': 'none',
                'hand_detected': False,
                'position': None
            })
    
    # 衰减音波
    if state.music_engine:
        state.music_engine.decay_waveform(WAVEFORM_DECAY)
        waveform = state.music_engine.get_waveform_data()
        state.canvas_manager.update_waveform(waveform)
    
    # 合并画布
    if state.canvas_manager:
        frame = state.canvas_manager.merge_canvases(frame, show_waveform=True)
    
    # 绘制状态栏
    frame = draw_status_bar(frame)
    
    # 更新 FPS
    update_fps()
    
    return frame


def handle_gesture(frame, gesture, new_trigger, x, y, within):
    """处理手势"""
    # 回放时禁用绘画（互斥）
    if state.master_playing:
        # 仅允许握拳手势停止回放
        if gesture == GestureType.FIST and new_trigger:
            if state.sequencer:
                state.sequencer.stop()
                state.master_playing = False
                socketio.emit('master_stopped', {})
        return
    
    if state.drawing_paused:
        if gesture == GestureType.PEACE and new_trigger:
            state.drawing_paused = False
            state.prev_x, state.prev_y = 0, 0
            state.detector.reset_smoothing()
            socketio.emit('status_update', {'drawing_paused': False})
        return
    
    if gesture == GestureType.FIVE and new_trigger:
        info = state.music_engine.switch_instrument()
        state.canvas_manager.set_instrument_color(info['key'])
        state.current_instrument = info['key']
        socketio.emit('instrument_changed', {'instrument': info['key']})
    
    elif gesture == GestureType.FIST and new_trigger:
        state.is_playing = state.music_engine.toggle_play()
        socketio.emit('status_update', {'is_playing': state.is_playing})
    
    elif gesture == GestureType.PEACE and new_trigger:
        toggle_recording()
    
    elif gesture == GestureType.DRAW and within and y > HEADER_HEIGHT:
        handle_draw(frame, x, y)
    
    elif gesture == GestureType.SELECT:
        handle_select(frame, x, y)
    
    else:
        if state.is_drawing:
            state.is_drawing = False
            state.canvas_manager.end_stroke()  # 结束当前笔画


def handle_draw(frame, x, y):
    """处理绘画（混合模式：记录笔画 + Preview 即时音）"""
    instrument_info = state.music_engine.get_instrument_info()
    color = instrument_info['color']
    instrument_key = instrument_info['key']
    
    if not state.is_drawing:
        # 开始新笔画
        state.is_drawing = True
        state.canvas_manager.save_state()
        state.canvas_manager.start_stroke(instrument_key, color)
        state.music_engine.reset_preview_state()
        state.prev_x, state.prev_y = x, y
    
    smooth_x, smooth_y = state.detector.get_smoothed_position(x, y)
    
    # 记录笔画点
    state.canvas_manager.add_stroke_point(smooth_x, smooth_y, state.brush_thickness)
    
    # 绘制线条
    if state.prev_x != 0 and state.prev_y != 0:
        state.canvas_manager.draw_melody_line(
            (state.prev_x, state.prev_y),
            (smooth_x, smooth_y),
            color,
            state.brush_thickness
        )
    
    # 使用 Preview 音（带时间+距离阈值）
    note_triggered = state.music_engine.play_preview_note(
        smooth_x, smooth_y, state.brush_thickness,
        CAMERA_WIDTH, CAMERA_HEIGHT
    )
    
    # 只在成功触发音符时才发送事件和粒子
    if note_triggered:
        velocity = state.music_engine.last_note * 2 if state.music_engine.last_note > 0 else 80
        state.canvas_manager.spawn_note_particles(smooth_x, smooth_y, color, velocity, count=3)
        
        # 发送音符信息
        if state.music_engine.last_note > 0:
            note_name = state.music_engine.get_note_name(state.music_engine.last_note)
            socketio.emit('note_played', {
                'note': note_name,
                'x': smooth_x,
                'y': smooth_y,
                'velocity': velocity
            })
    
    state.prev_x, state.prev_y = smooth_x, smooth_y


def handle_select(frame, x, y):
    """处理选择模式"""
    if state.is_drawing:
        state.is_drawing = False
        state.canvas_manager.end_stroke()  # 结束当前笔画
    state.prev_x, state.prev_y = 0, 0
    state.detector.reset_smoothing()
    
    if y < HEADER_HEIGHT:
        section = x // (CAMERA_WIDTH // len(BRUSH_THICKNESS_OPTIONS))
        if 0 <= section < len(BRUSH_THICKNESS_OPTIONS):
            state.brush_thickness = BRUSH_THICKNESS_OPTIONS[section]
            socketio.emit('thickness_changed', {'thickness': state.brush_thickness})


def draw_status_bar(frame):
    """绘制状态栏"""
    h, w = frame.shape[:2]
    
    # 渐变背景
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 80), (20, 20, 30), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    
    # 当前乐器
    instrument_info = state.music_engine.get_instrument_info() if state.music_engine else {'name_en': 'Piano', 'color': (255, 200, 100)}
    color = instrument_info['color']
    
    cv2.circle(frame, (25, 40), 14, color, -1)
    cv2.circle(frame, (25, 40), 14, (255, 255, 255), 2)
    cv2.putText(frame, f"{instrument_info['name_en']}", (50, 45),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    
    # 粗细和音量
    volume = map_thickness_to_volume(state.brush_thickness)
    cv2.putText(frame, f"Brush: {state.brush_thickness}px | Vol: {volume}", (180, 45),
               cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 200), 1, cv2.LINE_AA)
    
    # FPS
    cv2.putText(frame, f"FPS: {state.fps}", (w - 100, 45),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 1, cv2.LINE_AA)
    
    # 粗细选择栏
    section_width = w // len(BRUSH_THICKNESS_OPTIONS)
    for i, thickness in enumerate(BRUSH_THICKNESS_OPTIONS):
        x1 = i * section_width
        x2 = (i + 1) * section_width
        
        if thickness == state.brush_thickness:
            cv2.rectangle(frame, (x1, 60), (x2, 80), color, -1)
        else:
            cv2.rectangle(frame, (x1, 60), (x2, 80), (40, 40, 50), -1)
        
        cx = x1 + section_width // 2
        cv2.circle(frame, (cx, 70), thickness // 2 + 1, (255, 255, 255), -1)
    
    return frame


def update_fps():
    """更新 FPS 和性能指标"""
    state.frame_count += 1
    elapsed = time.time() - state.fps_start_time
    
    if elapsed >= 1.0:
        state.fps = int(state.frame_count / elapsed)
        state.frame_count = 0
        state.fps_start_time = time.time()
        
        # 每秒发送性能指标
        socketio.emit('perf_metrics', {
            'fps': state.fps,
            'detection_ms': round(state.detection_time_ms, 1),
            'render_ms': round(state.render_time_ms, 1)
        })


def toggle_recording():
    """切换录制"""
    if not state.music_engine:
        return
    
    notes, is_recording = state.music_engine.toggle_recording()
    state.is_recording = is_recording
    
    socketio.emit('status_update', {'is_recording': is_recording})
    
    if not is_recording and notes:
        filepath = state.music_engine.save_recording()
        img_path = state.canvas_manager.save_painting()
        socketio.emit('recording_saved', {
            'notes_path': filepath,
            'image_path': img_path
        })


# WebSocket 事件

@socketio.on('connect')
def on_connect():
    """客户端连接"""
    logger.info(f"客户端连接: {request.sid}")
    # 发送当前系统状态，确保前后端同步
    emit('connected', {
        'status': 'ok',
        'system_running': state.is_running,
        'is_playing': state.is_playing,
        'is_recording': state.is_recording,
        'drawing_paused': state.drawing_paused,
        'current_instrument': state.current_instrument
    })


@socketio.on('disconnect')
def on_disconnect():
    """客户端断开"""
    logger.debug(f"客户端断开: {request.sid}")


@socketio.on('start_system')
def on_start_system():
    """启动系统"""
    try:
        with state.lock:
            if state.is_running:
                emit('error', {'message': '系统已在运行'})
                return
            
            logger.info("正在初始化系统组件...")
            
            # 初始化组件
            state.detector = HandDetector()
            state.music_engine = MusicEngine()
            state.canvas_manager = CanvasManager(CAMERA_WIDTH, CAMERA_HEIGHT)
            state.canvas_manager.start_project()  # 初始化项目
            
            # 初始化 Master 回放音序器
            state.sequencer = Sequencer(state.music_engine)
            state.sequencer.on_note_play = on_sequencer_note_play
            state.sequencer.on_scan_position = on_sequencer_scan_position
            state.sequencer.on_playback_end = on_sequencer_end
            
            # 初始化摄像头 - 带重试机制
            logger.info(f"正在打开摄像头 (索引: {CAMERA_INDEX})...")
            state.cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
            
            # 重试机制：尝试不同的后端
            if not state.cap.isOpened():
                logger.warning("DirectShow 后端失败，尝试默认后端...")
                state.cap = cv2.VideoCapture(CAMERA_INDEX)
            
            if not state.cap.isOpened():
                logger.error("无法打开摄像头")
                emit('camera_error', {
                    'message': '无法访问摄像头',
                    'suggestions': [
                        '检查摄像头是否正确连接',
                        '关闭其他使用摄像头的应用程序',
                        '检查浏览器是否有摄像头权限',
                        '尝试重新插拔摄像头'
                    ]
                })
                return
            
            state.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            state.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            state.cap.set(cv2.CAP_PROP_FPS, 30)
            state.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # 验证摄像头可以读取帧
            ret, test_frame = state.cap.read()
            if not ret:
                logger.error("摄像头已打开但无法读取帧")
                emit('camera_error', {
                    'message': '摄像头已连接但无法获取画面',
                    'suggestions': [
                        '检查摄像头驱动是否正确安装',
                        '尝试降低摄像头分辨率'
                    ]
                })
                state.cap.release()
                state.cap = None
                return
            
            # 设置初始乐器
            state.canvas_manager.set_instrument_color(DEFAULT_INSTRUMENT)
            state.is_running = True
        
        emit('system_started', {'status': 'ok'})
        logger.info("系统启动成功")
        
    except Exception as e:
        logger.exception(f"系统启动失败: {e}")
        emit('error', {'message': f'启动失败: {str(e)}'})


@socketio.on('stop_system')
def on_stop_system():
    """停止系统"""
    with state.lock:
        state.is_running = False
        
        if state.cap:
            state.cap.release()
            state.cap = None
        
        if state.music_engine:
            state.music_engine.cleanup()
            state.music_engine = None
        
        state.detector = None
        state.canvas_manager = None
    
    emit('system_stopped', {'status': 'ok'})
    logger.info("系统已停止")


@socketio.on('set_instrument')
def on_set_instrument(data):
    """设置乐器"""
    instrument = data.get('instrument')
    if instrument and state.music_engine:
        state.music_engine.set_instrument(instrument)
        state.canvas_manager.set_instrument_color(instrument)
        state.current_instrument = instrument
        emit('instrument_changed', {'instrument': instrument})


@socketio.on('set_thickness')
def on_set_thickness(data):
    """设置粗细"""
    thickness = data.get('thickness')
    if thickness:
        state.brush_thickness = int(thickness)
        emit('thickness_changed', {'thickness': state.brush_thickness})


@socketio.on('toggle_play')
def on_toggle_play():
    """切换播放"""
    if state.music_engine:
        state.is_playing = state.music_engine.toggle_play()
        emit('status_update', {'is_playing': state.is_playing})


@socketio.on('toggle_recording')
def on_toggle_recording():
    """切换录制"""
    toggle_recording()


@socketio.on('toggle_pause')
def on_toggle_pause():
    """切换暂停"""
    state.drawing_paused = not state.drawing_paused
    if state.drawing_paused:
        if state.is_drawing:
            state.canvas_manager.end_stroke()  # 结束当前笔画
        state.is_drawing = False
        state.prev_x, state.prev_y = 0, 0
        if state.detector:
            state.detector.reset_smoothing()
    emit('status_update', {'drawing_paused': state.drawing_paused})


@socketio.on('clear_canvas')
def on_clear_canvas():
    """清空画布"""
    if state.canvas_manager:
        state.canvas_manager.clear_all()
        emit('canvas_cleared', {'status': 'ok'})


@socketio.on('undo')
def on_undo():
    """撤销"""
    if state.canvas_manager and state.canvas_manager.undo():
        undo, redo = state.canvas_manager.get_history_info()
        emit('history_update', {'undo': undo, 'redo': redo})


@socketio.on('redo')
def on_redo():
    """重做"""
    if state.canvas_manager and state.canvas_manager.redo():
        undo, redo = state.canvas_manager.get_history_info()
        emit('history_update', {'undo': undo, 'redo': redo})


@socketio.on('save_painting')
def on_save_painting():
    """保存画作"""
    if state.canvas_manager:
        path = state.canvas_manager.save_painting()
        if path:
            # 同时保存到作品库
            try:
                gallery = get_gallery()
                notes_data = None
                if state.music_engine and state.music_engine.recorded_notes:
                    notes_data = [n.to_dict() for n in state.music_engine.recorded_notes]
                
                # 获取项目数据（乐谱模型）
                project_data = None
                if state.canvas_manager:
                    project = state.canvas_manager.get_project()
                    if project and len(project.strokes) > 0:
                        project_data = project.to_dict()
                
                work_info = gallery.save_work(
                    canvas=state.canvas_manager.canvas,
                    notes_data=notes_data,
                    instrument=state.current_instrument,
                    project_data=project_data
                )
                
                if work_info:
                    emit('painting_saved', {'path': path, 'work_id': work_info['id']})
                else:
                    emit('painting_saved', {'path': path})
            except Exception as e:
                logger.error(f"保存到作品库失败: {e}")
                emit('painting_saved', {'path': path})


@socketio.on('export_audio')
def on_export_audio():
    """导出音频"""
    if state.music_engine and state.music_engine.recorded_notes:
        path = state.music_engine.export_audio()
        if path:
            emit('audio_exported', {'path': path})
        else:
            emit('error', {'message': '音频导出失败'})
    else:
        emit('error', {'message': '没有可导出的音频数据'})


# Master 回放控制

def on_sequencer_note_play(event):
    """Sequencer 播放音符时的回调"""
    # 计算音符名称
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (event.note // 12) - 1
    note_name = f"{note_names[event.note % 12]}{octave}"
    
    socketio.emit('master_note', {
        'note': event.note,
        'note_name': note_name,
        'x': event.x,
        'y': event.y,
        'velocity': event.velocity,
        'instrument': event.instrument
    })


def on_sequencer_scan_position(x):
    """Sequencer 扫描位置更新时的回调"""
    progress = (x / state.sequencer.scan_width * 100) if state.sequencer else 0
    socketio.emit('master_scan', {
        'position': x,
        'progress': progress,
        'current_time': state.sequencer.current_time if state.sequencer else 0
    })


def on_sequencer_end():
    """Sequencer 回放结束时的回调"""
    state.master_playing = False
    socketio.emit('master_ended', {})


@socketio.on('master_start')
def on_master_start(data=None):
    """开始 Master 回放"""
    # 调试信息
    logger.info(f"收到 master_start 请求，数据: {data}")
    
    # 检查系统状态
    if not state.sequencer or not state.canvas_manager:
        emit('error', {'message': '系统未初始化'})
        return
    
    # 检查 Sequencer 是否有项目数据
    if state.sequencer.project is None:
        logger.warning("Sequencer 项目为空，尝试从 CanvasManager 同步")
        
        # 尝试从 CanvasManager 获取项目
        project = state.canvas_manager.get_project()
        if project and len(project.strokes) > 0:
            state.sequencer.set_project(project)
            logger.info(f"从 CanvasManager 同步项目到 Sequencer: {len(project.strokes)} 笔画")
        else:
            emit('error', {'message': '没有可回放的内容，请先绘制或加载示例'})
            return
    
    # 设置回放模式
    mode = PlaybackMode.SCAN
    if data and data.get('mode') == 'timeline':
        mode = PlaybackMode.TIMELINE
    
    # 设置 BPM
    if data and 'bpm' in data:
        bpm_value = int(data['bpm'])
        state.sequencer.bpm = max(60, min(200, bpm_value))
    
    # 结束当前绘制（如果正在绘制）
    if state.is_drawing:
        state.is_drawing = False
        state.canvas_manager.end_stroke()
    
    # 准备回放
    state.sequencer.mode = mode
    state.sequencer.prepare_playback()
    
    # 记录调试信息
    logger.info(f"准备 Master 回放 - 模式: {mode.value}, BPM: {state.sequencer.bpm}")
    logger.info(f"事件数量: {len(state.sequencer.events)}, 项目笔画: {len(state.sequencer.project.strokes) if state.sequencer.project else 0}")
    
    # 开始回放
    state.sequencer.start()
    state.master_playing = True
    
    # 广播给所有客户端
    socketio.emit('master_started', {
        'mode': mode.value,
        'bpm': state.sequencer.bpm,
        'total_events': len(state.sequencer.events),
        'stroke_count': len(state.sequencer.project.strokes) if state.sequencer.project else 0,
        'duration': state.sequencer.project.duration if state.sequencer.project else 0
    })

@socketio.on('master_pause')
def on_master_pause():
    """暂停/继续 Master 回放"""
    if state.sequencer:
        state.sequencer.pause()
        emit('master_paused', {'paused': state.sequencer.is_paused})


@socketio.on('master_stop')
def on_master_stop():
    """停止 Master 回放"""
    if state.sequencer:
        state.sequencer.stop()
        state.master_playing = False
        emit('master_stopped', {})


@socketio.on('set_bpm')
def on_set_bpm(data):
    """设置 BPM"""
    if data and 'bpm' in data:
        bpm = max(60, min(200, data['bpm']))
        if state.sequencer:
            state.sequencer.bpm = bpm
        if state.canvas_manager:
            state.canvas_manager.project.bpm = bpm
        emit('bpm_changed', {'bpm': bpm})


@socketio.on('get_project_info')
def on_get_project_info():
    """获取项目信息"""
    if not state.canvas_manager:
        emit('project_info', {
            'stroke_count': 0,
            'duration': 0,
            'bpm': 120,
            'scale': 'pentatonic',
            'name': '无项目'
        })
        return
    
    project = state.canvas_manager.get_project()
    if project:
        emit('project_info', {
            'stroke_count': len(project.strokes),
            'duration': round(project.duration, 2),
            'bpm': project.bpm,
            'scale': project.scale,
            'name': project.name
        })
    else:
        emit('project_info', {
            'stroke_count': 0,
            'duration': 0,
            'bpm': 120,
            'scale': 'pentatonic',
            'name': '无项目'
        })


# 音乐性增强控制

@socketio.on('toggle_drum')
def on_toggle_drum():
    """切换鼓点"""
    if state.music_engine:
        state.music_engine.drum_enabled = not state.music_engine.drum_enabled
        emit('drum_toggled', {'enabled': state.music_engine.drum_enabled})


@socketio.on('toggle_bass')
def on_toggle_bass():
    """切换低音"""
    if state.music_engine:
        state.music_engine.bass_enabled = not state.music_engine.bass_enabled
        emit('bass_toggled', {'enabled': state.music_engine.bass_enabled})


@socketio.on('toggle_chord')
def on_toggle_chord():
    """切换和弦"""
    if state.music_engine:
        state.music_engine.chord_enabled = not state.music_engine.chord_enabled
        emit('chord_toggled', {'enabled': state.music_engine.chord_enabled})


@socketio.on('set_drum_pattern')
def on_set_drum_pattern(data):
    """设置鼓点模式"""
    if state.music_engine and data and 'pattern' in data:
        pattern = data['pattern']
        if pattern in state.music_engine.drum_patterns:
            state.music_engine.current_drum_pattern = pattern
            emit('drum_pattern_changed', {'pattern': pattern})


@socketio.on('toggle_metronome')
def on_toggle_metronome():
    """切换节拍器"""
    if state.music_engine:
        state.music_engine.metronome_enabled = not state.music_engine.metronome_enabled
        emit('metronome_toggled', {'enabled': state.music_engine.metronome_enabled})


@socketio.on('set_metronome_volume')
def on_set_metronome_volume(data):
    """设置节拍器音量"""
    if state.music_engine and data and 'volume' in data:
        state.music_engine.set_metronome_volume(data['volume'])


@socketio.on('set_accompaniment_level')
def on_set_accompaniment_level(data):
    """设置伴奏强度"""
    if state.music_engine and data and 'level' in data:
        level = data['level']
        state.music_engine.set_accompaniment_level(level)
        emit('accompaniment_level_changed', {'level': level})


@socketio.on('load_project')
def on_load_project(data):
    """加载作品项目用于回放"""
    if not data or 'work_id' not in data:
        emit('error', {'message': '缺少作品 ID'})
        return
    
    work_id = data['work_id']
    gallery = get_gallery()
    
    # 获取项目数据
    project_data = gallery.get_project_data(work_id)
    if not project_data:
        emit('error', {'message': f'找不到作品数据: {work_id}'})
        return
    
    try:
        from project_model import Project
        project = Project.from_dict(project_data)
        
        logger.info(f"正在加载作品: {work_id} - {project.name}")
        
        # === 重要修复：同步到画布管理器 ===
        if state.canvas_manager:
            state.canvas_manager.save_state()
            state.canvas_manager.clear_all()
            state.canvas_manager.project = project
            draw_example_on_canvas(project)  # 重用同一个绘制函数
            
            logger.info(f"作品已加载到画布: {work_id}, {len(project.strokes)} 笔画")
        
        # 导入到 Sequencer
        if state.sequencer:
            state.sequencer.set_project(project)
            
            emit('project_loaded', {
                'work_id': work_id,
                'name': project.name,
                'stroke_count': len(project.strokes),
                'duration': round(project.duration, 2),
                'bpm': project.bpm,
                'scale': project.scale,
                'canvas_loaded': True  # 新增标志
            })
            
            # 通知前端更新项目信息
            socketio.emit('project_info', {
                'stroke_count': len(project.strokes),
                'duration': round(project.duration, 2),
                'bpm': project.bpm,
                'scale': project.scale,
                'name': project.name,
                'source': 'gallery',
                'source_id': work_id
            })
            
            logger.info(f"作品已同步到音序器: {work_id}")
            
    except Exception as e:
        logger.error(f"加载作品失败: {e}", exc_info=True)
        emit('error', {'message': f'加载作品失败: {str(e)}'})

def draw_example_on_canvas(project):
    """
    将示例项目的笔画绘制到当前画布并导入到 CanvasManager
    
    Args:
        project: Project 对象
    """
    if not state.canvas_manager:
        return
    
    logger.info(f"开始绘制示例到画布: {project.name}")
    
    # 获取画布尺寸
    height, width = state.canvas_manager.canvas.shape[:2]
    
    # 重要：清空 CanvasManager 的项目数据
    state.canvas_manager.project.clear()
    state.canvas_manager.project = project  # 设置为新的项目
    
    # 重置画布
    state.canvas_manager.canvas = np.zeros((height, width, 3), np.uint8)
    state.canvas_manager.glow_layer = np.zeros((height, width, 3), np.uint8)
    state.canvas_manager.glow_layer = np.zeros((height, width, 3), np.uint8)
    
    # 清空粒子系统
    state.canvas_manager.particle_system.clear()
    state.canvas_manager.melody_trail.clear()
    
    # 绘制所有笔画
    for stroke_idx, stroke in enumerate(project.strokes):
        if len(stroke.points) < 2:
            continue
        
        # 获取颜色 - 处理不同的颜色格式
        if isinstance(stroke.color, list):
            color_list = stroke.color
            if len(color_list) == 3:
                # OpenCV 使用 BGR 格式，所以需要转换
                bgr_color = (color_list[2], color_list[1], color_list[0])
            else:
                bgr_color = (255, 200, 100)  # 默认钢琴色
        elif isinstance(stroke.color, tuple):
            bgr_color = stroke.color
        else:
            from config import INSTRUMENTS
            inst_color = INSTRUMENTS.get(stroke.instrument, INSTRUMENTS['piano'])['color']
            bgr_color = inst_color
        
        logger.debug(f"绘制笔画 {stroke_idx}: {stroke.instrument}, 颜色: {bgr_color}, 点数: {len(stroke.points)}")
        
        # 绘制线条
        for i in range(1, len(stroke.points)):
            p1 = stroke.points[i-1]
            p2 = stroke.points[i]
            pt1 = (int(p1.x), int(p1.y))
            pt2 = (int(p2.x), int(p2.y))
            
            # 厚度
            thickness = max(3, min(30, int(p1.thickness)))
            
            # 在主画布绘制
            cv2.line(state.canvas_manager.canvas, pt1, pt2, bgr_color, thickness, cv2.LINE_AA)
            
            # 添加发光效果
            glow_color = tuple(min(255, int(c * 0.5)) for c in bgr_color)
            cv2.line(state.canvas_manager.glow_layer, pt1, pt2, glow_color, thickness + 6, cv2.LINE_AA)
            
            # 外发光
            outer_glow = tuple(min(255, int(c * 0.25)) for c in bgr_color)
            cv2.line(state.canvas_manager.glow_layer, pt1, pt2, outer_glow, thickness + 12, cv2.LINE_AA)
    
    logger.info(f"示例绘制完成: {project.name}, {len(project.strokes)} 笔画")
    
    # 验证数据同步
    current_strokes = len(state.canvas_manager.project.strokes)
    logger.info(f"CanvasManager 当前笔画数: {current_strokes}")

@socketio.on('load_example')
def on_load_example(data):
    """加载示例项目用于回放"""
    if not data or 'example_id' not in data:
        emit('error', {'message': '缺少示例 ID'})
        return
    
    example_id = data['example_id']
    examples_dir = os.path.join(os.path.dirname(__file__), 'examples')
    filepath = os.path.join(examples_dir, f'{example_id}.json')
    
    if not os.path.exists(filepath):
        emit('error', {'message': f'示例不存在: {example_id}'})
        return
    
    try:
        # 加载示例数据
        with open(filepath, 'r', encoding='utf-8') as f:
            project_data = json.load(f)
        
        from project_model import Project
        project = Project.from_dict(project_data)
        
        logger.info(f"正在加载示例: {project.name} (ID: {example_id})")
        
        # === 重要：直接替换整个项目 ===
        if state.canvas_manager:
            # 保存当前状态到历史记录
            state.canvas_manager.save_state()
            
            # 清空当前画布
            state.canvas_manager.clear_all()
            
            # 关键：直接替换项目对象
            state.canvas_manager.project = project
            
            # 重新开始项目（重置时间）
            state.canvas_manager.start_project()
            
            # 将笔画重新添加到项目中（确保数据正确）
            for stroke in project.strokes:
                state.canvas_manager.project.add_stroke(stroke)
            
            # 在画布上绘制
            draw_example_on_canvas(project)
            
            logger.info(f"示例已完全加载到 CanvasManager: {len(project.strokes)} 笔画")
        
        # 同步到 Sequencer
        if state.sequencer:
            state.sequencer.set_project(project)
            
            logger.info(f"示例已同步到 Sequencer: {len(project.strokes)} 笔画")
        
        # 发送事件
        emit('project_loaded', {
            'example_id': example_id,
            'name': project.name,
            'stroke_count': len(project.strokes),
            'duration': round(project.duration, 2),
            'bpm': project.bpm,
            'scale': project.scale,
            'loaded': True
        })
        
        # 广播项目信息
        socketio.emit('project_info', {
            'stroke_count': len(project.strokes),
            'duration': round(project.duration, 2),
            'bpm': project.bpm,
            'scale': project.scale,
            'name': project.name,
            'source': 'example',
            'source_id': example_id
        })
        
        logger.info(f"示例加载完成: {project.name}")
        
    except Exception as e:
        logger.error(f"加载示例失败: {e}", exc_info=True)
        emit('error', {'message': f'加载示例失败: {str(e)}'})

# 主函数

def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("Gesture Music Paint - Web Server")
    logger.info("=" * 50)
    logger.info("启动服务器: http://localhost:5000")
    logger.info("按 Ctrl+C 停止服务器")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    main()
