#!/usr/bin/env python3
"""
工作流引擎
执行完整的自动化流程
"""

import time
import json
from pathlib import Path
from typing import List, Dict
from utils.logger import logger


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self, node_executor, region_detector, scroll_collector):
        """
        Args:
            node_executor: NodeExecutor实例
            region_detector: RegionDetector实例
            scroll_collector: ScrollCollector实例
        """
        self.executor = node_executor
        self.region_detector = region_detector
        self.scroll_collector = scroll_collector
        self.nodes = []
        self.node_map = {}
        self.node_order = []

        if hasattr(self.executor, 'set_function_registry'):
            self.executor.set_function_registry({
                'workflow.click_region_filter': self._click_region_filter_button,
                'region.detect_all': self.region_detector.detect_all_regions,
                'region.reset_detected': self._reset_detected_regions,
                'cache.clear_all': self.executor.cache.clear_all_cache,
            })

        logger.info("工作流引擎初始化完成")

    def load_nodes(self, nodes: List[Dict]):
        """
        加载节点配置

        Args:
            nodes: 节点配置列表
        """
        self.nodes = nodes
        self.node_map = {
            node['id']: node for node in nodes if node.get('id')
        }
        self.node_order = [node['id'] for node in nodes if node.get('id')]
        if hasattr(self.executor, 'set_node_registry'):
            self.executor.set_node_registry(nodes)
        logger.info(f"加载了 {len(nodes)} 个节点")

    def run(self) -> bool:
        """
        执行完整流程

        Returns:
            是否成功
        """
        logger.info("=== 开始自动化流程 ===")

        if self._should_use_node_graph():
            return self._run_node_graph()

        # 1. 执行初始化节点序列（点击美食、验证列表页、点击筛选项）
        if not self._execute_init_nodes():
            logger.error("初始化节点执行失败")
            return False

        # 2. 识别所有区域
        regions = self.region_detector.detect_all_regions()
        if not regions:
            logger.error("未检测到任何区域")
            return False

        logger.info(f"检测到 {len(regions)} 个区域")

        # 3. 遍历每个区域
        for i, region in enumerate(regions):
            region_name = region['name']
            logger.info(f"处理区域 {i+1}/{len(regions)}: {region_name}")

            # 3.1 点击区域
            if not self.region_detector.click_region(region_name):
                logger.error(f"点击区域失败: {region_name}")
                continue

            # 3.2 等待列表刷新
            time.sleep(1.0)

            # 3.3 滚动采集数据
            self.scroll_collector.collect_region_data(region_name)

            # 3.4 返回区域筛选菜单（准备切换下一个区域）
            if i < len(regions) - 1:  # 不是最后一个区域
                self._click_region_filter_button()
                time.sleep(0.5)

        logger.info("=== 自动化流程完成 ===")
        return True

    def _should_use_node_graph(self) -> bool:
        """是否使用节点流转模式"""
        for node in self.nodes:
            if node.get('type') in {'start', 'end', 'function', 'swipe'}:
                return True
            if node.get('next_node') or node.get('failure_node'):
                return True
            if node.get('is_start'):
                return True
        return False

    def _run_node_graph(self) -> bool:
        """按节点流转关系执行工作流"""
        start_node = self._find_start_node()
        if not start_node:
            logger.error("未找到可执行的起始节点")
            return False

        current_node_id = start_node['id']
        max_steps = max(1, self._get_max_steps())
        steps = 0

        logger.info(f"使用节点流转模式启动，起始节点: {start_node['name']} ({current_node_id})")

        while current_node_id:
            node = self.node_map.get(current_node_id)
            if not node:
                logger.error(f"节点不存在: {current_node_id}")
                return False

            steps += 1
            if steps > max_steps:
                logger.error(f"超过最大执行步数 {max_steps}，疑似存在死循环")
                return False

            result = self.executor.execute_node(node)

            if result.stop_workflow:
                logger.info("节点请求终止工作流")
                return result.success

            delay = node.get('delay_after', 0)
            if delay and delay > 0:
                time.sleep(delay)

            next_node_id = self._resolve_next_node(node, result.success, result.next_node_id)
            if not result.success and not next_node_id:
                logger.error(f"节点执行失败且未配置失败流转: {node['name']}")
                return False

            if not next_node_id:
                logger.info("节点流转完成")
                return result.success

            logger.info(f"节点流转: {node['id']} -> {next_node_id}")
            current_node_id = next_node_id

        logger.info("节点流转完成")
        return True

    def _find_start_node(self) -> Dict:
        """查找起始节点"""
        for node in self.nodes:
            if node.get('type') == 'start':
                return node
            if node.get('is_start'):
                return node

        for node in self.nodes:
            if node.get('is_init'):
                return node

        return self.nodes[0] if self.nodes else {}

    def _resolve_next_node(self, node: Dict, success: bool, explicit_next: str = None) -> str:
        """解析节点执行后的下一个节点"""
        next_node_id = explicit_next

        if not next_node_id:
            if success:
                next_node_id = node.get('next_node') or self._get_next_in_order(node.get('id'))
            else:
                next_node_id = node.get('failure_node')
                if not next_node_id and node.get('continue_on_fail'):
                    next_node_id = self._get_next_in_order(node.get('id'))

        if next_node_id in (None, "", "END", "__END__"):
            return ""

        if next_node_id not in self.node_map:
            logger.error(f"配置的下一个节点不存在: {next_node_id}")
            return ""

        return next_node_id

    def _get_next_in_order(self, node_id: str) -> str:
        """按列表顺序获取下一个节点"""
        if node_id not in self.node_order:
            return ""

        index = self.node_order.index(node_id)
        if index >= len(self.node_order) - 1:
            return ""

        return self.node_order[index + 1]

    def _get_max_steps(self) -> int:
        """获取工作流最大执行步数"""
        for node in self.nodes:
            if node.get('max_steps'):
                try:
                    return int(node['max_steps'])
                except (TypeError, ValueError):
                    break
        return max(100, len(self.nodes) * 10)

    def _reset_detected_regions(self):
        """重置区域识别缓存"""
        self.region_detector.detected_regions = []
        logger.info("区域识别缓存已重置")
        return True

    def _execute_init_nodes(self) -> bool:
        """
        执行初始化节点序列

        Returns:
            是否成功
        """
        logger.info("执行初始化节点序列")

        for node in self.nodes:
            if node.get('is_init', False):
                logger.info(f"执行节点: {node['name']}")

                result = self.executor.execute_node(node)
                if not result.success:
                    logger.error(f"节点执行失败: {node['name']}")
                    return False

                # 节点后延迟
                delay = node.get('delay_after', 0)
                if delay > 0:
                    time.sleep(delay)

        logger.info("初始化节点序列执行完成")
        return True

    def _click_region_filter_button(self) -> bool:
        """
        点击区域筛选按钮

        Returns:
            是否成功
        """
        # 查找区域筛选按钮节点
        for node in self.nodes:
            if node.get('name') == '点击区域筛选' or 'region_filter' in node.get('template', ''):
                return self.executor.execute_node(node).success

        logger.warning("未找到区域筛选按钮节点")
        return False

    @staticmethod
    def load_config(config_file: str) -> Dict:
        """
        加载配置文件

        Args:
            config_file: 配置文件路径

        Returns:
            配置字典
        """
        config_path = Path(config_file)
        if not config_path.exists():
            logger.error(f"配置文件不存在: {config_file}")
            return {}

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"加载配置成功: {config_file}")
                return config
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return {}
