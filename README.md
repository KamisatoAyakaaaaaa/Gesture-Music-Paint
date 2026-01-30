# 手势音乐画板 (Gesture Music Paint) 项目

## 1. 选题背景与实用性

### 1.1 选题背景

传统的音乐创作工具（如 DAW、MIDI 键盘）存在较高的学习门槛，限制了普通用户的音乐表达能力。同时，随着计算机视觉技术的成熟，基于手势的人机交互已成为研究热点。

本项目旨在探索一种**零门槛、沉浸式**的音乐创作方式：用户仅需通过摄像头，以自然的手势"绘画"动作，即可实时生成音乐作品。这种交互方式将视觉艺术（绘画轨迹）与听觉艺术（音乐旋律）有机融合，降低了音乐创作的技术壁垒。

### 1.2 应用场景

| 场景 | 描述 |
|------|------|
| **音乐教育** | 帮助儿童和音乐初学者理解音高、节奏等概念，通过可视化反馈建立音乐直觉 |
| **艺术创作** | 为艺术家提供跨媒介创作工具，实现"一笔一音"的同步创作体验 |
| **康复辅助** | 作为手部运动康复的辅助工具，通过音乐反馈激励患者进行手部锻炼 |
| **互动装置** | 可部署于博物馆、展览馆，作为沉浸式互动装置吸引观众参与 |
| **娱乐体验** | 无需专业设备，普通用户即可进行创意音乐创作 |

### 1.3 实用价值

- **低门槛**：无需任何专业设备（仅需摄像头），无需音乐理论知识
- **即时反馈**：绘画动作实时映射为音符，所画即所听
- **作品保存**：支持保存画作（PNG）、导出项目数据（JSON），便于分享与二次编辑
- **教育意义**：通过空间-音乐映射，直观理解音高与位置、时值与运动的关系

---

## 2. 系统需求分析

### 2.1 功能需求

| 功能模块 | 需求描述 | 优先级 |
|---------|---------|-------|
| 手势识别 | 实时检测食指、双指、握拳、张开手掌等手势 | P0 |
| 实时绘画 | 根据食指指尖位置绘制轨迹，支持多种颜色/粗细 | P0 |
| 音符生成 | 将绘画坐标映射为 MIDI 音符，实时播放 | P0 |
| 乐器切换 | 支持钢琴、吉他、鼓、合成器、弦乐等音色 | P1 |
| 作品保存 | 保存画作图片、导出项目 JSON 数据 | P1 |
| 作品库 | 管理已保存的作品，支持预览与加载回放 | P1 |
| Master 回放 | 加载项目后完整回放绘画+音乐 | P2 |
| 节拍器 | 提供 BPM 同步的节拍提示音 | P2 |
| 伴奏系统 | 自动生成鼓点、低音、和弦伴奏 | P2 |

### 2.2 非功能需求

| 需求类型 | 指标 |
|---------|------|
| **延迟** | 手势到画面反馈 < 100ms，音符触发延迟 < 50ms |
| **帧率** | 视频流 ≥ 20 FPS |
| **兼容性** | 支持 Windows/macOS/Linux，Chrome/Firefox/Edge 浏览器 |
| **可用性** | 无需安装额外硬件，普通摄像头即可使用 |

---

