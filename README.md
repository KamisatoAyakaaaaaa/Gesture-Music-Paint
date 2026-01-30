# Gesture Music Paint

**用手势创作音乐绘画的交互式应用**

通过摄像头捕捉手势，在空中绘画的同时生成音乐。绘画即作曲，让视觉艺术与听觉艺术完美融合。

## 功能特点

### 核心功能
- **手势绘画**：伸出食指在空中绘制，实时显示轨迹
- **音乐生成**：绘画位置自动映射为音符（X轴=音高，Y轴=时值）
- **多种乐器**：钢琴、吉他、鼓、合成器、弦乐，五指张开切换

### 手势控制
- ☝️ 食指伸出 → 绘画模式
- ✊ 握拳 → 播放/暂停
- ✌️ 比耶 → 开始/停止录制
- 🖐️ 五指张开 → 切换乐器

### 混合音乐模式
- **实时预览**：绘画时即时反馈音符（带时间+距离阈值控制）
- **Master 回放**：完成绘画后，扫描式从左到右回放整个作品

### 音乐增强（可开关）
- **鼓点**：自动节拍伴奏（基础四拍/摇滚/踩镲）
- **低音**：跟随音阶根音自动生成
- **和弦**：大三和弦（根音+三度+五度）

### 作品管理
- 保存画作（PNG）+ 乐谱数据（JSON）
- 作品库支持加载回放
- 导出音频文件

### 界面
- **Web 界面**：现代化响应式设计，支持浏览器访问
- **性能指标**：实时显示 FPS 和检测耗时

## 系统要求

- Python 3.9+
- 摄像头（内置或外接）
- Windows / macOS / Linux

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 下载手势识别模型

下载 `hand_landmarker.task` 文件并放置在项目根目录：

[MediaPipe Hand Landmarker 模型下载](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker#models)

### 3. 启动应用

**Web 版本（推荐）**：
```bash
python web_server.py
```
然后访问 http://localhost:5000

**桌面 GUI 版本**：
```bash
python gui_app.py
```

**或使用启动脚本**：
- Windows: 双击 `start_web.bat` 或 `start_gui.bat`

## 项目结构

```
Project/
├── web_server.py        # Web 服务器入口
├── gui_app.py           # 桌面 GUI 入口
├── config.py            # 配置参数
├── hand_detector.py     # 手势检测模块
├── music_engine.py      # 音乐生成引擎（含鼓/低音/和弦增强）
├── canvas_manager.py    # 画布管理器（含笔画记录）
├── gallery_manager.py   # 作品库管理
├── settings_manager.py  # 设置持久化
├── project_model.py     # 乐谱数据模型（Project/Stroke/Point）
├── sequencer.py         # Master 回放音序器
├── templates/           # HTML 模板
│   ├── landing.html     # 首页（项目介绍）
│   ├── index.html       # 应用主界面
│   └── gallery.html     # 作品库页面
├── static/              # 静态资源
│   ├── css/
│   └── js/
├── Recordings/          # 录制文件
├── SavedPaintings/      # 保存的画作
├── Gallery/             # 作品库（含 project.json）
└── hand_landmarker.task # 手势识别模型
```

## 配置说明

编辑 `config.py` 可调整：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `CAMERA_WIDTH` | 640 | 摄像头宽度 |
| `CAMERA_HEIGHT` | 480 | 摄像头高度 |
| `CAMERA_INDEX` | 0 | 摄像头索引 |
| `DEFAULT_SCALE` | pentatonic | 默认音阶 |
| `BPM` | 120 | 节拍速度 |

## 技术栈

- **计算机视觉**：OpenCV
- **手势识别**：MediaPipe
- **音频合成**：Pygame
- **Web 框架**：Flask + Flask-SocketIO
- **前端**：原生 HTML/CSS/JavaScript



## 致谢

- [MediaPipe](https://github.com/google/mediapipe) - 手势识别
- [Pygame](https://www.pygame.org/) - 音频处理
- [Flask](https://flask.palletsprojects.com/) - Web 框架
