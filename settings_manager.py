# -*- coding: utf-8 -*-
"""
设置管理器模块 - 用户设置持久化
"""

import json
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger('GesturePaint.Settings')

# 设置文件路径
SETTINGS_FILE = 'user_settings.json'

# 默认设置
DEFAULT_SETTINGS = {
    # 乐器设置
    'default_instrument': 'piano',
    'default_thickness': 10,
    
    # 音乐设置
    'scale_type': 'pentatonic',
    'root_note': 60,  # C4
    
    # 显示设置
    'show_waveform': True,
    'show_particles': True,
    'show_fps': True,
    
    # 引导设置
    'show_tutorial': True,
    'tutorial_completed': False,
    
    # 性能设置
    'video_quality': 65,  # JPEG 质量
    'particle_count': 50,
    
    # 界面设置
    'theme': 'dark',
    'sidebar_collapsed': False,
}

# 设置验证规则
SETTINGS_VALIDATORS = {
    'default_instrument': lambda v: v in ['piano', 'guitar', 'drums', 'synth', 'strings'],
    'default_thickness': lambda v: isinstance(v, int) and 3 <= v <= 30,
    'scale_type': lambda v: v in ['major', 'minor', 'pentatonic', 'blues', 'chromatic'],
    'root_note': lambda v: isinstance(v, int) and 0 <= v <= 127,
    'show_waveform': lambda v: isinstance(v, bool),
    'show_particles': lambda v: isinstance(v, bool),
    'show_fps': lambda v: isinstance(v, bool),
    'show_tutorial': lambda v: isinstance(v, bool),
    'tutorial_completed': lambda v: isinstance(v, bool),
    'video_quality': lambda v: isinstance(v, int) and 30 <= v <= 100,
    'particle_count': lambda v: isinstance(v, int) and 10 <= v <= 200,
    'theme': lambda v: v in ['dark', 'light'],
    'sidebar_collapsed': lambda v: isinstance(v, bool),
}


class SettingsManager:
    """
    设置管理器 - 负责用户设置的加载、保存和验证
    """
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._settings: Dict[str, Any] = {}
        self._load_settings()
        self._initialized = True
    
    def _load_settings(self) -> None:
        """从文件加载设置"""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                
                # 合并加载的设置和默认设置
                self._settings = DEFAULT_SETTINGS.copy()
                for key, value in loaded.items():
                    if key in DEFAULT_SETTINGS and self._validate_setting(key, value):
                        self._settings[key] = value
                
                logger.info(f"设置已从 {SETTINGS_FILE} 加载")
            else:
                self._settings = DEFAULT_SETTINGS.copy()
                logger.info("使用默认设置")
                
        except json.JSONDecodeError as e:
            logger.error(f"设置文件格式错误: {e}")
            self._settings = DEFAULT_SETTINGS.copy()
        except Exception as e:
            logger.error(f"加载设置失败: {e}")
            self._settings = DEFAULT_SETTINGS.copy()
    
    def _save_settings(self) -> bool:
        """保存设置到文件"""
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
            logger.info(f"设置已保存到 {SETTINGS_FILE}")
            return True
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            return False
    
    def _validate_setting(self, key: str, value: Any) -> bool:
        """验证单个设置值"""
        if key in SETTINGS_VALIDATORS:
            try:
                return SETTINGS_VALIDATORS[key](value)
            except Exception:
                return False
        return True
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取设置值"""
        return self._settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))
    
    def set(self, key: str, value: Any, save: bool = True) -> bool:
        """
        设置值
        
        Args:
            key: 设置键名
            value: 设置值
            save: 是否立即保存到文件
            
        Returns:
            是否设置成功
        """
        if not self._validate_setting(key, value):
            logger.warning(f"设置值验证失败: {key}={value}")
            return False
        
        self._settings[key] = value
        logger.debug(f"设置已更新: {key}={value}")
        
        if save:
            return self._save_settings()
        return True
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有设置"""
        return self._settings.copy()
    
    def reset(self, key: Optional[str] = None) -> bool:
        """
        重置设置
        
        Args:
            key: 要重置的键名，None 表示重置所有
            
        Returns:
            是否重置成功
        """
        if key is None:
            self._settings = DEFAULT_SETTINGS.copy()
            logger.info("所有设置已重置为默认值")
        elif key in DEFAULT_SETTINGS:
            self._settings[key] = DEFAULT_SETTINGS[key]
            logger.info(f"设置 {key} 已重置为默认值")
        else:
            logger.warning(f"未知的设置键: {key}")
            return False
        
        return self._save_settings()
    
    def mark_tutorial_completed(self) -> bool:
        """标记教程已完成"""
        self.set('tutorial_completed', True, save=False)
        self.set('show_tutorial', False, save=True)
        return True
    
    def should_show_tutorial(self) -> bool:
        """是否应该显示教程"""
        return self.get('show_tutorial', True) and not self.get('tutorial_completed', False)


# 全局实例
settings = SettingsManager()


def get_settings() -> SettingsManager:
    """获取设置管理器实例"""
    return settings
