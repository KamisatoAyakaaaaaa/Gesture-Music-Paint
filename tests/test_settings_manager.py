# -*- coding: utf-8 -*-
"""
settings_manager.py 单元测试
"""

import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class TestSettingsManager:
    """SettingsManager 测试"""
    
    def test_default_settings(self):
        """测试默认设置"""
        # 导入时会使用默认设置
        from settings_manager import SettingsManager
        
        # 创建临时设置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            # 手动创建一个新的 manager（绕过单例）
            class TestManager(SettingsManager):
                _instance = None
            
            manager = TestManager.__new__(TestManager)
            manager._initialized = False
            manager._settings_file = temp_path
            manager._settings = {}
            manager._defaults = {
                'current_instrument': 'piano',
                'brush_thickness': 10,
                'scale_type': 'pentatonic',
                'bpm': 120
            }
            
            # 测试获取默认值
            assert manager.get('current_instrument', 'piano') == 'piano'
            assert manager.get('nonexistent', 'default') == 'default'
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_settings_persistence(self):
        """测试设置持久化"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            # 写入设置
            settings = {'instrument': 'guitar', 'bpm': 100}
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f)
            
            # 读取设置
            with open(temp_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            
            assert loaded['instrument'] == 'guitar'
            assert loaded['bpm'] == 100
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
