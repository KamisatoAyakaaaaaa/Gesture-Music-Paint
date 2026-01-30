# -*- coding: utf-8 -*-
"""
作品管理器模块 - 作品保存、缩略图生成、历史管理
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
import cv2
import numpy as np

logger = logging.getLogger('GesturePaint.Gallery')

# 目录配置
GALLERY_FOLDER = 'Gallery'
PAINTINGS_FOLDER = os.path.join(GALLERY_FOLDER, 'paintings')
THUMBNAILS_FOLDER = os.path.join(GALLERY_FOLDER, 'thumbnails')
METADATA_FILE = os.path.join(GALLERY_FOLDER, 'gallery.json')

# 缩略图配置
THUMBNAIL_SIZE = (320, 180)


class GalleryManager:
    """
    作品管理器 - 负责作品的保存、加载和管理
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
        
        self._ensure_folders()
        self._metadata: Dict = self._load_metadata()
        self._initialized = True
    
    def _ensure_folders(self) -> None:
        """确保必要的文件夹存在"""
        for folder in [GALLERY_FOLDER, PAINTINGS_FOLDER, THUMBNAILS_FOLDER]:
            os.makedirs(folder, exist_ok=True)
    
    def _load_metadata(self) -> Dict:
        """加载作品元数据"""
        try:
            if os.path.exists(METADATA_FILE):
                with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载元数据失败: {e}")
        
        return {'works': [], 'total_count': 0}
    
    def _save_metadata(self) -> bool:
        """保存作品元数据"""
        try:
            with open(METADATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._metadata, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")
            return False
    
    def _generate_thumbnail(self, image: np.ndarray, output_path: str) -> bool:
        """生成缩略图"""
        try:
            thumbnail = cv2.resize(image, THUMBNAIL_SIZE, interpolation=cv2.INTER_AREA)
            cv2.imwrite(output_path, thumbnail)
            return True
        except Exception as e:
            logger.error(f"生成缩略图失败: {e}")
            return False
    
    def save_work(self, 
                  canvas: np.ndarray, 
                  notes_data: Optional[List] = None,
                  instrument: str = 'piano',
                  title: Optional[str] = None,
                  project_data: Optional[Dict] = None) -> Optional[Dict]:
        """
        保存作品
        
        Args:
            canvas: 画布图像 (numpy array)
            notes_data: 音符数据列表
            instrument: 使用的乐器
            title: 作品标题（可选）
            project_data: 项目数据（用于 Master 回放）
            
        Returns:
            作品信息字典，失败返回 None
        """
        try:
            timestamp = datetime.now()
            work_id = timestamp.strftime("%Y%m%d_%H%M%S")
            
            # 生成文件名
            painting_filename = f"painting_{work_id}.png"
            thumbnail_filename = f"thumb_{work_id}.jpg"
            notes_filename = f"notes_{work_id}.json" if notes_data else None
            project_filename = f"project_{work_id}.json" if project_data else None
            
            # 保存画作
            painting_path = os.path.join(PAINTINGS_FOLDER, painting_filename)
            cv2.imwrite(painting_path, canvas)
            
            # 生成缩略图
            thumbnail_path = os.path.join(THUMBNAILS_FOLDER, thumbnail_filename)
            self._generate_thumbnail(canvas, thumbnail_path)
            
            # 保存音符数据
            if notes_data:
                notes_path = os.path.join(GALLERY_FOLDER, notes_filename)
                with open(notes_path, 'w', encoding='utf-8') as f:
                    json.dump(notes_data, f, indent=2)
            
            # 保存项目数据（乐谱模型）
            if project_data:
                project_path = os.path.join(GALLERY_FOLDER, project_filename)
                with open(project_path, 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, indent=2, ensure_ascii=False)
            
            # 创建作品信息
            work_info = {
                'id': work_id,
                'title': title or f"作品 {self._metadata['total_count'] + 1}",
                'created_at': timestamp.isoformat(),
                'painting_file': painting_filename,
                'thumbnail_file': thumbnail_filename,
                'notes_file': notes_filename,
                'project_file': project_filename,
                'instrument': instrument,
                'notes_count': len(notes_data) if notes_data else 0,
                'stroke_count': len(project_data.get('strokes', [])) if project_data else 0
            }
            
            # 更新元数据
            self._metadata['works'].insert(0, work_info)  # 最新的在前面
            self._metadata['total_count'] += 1
            self._save_metadata()
            
            logger.info(f"作品已保存: {work_id}")
            return work_info
            
        except Exception as e:
            logger.error(f"保存作品失败: {e}")
            return None
    
    def get_works(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        """
        获取作品列表
        
        Args:
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            作品信息列表
        """
        works = self._metadata.get('works', [])
        return works[offset:offset + limit]
    
    def get_work(self, work_id: str) -> Optional[Dict]:
        """获取单个作品信息"""
        for work in self._metadata.get('works', []):
            if work['id'] == work_id:
                return work
        return None
    
    def get_work_image_path(self, work_id: str) -> Optional[str]:
        """获取作品图片路径"""
        work = self.get_work(work_id)
        if work:
            return os.path.join(PAINTINGS_FOLDER, work['painting_file'])
        return None
    
    def get_thumbnail_path(self, work_id: str) -> Optional[str]:
        """获取缩略图路径"""
        work = self.get_work(work_id)
        if work:
            return os.path.join(THUMBNAILS_FOLDER, work['thumbnail_file'])
        return None
    
    def get_notes_data(self, work_id: str) -> Optional[List]:
        """获取作品的音符数据"""
        work = self.get_work(work_id)
        if work and work.get('notes_file'):
            try:
                notes_path = os.path.join(GALLERY_FOLDER, work['notes_file'])
                with open(notes_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载音符数据失败: {e}")
        return None
    
    def get_project_data(self, work_id: str) -> Optional[Dict]:
        """获取作品的项目数据（用于 Master 回放）"""
        work = self.get_work(work_id)
        if work and work.get('project_file'):
            try:
                project_path = os.path.join(GALLERY_FOLDER, work['project_file'])
                with open(project_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载项目数据失败: {e}")
        return None
    
    def delete_work(self, work_id: str) -> bool:
        """删除作品"""
        work = self.get_work(work_id)
        if not work:
            return False
        
        try:
            # 删除文件
            painting_path = os.path.join(PAINTINGS_FOLDER, work['painting_file'])
            thumbnail_path = os.path.join(THUMBNAILS_FOLDER, work['thumbnail_file'])
            
            if os.path.exists(painting_path):
                os.remove(painting_path)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            if work.get('notes_file'):
                notes_path = os.path.join(GALLERY_FOLDER, work['notes_file'])
                if os.path.exists(notes_path):
                    os.remove(notes_path)
            
            # 更新元数据
            self._metadata['works'] = [w for w in self._metadata['works'] if w['id'] != work_id]
            self._save_metadata()
            
            logger.info(f"作品已删除: {work_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除作品失败: {e}")
            return False
    
    def get_total_count(self) -> int:
        """获取作品总数"""
        return self._metadata.get('total_count', 0)
    
    def update_work_title(self, work_id: str, title: str) -> bool:
        """更新作品标题"""
        for work in self._metadata.get('works', []):
            if work['id'] == work_id:
                work['title'] = title
                return self._save_metadata()
        return False


# 全局实例
gallery = GalleryManager()


def get_gallery() -> GalleryManager:
    """获取作品管理器实例"""
    return gallery