## 3. 系统架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                           客户端 (Browser)                          │
├─────────────────────────────────────────────────────────────────────┤
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│   │   视频显示   │    │   控制面板   │    │   作品库    │            │
│   │  (MJPEG)    │    │  (WebSocket) │    │  (Gallery)  │            │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘            │
│          │                  │                  │                    │
│          └──────────────────┴──────────────────┘                    │
│                             │ Socket.IO                             │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                    服务端 (Flask + SocketIO)                         │
├─────────────────────────────┼───────────────────────────────────────┤
│                      ┌──────┴──────┐                                │
│                      │  WebServer  │                                │
│                      │  (路由调度)  │                                │
│                      └──────┬──────┘                                │
│         ┌───────────────────┼───────────────────┐                   │
│         │                   │                   │                   │
│   ┌─────┴─────┐       ┌─────┴─────┐       ┌─────┴─────┐            │
│   │  Hand     │       │  Canvas   │       │  Music    │            │
│   │  Detector │       │  Manager  │       │  Engine   │            │
│   │ (MediaPipe)│       │ (OpenCV)  │       │ (Pygame)  │            │
│   └─────┬─────┘       └─────┬─────┘       └─────┬─────┘            │
│         │                   │                   │                   │
│   ┌─────┴─────┐       ┌─────┴─────┐       ┌─────┴─────┐            │
│   │ Gesture   │       │ Project   │       │ Sequencer │            │
│   │ Analysis  │       │  Model    │       │ (回放引擎) │            │
│   └───────────┘       └───────────┘       └───────────┘            │
│                                                                     │
│   ┌───────────────────────────────────────────────────────────────┐ │
│   │  辅助模块: SettingsManager | GalleryManager | Config          │ │
│   └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| **WebServer** | `web_server.py` | Flask 路由、Socket.IO 事件处理、视频流、状态管理 |
| **HandDetector** | `hand_detector.py` | MediaPipe 手势检测、21 点关键点提取、手势分类 |
| **CanvasManager** | `canvas_manager.py` | 多层画布渲染、粒子特效、撤销/重做栈 |
| **MusicEngine** | `music_engine.py` | ADSR 音频合成、乐器音色、鼓点/低音/和弦伴奏 |
| **ProjectModel** | `project_model.py` | Point/Stroke/Project 数据结构、JSON 序列化 |
| **Sequencer** | `sequencer.py` | 时间轴回放、扫描线模式、事件调度 |
| **SettingsManager** | `settings_manager.py` | 用户设置持久化 (JSON) |
| **GalleryManager** | `gallery_manager.py` | 作品库 CRUD、缩略图管理 |
| **Config** | `config.py` | 全局配置、映射函数、常量定义 |

### 3.3 数据流

```
摄像头帧 → HandDetector → 手势类型 + 坐标
                              ↓
                        WebServer (handle_gesture)
                              ↓
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
        CanvasManager    MusicEngine    ProjectModel
         (绘制轨迹)      (播放音符)     (记录数据)
              ↓               ↓               ↓
        合成帧 → MJPEG 推送给客户端
                       音频 → 服务端播放
                       项目数据 → 保存/回放
```

---

## 4. 核心算法说明

### 4.1 手势识别算法

**基于 MediaPipe Hands 的手势分类**

MediaPipe Hands 模型输出 21 个手部关键点的 3D 坐标：

```
         8 (INDEX_TIP)
         |
    7    |    12 (MIDDLE_TIP)
    |    |    |
    6    |    11
    |    |    |
    5----4----10---9----16---17---20 (PINKY_TIP)
              |        |    |
              |        15   19
              |        |    |
              3        14   18
              |        |
              2        13
              |
              1
              |
              0 (WRIST)
```

**手势判定逻辑**：

```python
def classify_gesture(landmarks):
    """基于关键点相对位置判定手势类型"""
    
    # 提取关键点
    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    middle_tip = landmarks[12]
    ring_tip = landmarks[16]
    pinky_tip = landmarks[20]
    
    index_mcp = landmarks[5]
    middle_mcp = landmarks[9]
    ring_mcp = landmarks[13]
    pinky_mcp = landmarks[17]
    
    # 判断各手指是否伸直（指尖高于 MCP 关节）
    index_up = index_tip.y < index_mcp.y
    middle_up = middle_tip.y < middle_mcp.y
    ring_up = ring_tip.y < ring_mcp.y
    pinky_up = pinky_tip.y < pinky_mcp.y
    
    # 手势分类
    if index_up and not middle_up and not ring_up and not pinky_up:
        return GestureType.INDEX_UP        # 食指伸出 → 绘画
    elif index_up and middle_up and not ring_up and not pinky_up:
        return GestureType.PEACE           # 双指 → 选择/录制
    elif not index_up and not middle_up and not ring_up and not pinky_up:
        return GestureType.FIST            # 握拳 → 播放/暂停
    elif index_up and middle_up and ring_up and pinky_up:
        return GestureType.OPEN_PALM       # 张开手掌 → 切换乐器
    else:
        return GestureType.UNKNOWN
```

