/**
 * Gesture Music Paint - Web Client
 * 前端控制脚本
 */

// 全局状态
const state = {
    isRunning: false,
    isPlaying: true,
    isRecording: false,
    isPaused: false,
    currentInstrument: 'piano',
    thickness: 10,
    instruments: [],
    thicknessOptions: []
};

// Socket.IO 连接
let socket = null;

// DOM 元素
const elements = {
    videoFeed: document.getElementById('video-feed'),
    videoPlaceholder: document.getElementById('video-placeholder'),
    startBtn: document.getElementById('start-btn'),
    playBtn: document.getElementById('play-btn'),
    pauseBtn: document.getElementById('pause-btn'),
    clearBtn: document.getElementById('clear-btn'),
    recordBtn: document.getElementById('record-btn'),
    saveBtn: document.getElementById('save-btn'),
    exportBtn: document.getElementById('export-btn'),
    undoBtn: document.getElementById('undo-btn'),
    redoBtn: document.getElementById('redo-btn'),
    instrumentList: document.getElementById('instrument-list'),
    thicknessSlider: document.getElementById('thickness-slider'),
    thicknessInfo: document.getElementById('thickness-info'),
    thicknessPresets: document.getElementById('thickness-presets'),
    playIndicator: document.getElementById('play-indicator'),
    recIndicator: document.getElementById('rec-indicator'),
    pauseIndicator: document.getElementById('pause-indicator'),
    currentNote: document.getElementById('current-note'),
    historyInfo: document.getElementById('history-info'),
    fpsValue: document.getElementById('fps-value'),
    connectionStatus: document.getElementById('connection-status'),
    toastContainer: document.getElementById('toast-container'),
    // 手势显示
    gestureDisplay: document.getElementById('gesture-display'),
    gestureIcon: document.getElementById('gesture-icon'),
    gestureName: document.getElementById('gesture-name'),
    // Master 回放控制
    masterPlayBtn: document.getElementById('master-play-btn'),
    masterPauseBtn: document.getElementById('master-pause-btn'),
    masterStopBtn: document.getElementById('master-stop-btn'),
    bpmSlider: document.getElementById('bpm-slider'),
    bpmValue: document.getElementById('bpm-value'),
    projectInfo: document.getElementById('project-info'),
    progressBar: document.getElementById('progress-bar'),
    playbackStatus: document.getElementById('playback-status'),
    scanLine: document.getElementById('scan-line'),
    playbackOverlay: document.getElementById('playback-overlay'),
    // 音乐增强
    drumToggle: document.getElementById('drum-toggle'),
    bassToggle: document.getElementById('bass-toggle'),
    chordToggle: document.getElementById('chord-toggle')
};

// 回放状态
const playbackState = {
    isPlaying: false,
    isPaused: false,
    mode: 'scan',
    progress: 0,
    scanPosition: 0
};

// 手势信息映射
const GESTURE_INFO = {
    'none': { icon: '✋', name: '等待手势', class: '' },
    'draw': { icon: '☝️', name: '绘制中', class: 'drawing' },
    'select': { icon: '✌️', name: '选择模式', class: 'active' },
    'fist': { icon: '✊', name: '握拳', class: 'active' },
    'peace': { icon: '✌️', name: '比耶', class: 'active' },
    'five': { icon: '🖐️', name: '五指张开', class: 'active' }
};

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
    // 加载乐器列表
    await loadInstruments();
    
    // 加载粗细选项
    await loadThicknessOptions();
    
    // 加载示例列表
    await loadExamples();
    
    // 初始化 WebSocket
    initSocket();
    
    // 绑定事件
    bindEvents();
    
    // 绑定键盘快捷键
    bindKeyboard();
    
    // 检查是否需要加载项目
    checkLoadProject();
});

