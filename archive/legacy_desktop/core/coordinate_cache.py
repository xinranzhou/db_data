#!/usr/bin/env python3
"""
坐标缓存管理器
管理节点坐标的缓存，避免重复识别
"""

import json
from pathlib import Path
from typing import Optional, Tuple, Dict
from datetime import datetime
from utils.logger import logger


class CoordinateCache:
    """坐标缓存管理器"""

    def __init__(self, cache_file: str):
        """
        Args:
            cache_file: 缓存文件路径
        """
        self.cache_file = Path(cache_file)
        self.cache_data = self._load_cache()
        logger.info(f"坐标缓存管理器初始化完成，缓存文件: {self.cache_file}")

    def _load_cache(self) -> Dict:
        """加载缓存文件"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"加载缓存成功，共 {len(data.get('nodes', {}))} 个节点")
                    return data
            except Exception as e:
                logger.error(f"加载缓存失败: {e}")
                return self._create_empty_cache()
        else:
            logger.info("缓存文件不存在，创建新缓存")
            return self._create_empty_cache()

    def _create_empty_cache(self) -> Dict:
        """创建空缓存"""
        return {
            "version": "1.0",
            "device_id": "unknown",
            "last_update": None,
            "nodes": {}
        }

    def _save_cache(self):
        """保存缓存到文件"""
        try:
            self.cache_data['last_update'] = datetime.now().isoformat()
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_data, f, indent=2, ensure_ascii=False)
            logger.debug("缓存已保存")
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    def get_node_cache(self, node_id: str) -> Optional[Dict]:
        """
        获取节点缓存

        Args:
            node_id: 节点ID

        Returns:
            缓存数据，未找到返回None
        """
        cache = self.cache_data['nodes'].get(node_id)
        if cache:
            logger.debug(f"节点 {node_id} 缓存命中")
        return cache

    def update_node_cache(self,
                          node_id: str,
                          rect: Tuple[int, int, int, int],
                          center: Tuple[int, int],
                          confidence: float = 0.0):
        """
        更新节点缓存

        Args:
            node_id: 节点ID
            rect: 矩形坐标 (x, y, w, h)
            center: 中心点坐标 (x, y)
            confidence: 置信度
        """
        self.cache_data['nodes'][node_id] = {
            'rect': list(rect),
            'center': list(center),
            'confidence': confidence,
            'update_time': datetime.now().isoformat()
        }
        self._save_cache()
        logger.info(f"节点 {node_id} 缓存已更新: center={center}, confidence={confidence:.3f}")

    def clear_node_cache(self, node_id: str):
        """
        清除节点缓存

        Args:
            node_id: 节点ID
        """
        if node_id in self.cache_data['nodes']:
            del self.cache_data['nodes'][node_id]
            self._save_cache()
            logger.info(f"节点 {node_id} 缓存已清除")

    def clear_all_cache(self):
        """清除所有缓存"""
        self.cache_data['nodes'] = {}
        self._save_cache()
        logger.info("所有缓存已清除")

    def set_device_id(self, device_id: str):
        """
        设置设备ID

        Args:
            device_id: 设备ID
        """
        self.cache_data['device_id'] = device_id
        self._save_cache()
        logger.info(f"设备ID已设置: {device_id}")

    def get_device_id(self) -> str:
        """获取设备ID"""
        return self.cache_data.get('device_id', 'unknown')