### 4.2 空间-音乐映射算法

**核心映射公式**：

| 物理量 | 画布属性 | 音乐属性 | 映射方式 |
|--------|---------|---------|---------|
| X 坐标 | 水平位置 | 音高 (MIDI Note) | 线性映射 + 音阶量化 |
| Y 坐标 | 垂直位置 | 时值 (Duration) | 反向线性映射 |
| 画笔粗细 | 线宽 | 音量 (Velocity) | 线性映射 |

**X → 音高映射**：

```python
def map_x_to_note(x: int, width: int = 640) -> int:
    """X 坐标映射到 MIDI 音符 (C3=48 到 C6=84)"""
    MIN_NOTE, MAX_NOTE = 48, 84  # 3 个八度
    note = int(MIN_NOTE + (x / width) * (MAX_NOTE - MIN_NOTE))
    return max(MIN_NOTE, min(MAX_NOTE, note))
```

**音阶量化**（确保和谐性）：

```python
SCALES = {
    'pentatonic': [0, 2, 4, 7, 9],      # 五声音阶
    'major': [0, 2, 4, 5, 7, 9, 11],    # 大调音阶
}

def quantize_to_scale(note: int, scale: str = 'pentatonic') -> int:
    """将任意音符量化到指定音阶"""
    intervals = SCALES[scale]
    octave = note // 12
    pitch_class = note % 12
    
    # 找到最近的音阶内音符
    closest = min(intervals, key=lambda x: abs(x - pitch_class))
    return octave * 12 + closest
```

### 4.3 音频合成算法

**ADSR 包络生成**：

```
音量 ^
     |    /\
     |   /  \________
     |  /            \
     | /              \
     +-------------------> 时间
       A   D    S    R

A = Attack  (起音，音量上升)
D = Decay   (衰减，音量下降到持续电平)
S = Sustain (持续，稳定音量)
R = Release (释放，音量归零)
```

```python
def generate_adsr_envelope(duration: float, sample_rate: int = 44100) -> np.ndarray:
    """生成 ADSR 包络曲线"""
    total_samples = int(duration * sample_rate)
    
    # 时间参数 (秒)
    attack = 0.01
    decay = 0.1
    sustain_level = 0.7
    release = 0.1
    
    # 计算各阶段采样数
    attack_samples = int(attack * sample_rate)
    decay_samples = int(decay * sample_rate)
    release_samples = int(release * sample_rate)
    sustain_samples = total_samples - attack_samples - decay_samples - release_samples
    
    # 构建包络
    envelope = np.concatenate([
        np.linspace(0, 1, attack_samples),                      # Attack
        np.linspace(1, sustain_level, decay_samples),           # Decay
        np.full(sustain_samples, sustain_level),                # Sustain
        np.linspace(sustain_level, 0, release_samples)          # Release
    ])
    
    return envelope[:total_samples]
```

**波形合成**：

```python
def generate_note(frequency: float, duration: float, waveform: str = 'sine') -> np.ndarray:
    """生成指定频率和波形的音符"""
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    if waveform == 'sine':
        wave = np.sin(2 * np.pi * frequency * t)
    elif waveform == 'square':
        wave = np.sign(np.sin(2 * np.pi * frequency * t))
    elif waveform == 'sawtooth':
        wave = 2 * (t * frequency - np.floor(0.5 + t * frequency))
    elif waveform == 'triangle':
        wave = 2 * np.abs(2 * (t * frequency - np.floor(t * frequency + 0.5))) - 1
    
    # 应用 ADSR 包络
    envelope = generate_adsr_envelope(duration, sample_rate)
    return (wave * envelope * 32767).astype(np.int16)
```

---

## 5. 工程实践

### 5.1 代码组织