// 加载示例列表
async function loadExamples() {
    const select = document.getElementById('example-select');
    if (!select) return;
    
    try {
        const response = await fetch('/api/examples');
        const examples = await response.json();
        
        examples.forEach(ex => {
            const option = document.createElement('option');
            option.value = ex.id;
            option.textContent = `${ex.name} (${ex.stroke_count}笔, ${ex.duration.toFixed(1)}s)`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('加载示例列表失败:', error);
    }
}

// 检查 URL 参数并加载项目
function checkLoadProject() {
    const urlParams = new URLSearchParams(window.location.search);
    const projectId = urlParams.get('load_project');
    
    if (projectId) {
        // 清除 URL 参数
        window.history.replaceState({}, document.title, window.location.pathname);
        
        // 等待 socket 连接后加载项目
        const checkSocket = setInterval(() => {
            if (socket && socket.connected) {
                clearInterval(checkSocket);
                loadProjectFromGallery(projectId);
            }
        }, 100);
    }
}

// 从作品库加载项目
async function loadProjectFromGallery(workId) {
    try {
        showToast('正在加载作品...', 'info');
        
        // 获取项目数据
        const response = await fetch(`/api/gallery/${workId}/project`);
        if (!response.ok) {
            showToast('无法加载项目数据', 'error');
            return;
        }
        
        // 发送到服务器加载
        socket.emit('load_project', { work_id: workId });
        
    } catch (error) {
        console.error('加载项目失败:', error);
        showToast('加载项目失败', 'error');
    }
}

// 加载乐器列表
async function loadInstruments() {
    try {
        const response = await fetch('/api/instruments');
        state.instruments = await response.json();
        renderInstruments();
    } catch (error) {
        console.error('加载乐器列表失败:', error);
    }
}

// 渲染乐器列表
function renderInstruments() {
    elements.instrumentList.innerHTML = state.instruments.map((inst, index) => `
        <div class="instrument-item ${inst.key === state.currentInstrument ? 'active' : ''}" 
             data-instrument="${inst.key}">
            <div class="instrument-color" style="background: ${inst.color}"></div>
            <span class="instrument-name">${inst.name}</span>
            <span class="instrument-name-en">(${inst.name_en})</span>
        </div>
    `).join('');
    
    // 绑定点击事件
    document.querySelectorAll('.instrument-item').forEach(item => {
        item.addEventListener('click', () => {
            const instrument = item.dataset.instrument;
            setInstrument(instrument);
        });
    });
}

// 加载粗细选项
async function loadThicknessOptions() {
    try {
        const response = await fetch('/api/thickness_options');
        state.thicknessOptions = await response.json();
        renderThicknessPresets();
    } catch (error) {
        console.error('加载粗细选项失败:', error);
    }
}

// 渲染粗细预设按钮
function renderThicknessPresets() {
    elements.thicknessPresets.innerHTML = state.thicknessOptions.map(t => `
        <button class="btn" data-thickness="${t}">${t}</button>
    `).join('');
    
    // 绑定点击事件
    document.querySelectorAll('.thickness-presets .btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const thickness = parseInt(btn.dataset.thickness);
            setThickness(thickness);
        });
    });
}

