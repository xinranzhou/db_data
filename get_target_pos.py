#!/usr/bin/env python3
"""
模板匹配工具 - 在目标图片中查找模板图片的位置

使用方法:
    python get_target_pos.py <模板图片> <目标图片> [阈值]

示例:
    python get_target_pos.py template.png target.jpg
    python get_target_pos.py template.png target.jpg 0.7
"""

import cv2
import numpy as np
import sys
import os


def get_target_pos(template_path, target_path, threshold=0.7):
    """
    在目标图片中查找模板图片的位置
    
    Args:
        template_path: 模板图片路径
        target_path: 目标图片路径
        threshold: 匹配阈值 (0-1)，默认0.7
    
    Returns:
        list: 匹配结果列表，每个元素包含 rect, center, confidence, scale
    """
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    target = cv2.imread(target_path, cv2.IMREAD_COLOR)
    
    if template is None:
        raise FileNotFoundError(f"无法加载模板图片: {template_path}")
    if target is None:
        raise FileNotFoundError(f"无法加载目标图片: {target_path}")
    
    th, tw = template.shape[:2]
    h, w = target.shape[:2]
    
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    target_gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
    
    scales = np.linspace(0.5, 2.0, 50)
    
    all_matches = []
    
    for scale in scales:
        scaled_w = int(tw * scale)
        scaled_h = int(th * scale)
        
        if scaled_w > w or scaled_h > h or scaled_w < 10 or scaled_h < 10:
            continue
        
        scaled_template = cv2.resize(template_gray, (scaled_w, scaled_h))
        
        result = cv2.matchTemplate(target_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
        
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= threshold:
            center_x = max_loc[0] + scaled_w // 2
            center_y = max_loc[1] + scaled_h // 2
            
            all_matches.append({
                'rect': (int(max_loc[0]), int(max_loc[1]), scaled_w, scaled_h),
                'center': (center_x, center_y),
                'confidence': float(max_val),
                'scale': float(scale)
            })
    
    if not all_matches:
        return []
    
    all_matches.sort(key=lambda x: x['confidence'], reverse=True)
    
    filtered = []
    for match in all_matches:
        x, y, w, h = match['rect']
        is_duplicate = False
        
        for fm in filtered:
            fx, fy, fw, fh = fm['rect']
            if abs(x - fx) < fw * 0.3 and abs(y - fy) < fh * 0.3:
                is_duplicate = True
                break
        
        if not is_duplicate:
            filtered.append(match)
    
    return filtered[:10]


def visualize_result(target_path, matches, output_path=None):
    """
    可视化匹配结果并保存
    
    Args:
        target_path: 目标图片路径
        matches: 匹配结果列表
        output_path: 输出图片路径，默认为 'result.jpg'
    """
    if output_path is None:
        output_path = 'result.jpg'
    
    target = cv2.imread(target_path, cv2.IMREAD_COLOR)
    result_img = target.copy()
    
    for i, match in enumerate(matches):
        x, y, w, h = match['rect']
        center_x, center_y = match['center']
        confidence = match['confidence']
        scale = match['scale']
        
        cv2.rectangle(result_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        cv2.circle(result_img, (center_x, center_y), 5, (0, 0, 255), -1)
        
        label = f"#{i+1}: {confidence:.2f} ({scale:.1f}x)"
        cv2.putText(result_img, label, (x, y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    cv2.imwrite(output_path, result_img)
    return output_path


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("错误: 参数不足")
        print("\n使用方法:")
        print("  python get_target_pos.py <模板图片> <目标图片> [阈值]")
        print("\n示例:")
        print("  python get_target_pos.py template.png target.jpg")
        print("  python get_target_pos.py template.png target.jpg 0.7")
        sys.exit(1)
    
    template_path = sys.argv[1]
    target_path = sys.argv[2]
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.7
    
    if not os.path.exists(template_path):
        print(f"错误: 模板图片不存在: {template_path}")
        sys.exit(1)
    
    if not os.path.exists(target_path):
        print(f"错误: 目标图片不存在: {target_path}")
        sys.exit(1)
    
    if threshold < 0 or threshold > 1:
        print(f"错误: 阈值必须在 0-1 之间，当前值: {threshold}")
        sys.exit(1)
    
    print(f"模板图片: {template_path}")
    print(f"目标图片: {target_path}")
    print(f"匹配阈值: {threshold}")
    print("-" * 60)
    
    try:
        matches = get_target_pos(template_path, target_path, threshold)
        
        if not matches:
            print("\n未找到匹配的模板!")
            print("\n建议:")
            print("  1. 降低阈值 (例如: 0.6 或 0.5)")
            print("  2. 检查模板图片是否在目标图片中存在")
            print("  3. 运行诊断工具: python analyze_match.py <模板> <目标>")
            sys.exit(0)
        
        print(f"\n找到 {len(matches)} 个匹配结果:\n")
        
        for i, match in enumerate(matches):
            print(f"匹配 #{i+1}:")
            print(f"  矩形坐标 (x, y, w, h): {match['rect']}")
            print(f"  中心坐标 (x, y): {match['center']}")
            print(f"  匹配置信度: {match['confidence']:.4f}")
            print(f"  缩放比例: {match['scale']:.2f}x")
            print()
        
        output_path = visualize_result(target_path, matches)
        print(f"结果图片已保存: {output_path}")
        
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
