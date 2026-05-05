#!/usr/bin/env python3
"""
节点执行引擎
执行单个节点的操作（开始、点击、验证、等待、滑动、函数、结束）
"""

import importlib
import inspect
import json
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from utils.logger import logger


@dataclass
class NodeResult:
    """节点执行结果"""

    success: bool
    next_node_id: Optional[str] = None
    stop_workflow: bool = False
    message: str = ""


class NodeExecutor:
    """节点执行引擎"""

    def __init__(self, matcher, clicker, cache_manager):
        """
        Args:
            matcher: TemplateMatcher实例
            clicker: ClickSimulator实例
            cache_manager: CoordinateCache实例
        """
        self.matcher = matcher
        self.clicker = clicker
        self.cache = cache_manager
        self.node_registry = {}
        self.function_registry = {}
        logger.info("节点执行引擎初始化完成")

    def set_node_registry(self, nodes):
        """注册节点字典，供复杂节点解析其他节点配置时使用"""
        self.node_registry = {
            node.get('id'): node for node in nodes if node.get('id')
        }

    def set_function_registry(self, functions: Dict[str, object]):
        """注册可直接调用的函数"""
        self.function_registry = functions or {}

    def execute_node(self, node: Dict) -> NodeResult:
        """
        执行单个节点

        Args:
            node: 节点配置字典

        Returns:
            节点执行结果
        """
        node_type = node.get('type')
        node_name = node.get('name', 'unknown')

        logger.info(f"执行节点: {node_name} (类型: {node_type})")

        if node_type == 'start':
            return self._execute_start(node)
        elif node_type == 'click':
            return self._execute_click(node)
        elif node_type == 'verify':
            return self._execute_verify(node)
        elif node_type == 'wait':
            return self._execute_wait(node)
        elif node_type == 'swipe':
            return self._execute_swipe(node)
        elif node_type == 'function':
            return self._execute_function(node)
        elif node_type == 'end':
            return self._execute_end(node)
        else:
            logger.error(f"未知的节点类型: {node_type}")
            return NodeResult(False, message=f"未知的节点类型: {node_type}")

    def _execute_start(self, node: Dict) -> NodeResult:
        """执行开始节点"""
        logger.info(f"开始节点: {node.get('name', node.get('id', 'start'))}")
        return NodeResult(True)

    def _execute_click(self, node: Dict) -> NodeResult:
        """
        执行点击节点

        Args:
            node: 节点配置

        Returns:
            节点执行结果
        """
        node_id = node.get('id')
        template = node.get('template')
        threshold = node.get('threshold', 0.7)
        retry = node.get('retry', 1)

        # 1. 尝试使用缓存坐标
        cache = self.cache.get_node_cache(node_id)
        if cache and cache.get('center'):
            x, y = cache['center']
            logger.info(f"使用缓存坐标: ({x}, {y})")
            if self.clicker.click(x, y):
                return NodeResult(True)
            else:
                logger.warning("缓存坐标点击失败，尝试模板匹配")

        # 2. 缓存失效，使用模板匹配
        for attempt in range(retry):
            if attempt > 0:
                logger.info(f"重试 {attempt}/{retry}")

            match = self.matcher.find_best_match(template, threshold)

            if match:
                # 3. 更新缓存
                self.cache.update_node_cache(
                    node_id,
                    rect=match.rect,
                    center=match.center,
                    confidence=match.confidence
                )

                # 4. 点击
                if self.clicker.click(match.x, match.y):
                    return NodeResult(True)

            # 降低阈值重试
            if attempt < retry - 1:
                threshold = max(0.6, threshold - 0.1)
                logger.info(f"降低阈值到 {threshold:.2f}")
                time.sleep(1)

        logger.error(f"节点 {node.get('name')} 执行失败")
        return NodeResult(False, message=f"节点 {node.get('name')} 执行失败")

    def _execute_verify(self, node: Dict) -> NodeResult:
        """
        执行验证节点

        Args:
            node: 节点配置

        Returns:
            节点执行结果
        """
        template = node.get('template')
        threshold = node.get('threshold', 0.7)
        timeout = float(node.get('timeout', 0.0) or 0.0)

        if timeout <= 0:
            match = self.matcher.find_best_match(template, threshold)
            logger.info(f"立即验证节点: {node.get('name')} (单次判断)")
        else:
            match = self.matcher.wait_for_template(
                template,
                timeout=timeout,
                threshold=threshold
            )

        if match:
            logger.info(f"验证成功: {node.get('name')}")
            return NodeResult(True)
        else:
            logger.error(f"验证失败: {node.get('name')}")
            return NodeResult(False, message=f"验证失败: {node.get('name')}")

    def _execute_wait(self, node: Dict) -> NodeResult:
        """
        执行等待节点

        Args:
            node: 节点配置

        Returns:
            节点执行结果
        """
        wait_min = node.get('wait_min')
        wait_max = node.get('wait_max')

        if wait_min is not None or wait_max is not None:
            min_value = float(wait_min if wait_min is not None else wait_max)
            max_value = float(wait_max if wait_max is not None else wait_min)
            if max_value < min_value:
                min_value, max_value = max_value, min_value
            duration = random.uniform(min_value, max_value)
            logger.info(f"随机等待 {duration:.2f} 秒 (范围: {min_value:.2f}-{max_value:.2f})")
        else:
            duration = float(node.get('duration', 1.0))
            logger.info(f"等待 {duration} 秒")

        time.sleep(duration)
        return NodeResult(True)

    def _execute_swipe(self, node: Dict) -> NodeResult:
        """
        执行滑动节点

        支持固定次数滑动，或滑动到停止模板出现为止。
        """
        direction = node.get('swipe_direction', 'up')
        distance = int(node.get('swipe_distance', 500))
        duration = float(node.get('swipe_duration', 0.5))
        max_swipes = max(1, int(node.get('max_swipes', 10)))
        max_failures = max(1, int(node.get('max_failures', 3)))
        post_wait = float(node.get('post_wait', node.get('delay_after', 0.5)))
        stop_template = node.get('stop_template')
        stop_threshold = float(node.get('stop_threshold', node.get('threshold', 0.8)))
        check_before_swipe = bool(node.get('check_before_swipe', True))
        success_on_max_swipes = bool(node.get('success_on_max_swipes', not stop_template))
        stop_conditions = self._build_stop_conditions(node)

        if stop_conditions and check_before_swipe:
            stop_result = self._check_stop_conditions(stop_conditions)
            if stop_result:
                return stop_result

        failures = 0

        for swipe_index in range(1, max_swipes + 1):
            start, end = self._build_swipe_points(direction, distance)
            logger.info(
                f"执行滑动 {swipe_index}/{max_swipes}: "
                f"{direction} {distance}px, {start} -> {end}"
            )

            if not self.clicker.swipe(start, end, duration=duration):
                failures += 1
                logger.warning(f"滑动失败 {failures}/{max_failures}")
                if failures >= max_failures:
                    return NodeResult(False, message="滑动连续失败，已终止")
                time.sleep(post_wait)
                continue

            failures = 0
            time.sleep(post_wait)

            stop_result = self._check_stop_conditions(stop_conditions)
            if stop_result:
                return stop_result

        if success_on_max_swipes:
            logger.warning("达到最大滑动次数，按成功处理")
            return NodeResult(True, message="达到最大滑动次数")

        logger.error("达到最大滑动次数，未检测到停止模板")
        return NodeResult(False, message="达到最大滑动次数，未检测到停止模板")

    def _execute_function(self, node: Dict) -> NodeResult:
        """执行函数调用节点"""
        function_path = (node.get('function_path') or '').strip()
        if not function_path:
            return NodeResult(False, message="未配置函数路径")

        try:
            function = self._resolve_function_callable(function_path)
        except Exception as exc:
            logger.error(f"函数解析失败: {function_path} - {exc}")
            return NodeResult(False, message=f"函数解析失败: {function_path}")

        try:
            args_text = (node.get('function_args_text') or '').strip()
            parsed_args = json.loads(args_text) if args_text else None
        except Exception as exc:
            logger.error(f"函数参数解析失败: {exc}")
            return NodeResult(False, message="函数参数 JSON 解析失败")

        try:
            result = self._invoke_function(function, parsed_args)
            normalized = self._normalize_function_result(result)
            logger.info(f"函数调用完成: {function_path}")
            return normalized
        except Exception as exc:
            logger.error(f"函数执行失败: {function_path} - {exc}", exc_info=True)
            return NodeResult(False, message=f"函数执行失败: {function_path}")

    def _execute_end(self, node: Dict) -> NodeResult:
        """执行结束节点"""
        success = bool(node.get('end_success', True))
        message = node.get('end_message', '流程结束')
        logger.info(f"结束节点: {message}")
        return NodeResult(success=success, stop_workflow=True, message=message)

    def _template_exists(self, template_name: str, threshold: float) -> bool:
        """检查模板是否出现"""
        match = self.matcher.find_best_match(template_name, threshold=threshold)
        return match is not None

    def _build_stop_conditions(self, node: Dict):
        """构造滑动节点的停止条件"""
        conditions = []
        default_threshold = float(node.get('stop_threshold', node.get('threshold', 0.8)))
        stop_rules_text = (node.get('stop_rules_text') or '').strip()

        if stop_rules_text:
            for raw_line in stop_rules_text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith('#'):
                    continue

                source, next_node_id = self._parse_stop_rule_line(line)
                condition = self._resolve_stop_rule_source(source, default_threshold)
                if condition:
                    condition['next_node_id'] = next_node_id
                    conditions.append(condition)

        stop_template = node.get('stop_template')
        if stop_template:
            conditions.append({
                'label': stop_template,
                'template': stop_template,
                'threshold': default_threshold,
                'next_node_id': node.get('stop_next_node') or None,
            })

        return conditions

    @staticmethod
    def _parse_stop_rule_line(line: str):
        """解析停止规则文本，格式: 模板或节点ID -> 下一个节点ID"""
        if '->' in line:
            source, next_node_id = line.split('->', 1)
            return source.strip(), next_node_id.strip() or None
        return line.strip(), None

    def _resolve_stop_rule_source(self, source: str, default_threshold: float):
        """将停止规则源解析为模板检测条件"""
        if not source:
            return None

        referenced_node = self.node_registry.get(source)
        if referenced_node:
            template = referenced_node.get('template') or referenced_node.get('stop_template')
            if not template:
                logger.warning(f"停止规则引用的节点未配置模板: {source}")
                return None
            return {
                'label': referenced_node.get('name', source),
                'template': template,
                'threshold': float(referenced_node.get('threshold', default_threshold)),
            }

        return {
            'label': source,
            'template': source,
            'threshold': default_threshold,
        }

    def _check_stop_conditions(self, conditions) -> Optional[NodeResult]:
        """检查是否命中任何停止条件"""
        for condition in conditions:
            if self._template_exists(condition['template'], condition['threshold']):
                logger.info(f"检测到停止条件，结束滑动: {condition['label']}")
                return NodeResult(
                    True,
                    next_node_id=condition.get('next_node_id'),
                    message=f"匹配停止条件: {condition['label']}",
                )
        return None

    def _resolve_function_callable(self, function_path: str):
        """解析函数路径"""
        if function_path in self.function_registry:
            return self.function_registry[function_path]

        if ':' in function_path:
            module_name, attr_name = function_path.split(':', 1)
        else:
            module_name, attr_name = function_path.rsplit('.', 1)

        module = importlib.import_module(module_name)
        return getattr(module, attr_name)

    def _invoke_function(self, function, parsed_args):
        """执行函数，支持位置参数、关键字参数和上下文注入"""
        signature = inspect.signature(function)
        kwargs = {}
        args = []

        if isinstance(parsed_args, dict):
            kwargs = dict(parsed_args)
        elif isinstance(parsed_args, list):
            args = list(parsed_args)
        elif parsed_args is not None:
            args = [parsed_args]

        if 'context' in signature.parameters and 'context' not in kwargs:
            kwargs['context'] = self._build_function_context()

        return function(*args, **kwargs)

    def _build_function_context(self):
        """构建函数调用上下文"""
        return {
            'executor': self,
            'matcher': self.matcher,
            'clicker': self.clicker,
            'cache': self.cache,
            'nodes': self.node_registry,
        }

    @staticmethod
    def _normalize_function_result(result) -> NodeResult:
        """将函数返回值标准化为 NodeResult"""
        if isinstance(result, NodeResult):
            return result
        if isinstance(result, dict):
            return NodeResult(
                success=bool(result.get('success', True)),
                next_node_id=result.get('next_node_id'),
                stop_workflow=bool(result.get('stop_workflow', False)),
                message=result.get('message', ''),
            )
        if isinstance(result, bool):
            return NodeResult(success=result)
        if result is None:
            return NodeResult(success=True)
        return NodeResult(success=bool(result), message=str(result))

    def _build_swipe_points(self, direction: str, distance: int) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """根据方向和距离构造滑动起止点"""
        screen_width, screen_height = self.matcher.screen_capture.get_screen_size()
        center_x = screen_width // 2
        center_y = screen_height // 2
        horizontal_margin = max(50, screen_width // 6)
        vertical_margin = max(80, screen_height // 6)

        if direction == 'down':
            start = (center_x, center_y - distance // 2)
            end = (center_x, min(screen_height - vertical_margin, center_y + distance // 2))
        elif direction == 'left':
            start = (center_x + distance // 2, center_y)
            end = (max(horizontal_margin, center_x - distance // 2), center_y)
        elif direction == 'right':
            start = (center_x - distance // 2, center_y)
            end = (min(screen_width - horizontal_margin, center_x + distance // 2), center_y)
        else:
            start = (center_x, center_y + distance // 2)
            end = (center_x, max(vertical_margin, center_y - distance // 2))

        return self._clamp_point(start, screen_width, screen_height), self._clamp_point(end, screen_width, screen_height)

    @staticmethod
    def _clamp_point(point: Tuple[int, int], screen_width: int, screen_height: int) -> Tuple[int, int]:
        """限制坐标在屏幕范围内"""
        x = min(max(1, point[0]), max(1, screen_width - 1))
        y = min(max(1, point[1]), max(1, screen_height - 1))
        return (x, y)