// 初始化 WebSocket
function initSocket() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('WebSocket 已连接');
        updateConnectionStatus(true);
    });
    
    socket.on('disconnect', () => {
        console.log('WebSocket 已断开');
        updateConnectionStatus(false);
        // 自动重连机制
        showToast('连接断开，正在重连...', 'warning');
        setTimeout(() => {
            if (!socket.connected) {
                socket.connect();
            }
        }, 2000);
    });
    
    socket.on('connected', (data) => {
        showToast('已连接到服务器', 'success');
        
        // 同步服务器状态
        if (data.system_running !== undefined) {
            state.isRunning = data.system_running;
            state.isPlaying = data.is_playing;
            state.isRecording = data.is_recording;
            state.isPaused = data.drawing_paused;
            state.currentInstrument = data.current_instrument || 'piano';
            updateUI();
            
            // 如果系统已运行，显示视频流
            if (state.isRunning) {
                elements.videoPlaceholder.style.display = 'none';
                elements.videoFeed.style.display = 'block';
                elements.videoFeed.src = '/video_feed';
            }
        }
    });
    
    socket.on('system_started', (data) => {
        state.isRunning = true;
        updateUI();
        showToast('系统已启动', 'success');
        
        // 显示视频流
        elements.videoPlaceholder.style.display = 'none';
        elements.videoFeed.style.display = 'block';
        elements.videoFeed.src = '/video_feed?' + new Date().getTime();
    });
    
    socket.on('system_stopped', (data) => {
        state.isRunning = false;
        updateUI();
        showToast('系统已停止', 'info');
        
        // 隐藏视频流
        elements.videoFeed.style.display = 'none';
        elements.videoPlaceholder.style.display = 'flex';
        elements.videoFeed.src = '';
    });
    
    socket.on('error', (data) => {
        showToast(data.message, 'error');
    });
    
    // 摄像头错误处理
    socket.on('camera_error', (data) => {
        showToast(data.message, 'error');
        // 显示详细建议
        if (data.suggestions && data.suggestions.length > 0) {
            const suggestionList = data.suggestions.map(s => `• ${s}`).join('\n');
            setTimeout(() => {
                alert(`摄像头问题\n\n${data.message}\n\n解决建议：\n${suggestionList}`);
            }, 500);
        }
        // 更新占位符显示错误状态
        const placeholder = document.getElementById('video-placeholder');
        if (placeholder) {
            placeholder.innerHTML = `
                <div class="placeholder-content error-state">
                    <span class="placeholder-icon">⚠️</span>
                    <h3>${data.message}</h3>
                    <p>请检查摄像头连接后重试</p>
                </div>
            `;
        }
    });
    
    socket.on('instrument_changed', (data) => {
        state.currentInstrument = data.instrument;
        updateInstrumentUI();
    });
    
    socket.on('thickness_changed', (data) => {
        state.thickness = data.thickness;
        updateThicknessUI();
    });
    
    socket.on('status_update', (data) => {
        if (data.is_playing !== undefined) {
            state.isPlaying = data.is_playing;
        }
        if (data.is_recording !== undefined) {
            state.isRecording = data.is_recording;
        }
        if (data.drawing_paused !== undefined) {
            state.isPaused = data.drawing_paused;
        }
        updateStatusIndicators();
    });
    
    socket.on('note_played', (data) => {
        elements.currentNote.textContent = data.note;
    });
    
    // 手势检测状态
    socket.on('gesture_detected', (data) => {
        updateGestureDisplay(data);
    });
    
    socket.on('history_update', (data) => {
        elements.historyInfo.textContent = `撤销: ${data.undo} | 重做: ${data.redo}`;
    });
    
    socket.on('canvas_cleared', () => {
        showToast('画布已清空', 'info');
    });
    
    // Master 回放事件
    socket.on('master_started', (data) => {
        playbackState.isPlaying = true;
        playbackState.isPaused = false;
        updatePlaybackUI();
        showToast(`回放开始 (${data.total_events} 个音符)`, 'success');
    });
    
    socket.on('master_paused', (data) => {
        playbackState.isPaused = data.paused;
        updatePlaybackUI();
    });
    
    socket.on('master_stopped', () => {
        playbackState.isPlaying = false;
        playbackState.isPaused = false;
        playbackState.progress = 0;
        playbackState.scanPosition = 0;
        updatePlaybackUI();
        showToast('回放停止', 'info');
    });
    
    socket.on('master_ended', () => {
        playbackState.isPlaying = false;
        playbackState.isPaused = false;
        playbackState.progress = 0;
        playbackState.scanPosition = 0;
        updatePlaybackUI();
        showToast('回放结束', 'info');
    });
    
    socket.on('master_scan', (data) => {
        // 更新扫描线位置
        playbackState.scanPosition = data.position;
        playbackState.progress = data.progress || (data.position / 640 * 100);
        updateScanLine(data.position);
        updateProgressBar(playbackState.progress);
    });
    
    socket.on('master_note', (data) => {
        // 可视化音符触发
        if (elements.currentNote) {
            elements.currentNote.textContent = data.note_name || data.note;
        }
    });
    
    socket.on('project_info', (data) => {
        if (elements.projectInfo) {
            elements.projectInfo.textContent = `笔画: ${data.stroke_count} | 时长: ${data.duration.toFixed(1)}s`;
        }
    });
    
    socket.on('project_loaded', (data) => {
        showToast(`作品已加载 (${data.stroke_count} 笔画)`, 'success');
        if (elements.projectInfo) {
            elements.projectInfo.textContent = `笔画: ${data.stroke_count} | 时长: ${data.duration.toFixed(1)}s`;
        }
        // 可以自动开始回放
        if (confirm('是否立即开始回放?')) {
            const mode = document.querySelector('input[name="playback-mode"]:checked')?.value || 'scan';
            socket.emit('master_start', { mode: mode, bpm: data.bpm || 120 });
        }
    });
    
    // 音乐增强事件
    socket.on('drum_toggled', (data) => {
        showToast(data.enabled ? '鼓点已开启' : '鼓点已关闭', 'info');
    });
    
    socket.on('bass_toggled', (data) => {
        showToast(data.enabled ? '低音已开启' : '低音已关闭', 'info');
    });
    
    socket.on('chord_toggled', (data) => {
        showToast(data.enabled ? '和弦已开启' : '和弦已关闭', 'info');
    });
    
    socket.on('metronome_toggled', (data) => {
        showToast(data.enabled ? '节拍器已开启' : '节拍器已关闭', 'info');
        const toggle = document.getElementById('metronome-toggle');
        if (toggle) toggle.checked = data.enabled;
    });
    
    socket.on('accompaniment_level_changed', (data) => {
        const labels = { 'off': '关闭', 'low': '轻伴奏', 'high': '重伴奏' };
        showToast(`伴奏强度: ${labels[data.level] || data.level}`, 'info');
    });
    
    // 性能指标
    socket.on('perf_metrics', (data) => {
        if (elements.fpsValue) {
            elements.fpsValue.textContent = data.fps;
        }
        const detectionMs = document.getElementById('detection-ms');
        if (detectionMs) {
            detectionMs.textContent = data.detection_ms;
        }
    });
    
    socket.on('recording_saved', (data) => {
        showToast('录制已保存', 'success');
    });
    
    socket.on('painting_saved', (data) => {
        showToast(`画作已保存: ${data.path}`, 'success');
    });
    
    socket.on('audio_exported', (data) => {
        showToast(`音频已导出: ${data.path}`, 'success');
    });
}

