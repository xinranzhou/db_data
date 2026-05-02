#!/usr/bin/env python3
"""
截图和框选工具
截取屏幕并框选目标区域，自动生成模板图片
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Dict
from utils.logger import logger


class ScreenshotTool:
    """截图和框选工具"""

    def __init__(self, screen_capture, template_dir: str):
        """
        Args:
            screen_capture: ScreenCapture实例
            template_dir: 模板保存目录
        """
        self.screen_capture = screen_capture
        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(parents=True, exist_ok=True)

        self.screenshot = None
        self.rect = None
        self.drawing = False
        self.start_point = None

        logger.info(f"截图工具初始化完成，模板目录: {self.template_dir}")

    def capture_and_select(self, template_name: str) -> Optional[Dict]:
        """
        截图并框选区域

        Args:
            template_name: 模板文件名

        Returns:
            {
                'template_path': str,
                'rect': (x, y, w, h),
                'center': (x, y)
            }
        """
        logger.info("开始截图...")

        # 1. 截取全屏
        self.screenshot = self.screen_capture.capture_screen()

        # 2. 显示截图并等待用户框选
        logger.info("请在窗口中拖拽框选目标区域，按Enter确认，Esc取消")

        # 创建窗口
        window_name = "截图工具 - 拖拽框选目标区域"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        # 设置鼠标回调
        cv2.setMouseCallback(window_name, self._mouse_callback)

        # 显示图片
        display_img = self.screenshot.copy()

        while True:
            # 如果正在绘制，显示矩形
            if self.rect:
                temp_img = self.screenshot.copy()
                x, y, w, h = self.rect
                cv2.rectangle(temp_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.imshow(window_name, temp_img)
            else:
                cv2.imshow(window_name, display_img)

            key = cv2.waitKey(1) & 0xFF

            # Enter键确认
            if key == 13:
                if self.rect:
                    break
                else:
                    logger.warning("请先框选区域")

            # Esc键取消
            elif key == 27:
                logger.info("用户取消")
                cv2.destroyAllWindows()
                return None

        cv2.destroyAllWindows()

        # 3. 裁剪并保存模板
        if self.rect:
            result = self._crop_and_save(template_name)
            logger.info(f"模板已保存: {result['template_path']}")
            return result

        return None

    def _mouse_callback(self, event, x, y, flags, param):
        """鼠标回调函数"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_point = (x, y)

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                w = x - self.start_point[0]
                h = y - self.start_point[1]
                self.rect = (self.start_point[0], self.start_point[1], w, h)

        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            w = x - self.start_point[0]
            h = y - self.start_point[1]
            self.rect = (self.start_point[0], self.start_point[1], w, h)

    def _crop_and_save(self, template_name: str) -> Dict:
        """
        裁剪并保存模板

        Args:
            template_name: 模板文件名

        Returns:
            结果字典
        """
        x, y, w, h = self.rect

        # 确保坐标为正
        if w < 0:
            x = x + w
            w = -w
        if h < 0:
            y = y + h
            h = -h

        # 裁剪图片
        cropped = self.screenshot[y:y+h, x:x+w]

        # 保存模板
        template_path = self.template_dir / template_name
        cv2.imwrite(str(template_path), cropped)

        # 计算中心点
        center_x = x + w // 2
        center_y = y + h // 2

        return {
            'template_path': str(template_path),
            'rect': (x, y, w, h),
            'center': (center_x, center_y)
        }