```
Project/
├── web_server.py          # 主服务 (Flask + SocketIO)
├── hand_detector.py       # 手势检测模块
├── canvas_manager.py      # 画布渲染模块
├── music_engine.py        # 音频合成模块
├── project_model.py       # 数据模型
├── sequencer.py           # 回放引擎
├── settings_manager.py    # 设置管理
├── gallery_manager.py     # 作品库管理
├── config.py              # 全局配置
│
├── templates/             # HTML 模板
│   ├── landing.html       # 首页
│   ├── index.html         # 应用主界面
│   └── gallery.html       # 作品库页面
│
├── static/                # 静态资源
│   ├── css/style.css
│   └── js/app.js
│
├── tests/                 # 单元测试
│   ├── test_project_model.py
│   ├── test_config.py
│   └── test_settings_manager.py
│
├── examples/              # 示例项目
│   └── demo_melody.json
│
├── requirements.txt       # 生产依赖
├── requirements-dev.txt   # 开发依赖
├── pyproject.toml         # 工具配置
└── README.md              # 项目说明
```

### 5.2 代码规范

- **类型注解**：所有函数使用 Python Type Hints
- **日志系统**：使用 `logging` 模块，按模块命名（如 `GesturePaint.Canvas`）
- **配置管理**：敏感配置通过环境变量注入（如 `FLASK_SECRET_KEY`）
- **代码格式**：使用 Black 格式化，Ruff 静态检查

### 5.3 测试覆盖

| 测试文件 | 测试内容 | 用例数 |
|---------|---------|-------|
| `test_project_model.py` | Point/Stroke/Project 数据结构、序列化、量化函数 | 16 |
| `test_config.py` | 坐标-音符映射、音阶量化、参数边界 | 9 |
| `test_settings_manager.py` | 设置默认值、持久化读写 | 3 |
| **合计** | | **28** |

运行测试：

```bash
python -m pytest tests/ -v
```

### 5.4 依赖管理

**生产依赖** (`requirements.txt`)：

| 包 | 版本 | 用途 |
|----|------|------|
| Flask | ≥3.0.0 | Web 框架 |
| Flask-SocketIO | ≥5.3.0 | WebSocket 支持 |
| opencv-python | ≥4.8.0 | 图像处理 |
| mediapipe | ≥0.10.0 | 手势识别 |
| pygame | ≥2.5.0 | 音频合成 |
| numpy | ≥1.24.0 | 数值计算 |
| Pillow | ≥10.0.0 | 图像导出 |
---

## 6. 性能评测

### 6.1 测试环境

| 项目 | 配置 |
|------|------|
| CPU | Intel Core i5-10400 / Apple M1 |
| RAM | 16 GB |
| 摄像头 | 720p @ 30fps |
| 浏览器 | Chrome 120 |

### 6.2 延迟测试

| 指标 | 目标 | 实测值 | 状态 |
|------|------|-------|------|
| 手势检测延迟 | < 50ms | ~30ms | ✅ |
| 画面渲染延迟 | < 100ms | ~80ms | ✅ |
| 音符触发延迟 | < 50ms | ~20ms | ✅ |
| 端到端延迟 | < 150ms | ~130ms | ✅ |

### 6.3 帧率测试

| 场景 | 目标 | 实测值 |
|------|------|-------|
| 空闲状态 | ≥25 FPS | 28-30 FPS |
| 绘画中（单笔画） | ≥20 FPS | 24-26 FPS |
| 绘画中（复杂画布） | ≥15 FPS | 18-22 FPS |
| 回放中 | ≥20 FPS | 22-25 FPS |

### 6.4 资源占用

| 指标 | 空闲 | 运行中 |
|------|------|-------|
| CPU 占用 | ~5% | 15-25% |
| 内存占用 | ~150 MB | ~250 MB |
| GPU 占用 (如有) | ~10% | 20-30% |

---



## 附录 A：快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python web_server.py

# 访问应用
# 打开浏览器访问 http://localhost:5000
```

## 附录 B：手势速查表

| 手势 | 图示 | 功能 |
|------|------|------|
| 食指伸出 | ☝️ | 绘画模式 |
| 双指 | ✌️ | 选择/录制 |
| 握拳 | ✊ | 播放/暂停 |
| 张开手掌 | 🖐️ | 切换乐器 |

---