// 绑定事件
function bindEvents() {
    // 启动/停止按钮
    elements.startBtn.addEventListener('click', toggleSystem);
    
    // 播放按钮
    elements.playBtn.addEventListener('click', () => {
        socket.emit('toggle_play');
    });
    
    // 暂停按钮
    elements.pauseBtn.addEventListener('click', () => {
        socket.emit('toggle_pause');
    });
    
    // 清空按钮
    elements.clearBtn.addEventListener('click', () => {
        socket.emit('clear_canvas');
    });
    
    // 录制按钮
    elements.recordBtn.addEventListener('click', () => {
        socket.emit('toggle_recording');
    });
    
    // 保存按钮
    elements.saveBtn.addEventListener('click', () => {
        socket.emit('save_painting');
    });
    
    // 导出按钮
    elements.exportBtn.addEventListener('click', () => {
        socket.emit('export_audio');
    });
    
    // 撤销按钮
    elements.undoBtn.addEventListener('click', () => {
        socket.emit('undo');
    });
    
    // 重做按钮
    elements.redoBtn.addEventListener('click', () => {
        socket.emit('redo');
    });
    
    // 粗细滑块
    elements.thicknessSlider.addEventListener('input', (e) => {
        const thickness = parseInt(e.target.value);
        setThickness(thickness);
    });
    
    // Master 回放按钮
    if (elements.masterPlayBtn) {
        elements.masterPlayBtn.addEventListener('click', () => {
            if (playbackState.isPaused) {
                // 继续播放
                socket.emit('master_pause');
            } else {
                // 开始播放
                const mode = document.querySelector('input[name="playback-mode"]:checked')?.value || 'scan';
                playbackState.mode = mode;
                socket.emit('master_start', { mode: mode, bpm: state.bpm || 120 });
            }
        });
    }
    
    if (elements.masterPauseBtn) {
        elements.masterPauseBtn.addEventListener('click', () => {
            socket.emit('master_pause');
        });
    }
    
    if (elements.masterStopBtn) {
        elements.masterStopBtn.addEventListener('click', () => {
            socket.emit('master_stop');
        });
    }
    
    // 回放模式选择
    document.querySelectorAll('input[name="playback-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            playbackState.mode = e.target.value;
        });
    });
    
    // BPM 滑块
    if (elements.bpmSlider) {
        elements.bpmSlider.addEventListener('input', (e) => {
            const bpm = parseInt(e.target.value);
            state.bpm = bpm;
            if (elements.bpmValue) {
                elements.bpmValue.textContent = bpm;
            }
            socket.emit('set_bpm', { bpm });
        });
    }
    
    // 音乐增强开关
    if (elements.drumToggle) {
        elements.drumToggle.addEventListener('change', () => {
            socket.emit('toggle_drum');
        });
    }
    
    if (elements.bassToggle) {
        elements.bassToggle.addEventListener('change', () => {
            socket.emit('toggle_bass');
        });
    }
    
    if (elements.chordToggle) {
        elements.chordToggle.addEventListener('change', () => {
            socket.emit('toggle_chord');
        });
    }
    
    // 示例加载
    const loadExampleBtn = document.getElementById('load-example-btn');
    const exampleSelect = document.getElementById('example-select');
    
    if (loadExampleBtn && exampleSelect) {
        loadExampleBtn.addEventListener('click', () => {
            const exampleId = exampleSelect.value;
            if (exampleId) {
                socket.emit('load_example', { example_id: exampleId });
            } else {
                showToast('请先选择一个示例', 'warning');
            }
        });
    }
    
    // 节拍器
    const metronomeToggle = document.getElementById('metronome-toggle');
    if (metronomeToggle) {
        metronomeToggle.addEventListener('change', () => {
            socket.emit('toggle_metronome');
        });
    }
    
    // 伴奏强度
    document.querySelectorAll('.level-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const level = btn.dataset.level;
            socket.emit('set_accompaniment_level', { level });
            
            // 更新 UI
            document.querySelectorAll('.level-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
}

// 绑定键盘快捷键
function bindKeyboard() {
    document.addEventListener('keydown', (e) => {
        if (!state.isRunning) return;
        
        const key = e.key.toLowerCase();
        
        switch (key) {
            case ' ':
                e.preventDefault();
                socket.emit('toggle_play');
                break;
            case 'c':
                socket.emit('clear_canvas');
                break;
            case 'z':
                socket.emit('undo');
                break;
            case 'y':
                socket.emit('redo');
                break;
            case 's':
                socket.emit('save_painting');
                break;
            case 'r':
                socket.emit('toggle_recording');
                break;
            case 'e':
                socket.emit('export_audio');
                break;
            case 'p':
                socket.emit('toggle_pause');
                break;
            case '1':
            case '2':
            case '3':
            case '4':
            case '5':
                const index = parseInt(key) - 1;
                if (index < state.instruments.length) {
                    setInstrument(state.instruments[index].key);
                }
                break;
        }
    });
}

// 启动/停止系统
function toggleSystem() {
    if (state.isRunning) {
        socket.emit('stop_system');
    } else {
        socket.emit('start_system');
    }
}

// 设置乐器
function setInstrument(instrument) {
    state.currentInstrument = instrument;
    socket.emit('set_instrument', { instrument });
    updateInstrumentUI();
}

// 设置粗细
function setThickness(thickness) {
    state.thickness = thickness;
    socket.emit('set_thickness', { thickness });
    updateThicknessUI();
}

// 更新连接状态
function updateConnectionStatus(connected) {
    const dot = elements.connectionStatus.querySelector('.status-dot');
    const text = elements.connectionStatus.querySelector('span:last-child');
    
    if (connected) {
        dot.className = 'status-dot connected';
        text.textContent = '已连接';
    } else {
        dot.className = 'status-dot disconnected';
        text.textContent = '未连接';
    }
}

// 更新 UI
function updateUI() {
    const enabled = state.isRunning;
    
    // 更新按钮状态
    elements.startBtn.innerHTML = enabled 
        ? '<span class="btn-icon">■</span>停止系统' 
        : '<span class="btn-icon">▶</span>启动系统';
    elements.startBtn.className = enabled 
        ? 'btn btn-danger btn-large' 
        : 'btn btn-primary btn-large';
    
    elements.playBtn.disabled = !enabled;
    elements.pauseBtn.disabled = !enabled;
    elements.clearBtn.disabled = !enabled;
    elements.recordBtn.disabled = !enabled;
    elements.saveBtn.disabled = !enabled;
    elements.exportBtn.disabled = !enabled;
    elements.undoBtn.disabled = !enabled;
    elements.redoBtn.disabled = !enabled;
    
    // Master 回放按钮
    if (elements.masterPlayBtn) {
        elements.masterPlayBtn.disabled = !enabled;
    }
    if (elements.masterStopBtn) {
        elements.masterStopBtn.disabled = true; // 默认禁用，播放时启用
    }
    
    updateStatusIndicators();
}

// 更新状态指示器
function updateStatusIndicators() {
    // 播放状态
    const playDot = elements.playIndicator.querySelector('.indicator-dot');
    if (state.isPlaying) {
        elements.playIndicator.classList.add('active');
        playDot.classList.add('active');
    } else {
        elements.playIndicator.classList.remove('active');
        playDot.classList.remove('active');
    }
    elements.playBtn.textContent = state.isPlaying ? '暂停' : '播放';
    
    // 录制状态
    const recDot = elements.recIndicator.querySelector('.indicator-dot');
    if (state.isRecording) {
        elements.recIndicator.classList.add('recording');
        recDot.classList.add('recording');
        elements.recordBtn.innerHTML = '<span class="btn-icon">■</span>停止录制';
    } else {
        elements.recIndicator.classList.remove('recording');
        recDot.classList.remove('recording');
        elements.recordBtn.innerHTML = '<span class="btn-icon">●</span>开始录制';
    }
    
    // 暂停状态
    const pauseDot = elements.pauseIndicator.querySelector('.indicator-dot');
    if (state.isPaused) {
        elements.pauseIndicator.classList.add('paused');
        pauseDot.classList.add('paused');
        elements.pauseBtn.textContent = '继续';
    } else {
        elements.pauseIndicator.classList.remove('paused');
        pauseDot.classList.remove('paused');
        elements.pauseBtn.textContent = '暂停';
    }
}

// 更新回放 UI
function updatePlaybackUI() {
    const isPlaying = playbackState.isPlaying;
    const isPaused = playbackState.isPaused;
    
    // 按钮状态
    if (elements.masterPlayBtn) {
        elements.masterPlayBtn.disabled = isPlaying && !isPaused;
        elements.masterPlayBtn.innerHTML = isPaused 
            ? '<span class="btn-icon">▶</span> 继续'
            : '<span class="btn-icon">▶</span> 回放';
    }
    if (elements.masterPauseBtn) {
        elements.masterPauseBtn.disabled = !isPlaying;
    }
    if (elements.masterStopBtn) {
        elements.masterStopBtn.disabled = !isPlaying;
    }
    
    // 扫描线和覆盖层
    if (elements.scanLine) {
        elements.scanLine.classList.toggle('active', isPlaying && !isPaused);
    }
    if (elements.playbackOverlay) {
        elements.playbackOverlay.classList.toggle('active', isPlaying);
    }
    
    // 状态文字
    if (elements.playbackStatus) {
        if (isPlaying) {
            elements.playbackStatus.textContent = isPaused ? '已暂停' : '回放中...';
            elements.playbackStatus.className = 'playback-status' + (isPaused ? '' : ' playing');
        } else {
            elements.playbackStatus.textContent = '';
            elements.playbackStatus.className = 'playback-status';
        }
    }
    
    // 重置进度条
    if (!isPlaying) {
        updateProgressBar(0);
        updateScanLine(0);
    }
}

// 更新扫描线位置
function updateScanLine(position) {
    if (elements.scanLine && elements.videoFeed) {
        const containerWidth = elements.videoFeed.offsetWidth || 640;
        const percent = (position / 640) * 100;
        elements.scanLine.style.left = `${percent}%`;
    }
}

// 更新进度条
function updateProgressBar(percent) {
    if (elements.progressBar) {
        elements.progressBar.style.width = `${Math.min(100, percent)}%`;
    }
}

// 更新乐器 UI
function updateInstrumentUI() {
    document.querySelectorAll('.instrument-item').forEach(item => {
        if (item.dataset.instrument === state.currentInstrument) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}

// 更新粗细 UI
function updateThicknessUI() {
    elements.thicknessSlider.value = state.thickness;
    const volume = mapThicknessToVolume(state.thickness);
    elements.thicknessInfo.textContent = `粗细: ${state.thickness}px | 音量: ${volume}`;
}

// 粗细映射到音量
function mapThicknessToVolume(thickness) {
    const minThickness = 3;
    const maxThickness = 30;
    const minVolume = 30;
    const maxVolume = 127;
    
    const ratio = (thickness - minThickness) / (maxThickness - minThickness);
    return Math.round(minVolume + ratio * (maxVolume - minVolume));
}

// 显示 Toast 通知
function showToast(message, type = 'info') {
    const icons = {
        success: '✓',
        error: '✕',
        info: 'ℹ',
        warning: '⚠'
    };
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${message}</span>
    `;
    
    elements.toastContainer.appendChild(toast);
    
    // 3秒后移除
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 更新手势显示
function updateGestureDisplay(data) {
    if (!elements.gestureDisplay) return;
    
    const gesture = data.gesture || 'none';
    const info = GESTURE_INFO[gesture] || GESTURE_INFO['none'];
    
    // 更新图标和名称
    if (elements.gestureIcon) {
        elements.gestureIcon.textContent = info.icon;
    }
    if (elements.gestureName) {
        elements.gestureName.textContent = data.hand_detected ? info.name : '未检测到手';
    }
    
    // 更新样式
    elements.gestureDisplay.className = 'gesture-display';
    if (data.hand_detected && info.class) {
        elements.gestureDisplay.classList.add(info.class);
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
//                              新手引导系统
// ═══════════════════════════════════════════════════════════════════════════════

const TUTORIAL_STEPS = [
    {
        title: '欢迎使用 Gesture Music Paint',
        content: '这是一个用手势创作音乐绘画的应用。让我们快速了解如何使用！',
        icon: '🎨'
    },
    {
        title: '第1步：启动系统',
        content: '点击「启动系统」按钮，开启摄像头和手势识别。',
        icon: '▶️'
    },
    {
        title: '第2步：手势控制',
        content: '☝️ 伸出食指绘画 | ✋ 张开五指切换乐器 | ✊ 握拳播放/暂停 | ✌️ 比耶录制',
        icon: '🤚'
    },
    {
        title: '第3步：保存作品',
        content: '点击「保存画作」保存图片，点击「导出音频」保存音乐为 WAV 文件。',
        icon: '💾'
    }
];

let currentTutorialStep = 0;
let tutorialOverlay = null;

async function checkAndShowTutorial() {
    try {
        const response = await fetch('/api/tutorial/status');
        const data = await response.json();
        
        if (data.should_show) {
            showTutorial();
        }
    } catch (error) {
        console.log('获取教程状态失败:', error);
    }
}

function showTutorial() {
    currentTutorialStep = 0;
    createTutorialOverlay();
    renderTutorialStep();
}

function createTutorialOverlay() {
    if (tutorialOverlay) {
        tutorialOverlay.remove();
    }
    
    tutorialOverlay = document.createElement('div');
    tutorialOverlay.className = 'tutorial-overlay';
    tutorialOverlay.innerHTML = `
        <div class="tutorial-modal">
            <div class="tutorial-header">
                <span class="tutorial-icon"></span>
                <h3 class="tutorial-title"></h3>
            </div>
            <p class="tutorial-content"></p>
            <div class="tutorial-progress"></div>
            <div class="tutorial-actions">
                <button class="btn tutorial-skip">跳过教程</button>
                <button class="btn btn-primary tutorial-next">下一步</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(tutorialOverlay);
    
    // 绑定事件
    tutorialOverlay.querySelector('.tutorial-skip').addEventListener('click', closeTutorial);
    tutorialOverlay.querySelector('.tutorial-next').addEventListener('click', nextTutorialStep);
}

function renderTutorialStep() {
    if (!tutorialOverlay) return;
    
    const step = TUTORIAL_STEPS[currentTutorialStep];
    
    tutorialOverlay.querySelector('.tutorial-icon').textContent = step.icon;
    tutorialOverlay.querySelector('.tutorial-title').textContent = step.title;
    tutorialOverlay.querySelector('.tutorial-content').textContent = step.content;
    
    // 更新进度
    const progressHtml = TUTORIAL_STEPS.map((_, i) => 
        `<span class="progress-dot ${i === currentTutorialStep ? 'active' : ''} ${i < currentTutorialStep ? 'completed' : ''}"></span>`
    ).join('');
    tutorialOverlay.querySelector('.tutorial-progress').innerHTML = progressHtml;
    
    // 更新按钮文字
    const nextBtn = tutorialOverlay.querySelector('.tutorial-next');
    if (currentTutorialStep === TUTORIAL_STEPS.length - 1) {
        nextBtn.textContent = '开始使用';
    } else {
        nextBtn.textContent = '下一步';
    }
}

function nextTutorialStep() {
    currentTutorialStep++;
    
    if (currentTutorialStep >= TUTORIAL_STEPS.length) {
        closeTutorial();
    } else {
        renderTutorialStep();
    }
}

async function closeTutorial() {
    if (tutorialOverlay) {
        tutorialOverlay.classList.add('fade-out');
        setTimeout(() => {
            tutorialOverlay.remove();
            tutorialOverlay = null;
        }, 300);
    }
    
    // 标记教程完成
    try {
        await fetch('/api/tutorial/complete', { method: 'POST' });
    } catch (error) {
        console.log('标记教程完成失败:', error);
    }
}

// 页面加载后检查是否需要显示教程
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(checkAndShowTutorial, 500);
});
