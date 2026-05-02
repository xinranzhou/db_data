#!/usr/bin/env python3
"""
自动化执行主程序
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import setup_logger, logger
from config.app_settings import AppSettings
from config.settings import Settings
from core.screen_capture import ScreenCapture
from core.click_simulator import ClickSimulator
from core.template_matcher import TemplateMatcher
from core.coordinate_cache import CoordinateCache
from core.node_executor import NodeExecutor
from core.adb_device import ADBDevice
from automation.region_detector import RegionDetector
from automation.scroll_collector import ScrollCollector
from automation.workflow_engine import WorkflowEngine
from integration.packet_catcher import PacketCatcher
from integration.http_capture import HttpCaptureManager


def main():
    """主函数"""
    # 1. 初始化日志
    setup_logger()
    logger.info("=" * 60)
    logger.info("大众点评小程序自动化采集系统")
    logger.info("=" * 60)

    try:
        # 2. 检查是否使用ADB模式
        adb_device_id = os.environ.get('ADB_DEVICE_ID')
        adb_path = os.environ.get('ADB_PATH') or AppSettings.load().get('adb', {}).get('adb_path')
        adb_device = None

        if adb_device_id:
            logger.info(f"使用ADB模式，设备ID: {adb_device_id}")
            adb_device = ADBDevice(adb_device_id, adb_path=adb_path)
            if not adb_device.connect():
                logger.error("ADB设备连接失败")
                return 1

            device_info = adb_device.get_device_info()
            logger.info(f"设备信息: {device_info.get('model', 'Unknown')} - {device_info.get('screen_width', 0)}x{device_info.get('screen_height', 0)}")
        else:
            logger.info("使用PyAutoGUI模式（PC端）")

        # 3. 加载配置
        logger.info("加载配置文件...")
        nodes_config = WorkflowEngine.load_config(Settings.NODES_CONFIG)
        regions_config = WorkflowEngine.load_config(Settings.REGIONS_CONFIG)

        if not nodes_config or not regions_config:
            logger.error("配置文件加载失败")
            return 1

        # 4. 初始化核心组件
        logger.info("初始化核心组件...")
        screen = ScreenCapture(adb_device=adb_device, device_scale=Settings.SCREEN['device_scale'])
        clicker = ClickSimulator(adb_device=adb_device)
        matcher = TemplateMatcher(str(Settings.TEMPLATE_DIR), screen)
        cache_manager = CoordinateCache(str(Settings.CACHE_FILE))

        # 5. 初始化执行器
        logger.info("初始化执行器...")
        node_executor = NodeExecutor(matcher, clicker, cache_manager)
        region_detector = RegionDetector(
            matcher,
            clicker,
            regions_config.get('regions', [])
        )
        scroll_collector = ScrollCollector(
            clicker,
            matcher,
            nodes_config.get('scroll_config', {})
        )

        # 6. 初始化工作流引擎
        logger.info("初始化工作流引擎...")
        workflow = WorkflowEngine(node_executor, region_detector, scroll_collector)
        workflow.load_nodes(nodes_config.get('nodes', []))

        app_settings = AppSettings.load()
        capture_manager = None
        if os.environ.get('CAPTURE_MANAGED_BY_GUI') != '1' and app_settings.get('capture', {}).get('enabled'):
            capture_manager = HttpCaptureManager()
            ok, message = capture_manager.start(app_settings.get('capture', {}))
            logger.info(f"HTTP 抓取服务: {message}")

        # 7. 启动Rust抓包工具（后台运行）
        logger.info("启动Rust抓包工具...")
        packet_catcher = PacketCatcher(nodes_config.get('rust_config', {}))
        packet_catcher.start()

        # 8. 执行自动化流程
        logger.info("开始执行自动化流程...")
        success = workflow.run()

        if success:
            logger.info("✓ 自动化流程执行成功")
            return 0
        else:
            logger.error("✗ 自动化流程执行失败")
            return 1

    except KeyboardInterrupt:
        logger.info("用户中断")
        return 130

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        return 1

    finally:
        # 9. 停止抓包工具
        try:
            if 'packet_catcher' in locals():
                packet_catcher.stop()
        except:
            pass

        try:
            if 'capture_manager' in locals() and capture_manager:
                capture_manager.import_pending()
                capture_manager.stop()
        except:
            pass

        # 10. 断开ADB连接
        try:
            if adb_device:
                adb_device.disconnect()
        except:
            pass

        logger.info("流程结束")


if __name__ == '__main__':
    sys.exit(main())
