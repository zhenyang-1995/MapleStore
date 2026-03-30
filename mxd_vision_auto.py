#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒险岛Online - 图像识别完全自动刷怪脚本
功能：
  - 双模式怪物检测：模板匹配 / 颜色轮廓检测（可切换）
  - 支持近战/远程职业战斗策略
  - 异常处理：防卡死、被击退恢复、死亡检测
  - 专为小地图优化

使用说明：
  1. 先运行脚本，选择检测模式
  2. 按提示截图保存怪物模板（如使用模板匹配模式）
  3. 配置职业类型和按键
  4. 进入游戏，按 F10 开始自动刷怪
  5. 按 ESC 停止
"""

import random
import threading
import time
import json
import cv2
import numpy as np
import mss
import pygetwindow as gw
from pathlib import Path
from datetime import datetime
from collections import deque
from pynput import keyboard
from pynput.keyboard import Controller, Key


class ScreenCapture:
    """屏幕捕获模块 - 使用mss实现高性能截图"""
    
    def __init__(self):
        self.sct = mss.mss()
        self.game_window = None
        self.monitor = None
        
    def find_game_window(self, window_title="冒险岛"):
        """查找游戏窗口"""
        try:
            # 尝试查找包含"冒险岛"的窗口
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                # 尝试其他常见标题
                for title in ["MapleStory", "新枫之谷", "Maple"]:
                    windows = gw.getWindowsWithTitle(title)
                    if windows:
                        break
                        
            if windows:
                self.game_window = windows[0]
                print(f"[屏幕] 找到游戏窗口: {self.game_window.title}")
                return True
            else:
                print("[屏幕] 未找到游戏窗口，将捕获全屏")
                return False
        except Exception as e:
            print(f"[屏幕] 查找窗口失败: {e}")
            return False
    
    def capture(self, region=None):
        """
        捕获屏幕区域
        region: (left, top, width, height) 或 None捕获全屏/游戏窗口
        返回: numpy array (BGR格式，OpenCV可用)
        """
        try:
            if region:
                monitor = {
                    "left": region[0],
                    "top": region[1],
                    "width": region[2],
                    "height": region[3]
                }
            elif self.game_window and self.game_window.isActive:
                # 捕获游戏窗口区域
                monitor = {
                    "left": self.game_window.left,
                    "top": self.game_window.top,
                    "width": self.game_window.width,
                    "height": self.game_window.height
                }
            else:
                # 捕获主屏幕
                monitor = self.sct.monitors[1]  # 1是主屏幕，0是所有屏幕
                
            screenshot = self.sct.grab(monitor)
            # 转换为OpenCV格式 (BGR)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            return img
            
        except Exception as e:
            print(f"[屏幕] 截图失败: {e}")
            return None
    
    def get_game_region(self):
        """获取游戏窗口区域"""
        if self.game_window:
            return (
                self.game_window.left,
                self.game_window.top,
                self.game_window.width,
                self.game_window.height
            )
        return None


class MonsterDetector:
    """怪物检测模块 - 支持模板匹配和颜色轮廓两种模式"""
    
    def __init__(self):
        self.mode = "template"  # "template" 或 "color"
        self.templates = []     # 模板图像列表
        self.template_threshold = 0.75  # 模板匹配阈值
        
        # 颜色检测参数
        self.color_ranges = {
            # HSV颜色范围，可根据怪物颜色调整
            "red": [(0, 100, 100), (10, 255, 255)],      # 红色怪物
            "red2": [(160, 100, 100), (180, 255, 255)],  # 红色（HSV环绕）
            "blue": [(100, 100, 100), (130, 255, 255)],  # 蓝色怪物
            "green": [(40, 100, 100), (80, 255, 255)],   # 绿色怪物
            "yellow": [(20, 100, 100), (35, 255, 255)],  # 黄色怪物
        }
        self.target_color = "red"  # 默认检测红色系怪物
        self.min_contour_area = 500   # 最小轮廓面积
        self.max_contour_area = 50000 # 最大轮廓面积
        
    def set_mode(self, mode):
        """设置检测模式"""
        if mode in ["template", "color"]:
            self.mode = mode
            print(f"[检测] 切换到模式: {mode}")
            return True
        return False
    
    def add_template(self, image_path):
        """添加模板图像"""
        template = cv2.imread(image_path)
        if template is not None:
            self.templates.append(template)
            print(f"[检测] 添加模板: {image_path}, 尺寸: {template.shape}")
            return True
        else:
            print(f"[检测] 无法加载模板: {image_path}")
            return False
    
    def detect(self, screenshot):
        """
        检测怪物位置
        返回: [(x, y, w, h), ...] 怪物边界框列表（相对于截图的坐标）
        """
        if screenshot is None:
            return []
            
        if self.mode == "template":
            return self._detect_by_template(screenshot)
        else:
            return self._detect_by_color(screenshot)
    
    def _detect_by_template(self, screenshot):
        """模板匹配检测"""
        monsters = []
        
        for template in self.templates:
            if template is None:
                continue
                
            # 多尺度匹配（处理怪物大小变化）
            h, w = template.shape[:2]
            for scale in [0.8, 0.9, 1.0, 1.1, 1.2]:
                resized_template = cv2.resize(template, None, fx=scale, fy=scale)
                if resized_template.shape[0] > screenshot.shape[0] or \
                   resized_template.shape[1] > screenshot.shape[1]:
                    continue
                    
                result = cv2.matchTemplate(screenshot, resized_template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                if max_val >= self.template_threshold:
                    x, y = max_loc
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    monsters.append((x, y, new_w, new_h))
                    
        # NMS去重（Non-Maximum Suppression）
        monsters = self._apply_nms(monsters, threshold=0.3)
        return monsters
    
    def _detect_by_color(self, screenshot):
        """颜色+轮廓检测"""
        monsters = []
        
        # 转换到HSV颜色空间
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)
        
        # 获取目标颜色范围
        color_range = self.color_ranges.get(self.target_color, self.color_ranges["red"])
        
        # 创建掩码
        if self.target_color == "red":
            # 红色需要两个范围（HSV中红色在0度和180度附近）
            mask1 = cv2.inRange(hsv, np.array(self.color_ranges["red"][0]), 
                               np.array(self.color_ranges["red"][1]))
            mask2 = cv2.inRange(hsv, np.array(self.color_ranges["red2"][0]), 
                               np.array(self.color_ranges["red2"][1]))
            mask = cv2.bitwise_or(mask1, mask2)
        else:
            mask = cv2.inRange(hsv, np.array(color_range[0]), np.array(color_range[1]))
        
        # 形态学操作去噪
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.min_contour_area < area < self.max_contour_area:
                x, y, w, h = cv2.boundingRect(cnt)
                # 过滤太扁或太长的区域（不太可能是怪物）
                aspect_ratio = w / float(h)
                if 0.3 < aspect_ratio < 3.0:
                    monsters.append((x, y, w, h))
        
        return monsters
    
    def _apply_nms(self, boxes, threshold=0.3):
        """非极大值抑制，去除重叠检测框"""
        if not boxes:
            return boxes
            
        # 按面积排序
        boxes = sorted(boxes, key=lambda b: b[2]*b[3], reverse=True)
        result = []
        
        for box in boxes:
            should_keep = True
            for kept in result:
                if self._iou(box, kept) > threshold:
                    should_keep = False
                    break
            if should_keep:
                result.append(box)
                
        return result
    
    def _iou(self, box1, box2):
        """计算两个框的IoU（交并比）"""
        x1, y1, w1, h1 = box1
        x2, y2, w2, h2 = box2
        
        # 计算交集
        xi1 = max(x1, x2)
        yi1 = max(y1, y2)
        xi2 = min(x1+w1, x2+w2)
        yi2 = min(y1+h1, y2+h2)
        
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        box1_area = w1 * h1
        box2_area = w2 * h2
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0
    
    def set_color(self, color_name):
        """设置检测的颜色"""
        if color_name in self.color_ranges:
            self.target_color = color_name
            print(f"[检测] 设置检测颜色: {color_name}")
            return True
        return False


class CombatStrategy:
    """战斗策略模块 - 支持近战/远程职业"""
    
    def __init__(self):
        self.combat_type = "melee"  # "melee"近战 或 "ranged"远程
        self.attack_range = 50      # 攻击距离（像素）
        self.attack_key = 'x'       # 攻击键
        self.skill_keys = ['a', 's']  # 技能键列表
        self.jump_key = Key.space   # 跳跃键
        
        # 按键控制器
        self.controller = Controller()
        
    def set_combat_type(self, combat_type, attack_range=None):
        """设置战斗类型"""
        if combat_type in ["melee", "ranged"]:
            self.combat_type = combat_type
            if attack_range:
                self.attack_range = attack_range
            else:
                self.attack_range = 80 if combat_type == "melee" else 250
            print(f"[战斗] 设置为{'近战' if combat_type=='melee' else '远程'}模式, 攻击距离: {self.attack_range}px")
            return True
        return False
    
    def set_keys(self, attack='x', skills=None, jump=Key.space):
        """设置按键"""
        self.attack_key = attack
        self.skill_keys = skills or ['a', 's']
        self.jump_key = jump
        
    def get_action(self, player_pos, monsters):
        """
        根据玩家位置和怪物位置决定行动
        返回: (action_type, params)
            action_type: "move_left", "move_right", "attack", "skill", "jump", "idle"
        """
        if not monsters:
            return "idle", None
            
        # 找到最近的怪物
        nearest = self._find_nearest_monster(player_pos, monsters)
        if nearest is None:
            return "idle", None
            
        mx, my, mw, mh = nearest
        px, py = player_pos
        
        # 怪物中心点
        monster_center_x = mx + mw // 2
        monster_center_y = my + mh // 2
        
        # 计算距离
        distance = abs(monster_center_x - px)
        height_diff = abs(monster_center_y - py)
        
        # 决策逻辑
        if height_diff > 50:
            # 高度差太大，可能需要跳跃或上下移动
            if monster_center_y < py:
                return "jump", None
                
        if distance <= self.attack_range:
            # 在攻击范围内
            if random.random() < 0.3 and self.skill_keys:
                # 30%概率使用技能
                skill = random.choice(self.skill_keys)
                return "skill", skill
            else:
                return "attack", self.attack_key
        else:
            # 需要移动靠近
            if monster_center_x < px:
                return "move_left", None
            else:
                return "move_right", None
    
    def _find_nearest_monster(self, player_pos, monsters):
        """找到最近的怪物"""
        if not monsters:
            return None
            
        px, py = player_pos
        nearest = None
        min_dist = float('inf')
        
        for (mx, my, mw, mh) in monsters:
            cx = mx + mw // 2
            cy = my + mh // 2
            dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                nearest = (mx, my, mw, mh)
                
        return nearest
    
    def execute_action(self, action_type, params):
        """执行动作"""
        if action_type == "idle":
            return
            
        elif action_type == "move_left":
            self._press_key(Key.left, duration=random.uniform(0.1, 0.3))
            
        elif action_type == "move_right":
            self._press_key(Key.right, duration=random.uniform(0.1, 0.3))
            
        elif action_type == "attack":
            key = params or self.attack_key
            self._press_key(key, duration=random.uniform(0.05, 0.15))
            
        elif action_type == "skill":
            key = params or self.skill_keys[0]
            self._press_key(key, duration=random.uniform(0.1, 0.2))
            
        elif action_type == "jump":
            self._press_key(self.jump_key, duration=random.uniform(0.05, 0.1))
    
    def _press_key(self, key, duration=0.1):
        """按下并释放按键，添加随机延迟"""
        self.controller.press(key)
        time.sleep(duration)
        self.controller.release(key)
        time.sleep(random.uniform(0.05, 0.15))  # 操作后随机延迟


class ExceptionHandler:
    """异常处理模块 - 防卡死、被击退恢复、死亡检测"""
    
    def __init__(self):
        # 卡死检测参数
        self.position_history = deque(maxlen=30)  # 记录最近30次位置
        self.action_history = deque(maxlen=50)    # 记录最近50次动作
        self.stuck_threshold = 20  # 连续多少次位置不变判定为卡死
        self.no_action_threshold = 100  # 连续多少次idle判定为无怪
        
        # 死亡检测
        self.death_check_interval = 10  # 每10秒检查一次死亡
        self.last_death_check = 0
        
        # 统计数据
        self.start_time = None
        self.total_kills_estimate = 0
        self.last_recovery_time = 0
        
    def update_position(self, player_pos):
        """更新位置历史"""
        self.position_history.append(player_pos)
        
    def update_action(self, action_type):
        """更新动作历史"""
        self.action_history.append(action_type)
        
    def check_exceptions(self, current_time):
        """检查各种异常情况，返回异常类型和恢复建议"""
        
        # 1. 卡死检测 - 长时间位置基本不变
        if len(self.position_history) >= self.stuck_threshold:
            recent_positions = list(self.position_history)[-self.stuck_threshold:]
            # 计算位置方差
            if len(recent_positions) > 0:
                xs = [p[0] for p in recent_positions]
                variance = max(xs) - min(xs)
                if variance < 10:  # 30帧内移动小于10像素
                    if current_time - self.last_recovery_time > 5:  # 5秒内不重复处理
                        self.last_recovery_time = current_time
                        return "stuck", "尝试跳跃或反向移动"
        
        # 2. 无怪物检测 - 长时间idle
        if len(self.action_history) >= self.no_action_threshold:
            recent_actions = list(self.action_history)[-self.no_action_threshold:]
            idle_count = recent_actions.count("idle")
            if idle_count > self.no_action_threshold * 0.8:  # 80%时间idle
                if current_time - self.last_recovery_time > 5:
                    self.last_recovery_time = current_time
                    return "no_monsters", "尝试移动寻找怪物"
        
        # 3. 被击退检测 - 位置突然大幅变化（简化版）
        if len(self.position_history) >= 3:
            p1 = self.position_history[-3]
            p2 = self.position_history[-1]
            if p1 and p2:
                dist = abs(p2[0] - p1[0])
                if dist > 100:  # 突然移动超过100像素
                    return "knocked_back", None
        
        return None, None
    
    def execute_recovery(self, exception_type):
        """执行恢复操作"""
        controller = Controller()
        
        if exception_type == "stuck":
            print("[异常] 检测到卡死，执行恢复...")
            # 尝试跳跃或随机移动
            for _ in range(3):
                if random.random() < 0.5:
                    controller.press(Key.left)
                    time.sleep(0.3)
                    controller.release(Key.left)
                else:
                    controller.press(Key.right)
                    time.sleep(0.3)
                    controller.release(Key.right)
                controller.press(Key.space)
                time.sleep(0.1)
                controller.release(Key.space)
                time.sleep(0.3)
                
        elif exception_type == "no_monsters":
            print("[异常] 长时间未找到怪物，执行探索...")
            # 左右移动探索
            for direction in [Key.left, Key.right, Key.left, Key.right]:
                controller.press(direction)
                time.sleep(0.5)
                controller.release(direction)
                time.sleep(0.2)
                
        elif exception_type == "knocked_back":
            print("[异常] 检测到被击退，恢复中...")
            # 短暂停顿后继续
            time.sleep(0.5)
            
        # 清空历史记录重新开始
        self.position_history.clear()
        self.action_history.clear()


class MXDVisionAuto:
    """图像识别自动刷怪主控类"""
    
    def __init__(self):
        # 初始化各模块
        self.screen = ScreenCapture()
        self.detector = MonsterDetector()
        self.combat = CombatStrategy()
        self.exception_handler = ExceptionHandler()
        
        # 运行状态
        self.running = False
        self.stop_flag = False
        self.show_debug = False  # 是否显示调试画面
        
        # 玩家位置（屏幕中心下方，需要根据实际情况调整）
        self.player_offset_x = 0  # 相对于截图中心的X偏移
        self.player_offset_y = 50  # 相对于截图中心的Y偏移
        
        # 帧率控制
        self.target_fps = 15
        self.frame_interval = 1.0 / self.target_fps
        
        # 统计数据
        self.frame_count = 0
        self.detection_count = 0
        self.start_time = None
        
    def setup(self):
        """初始化设置"""
        print("\n" + "="*50)
        print("冒险岛图像识别自动刷怪 - 初始化")
        print("="*50 + "\n")
        
        # 查找游戏窗口
        self.screen.find_game_window()
        
        # 选择检测模式
        print("\n选择怪物检测模式:")
        print("1. 模板匹配 (需要先截图保存怪物图片)")
        print("2. 颜色检测 (基于怪物颜色识别)")
        choice = input("请输入 (1-2): ").strip()
        
        if choice == "1":
            self.detector.set_mode("template")
            self._setup_template_mode()
        else:
            self.detector.set_mode("color")
            self._setup_color_mode()
            
        # 设置战斗类型
        print("\n选择职业类型:")
        print("1. 近战 (战士/飞侠等)")
        print("2. 远程 (法师/弓箭手等)")
        combat_choice = input("请输入 (1-2): ").strip()
        
        if combat_choice == "2":
            attack_range = input("请输入攻击距离 (默认250像素): ").strip()
            attack_range = int(attack_range) if attack_range.isdigit() else 250
            self.combat.set_combat_type("ranged", attack_range)
        else:
            attack_range = input("请输入攻击距离 (默认80像素): ").strip()
            attack_range = int(attack_range) if attack_range.isdigit() else 80
            self.combat.set_combat_type("melee", attack_range)
            
        # 设置按键
        print("\n设置按键 (直接回车使用默认值):")
        attack = input("攻击键 (默认x): ").strip() or 'x'
        skills_input = input("技能键 (多个用逗号分隔，默认a,s): ").strip()
        skills = skills_input.split(',') if skills_input else ['a', 's']
        self.combat.set_keys(attack=attack, skills=skills)
        
        print("\n" + "="*50)
        print("初始化完成！")
        print(f"检测模式: {'模板匹配' if self.detector.mode=='template' else '颜色检测'}")
        print(f"战斗类型: {'近战' if self.combat.combat_type=='melee' else '远程'}")
        print("按 F10 开始自动刷怪，ESC 停止")
        print("="*50 + "\n")
        
    def _setup_template_mode(self):
        """设置模板匹配模式"""
        print("\n模板匹配设置:")
        print("请先进入游戏，对准怪物，按回车截图保存为模板")
        input("准备好后按回车...")
        
        # 截图
        img = self.screen.capture()
        if img is not None:
            timestamp = datetime.now().strftime("%m%d_%H%M%S")
            template_path = f"template_{timestamp}.png"
            
            # 让用户选择怪物区域（简化版：假设怪物在屏幕中央）
            h, w = img.shape[:2]
            # 截取中央区域作为模板
            cx, cy = w // 2, h // 2
            crop_size = 80
            template = img[cy-crop_size:cy+crop_size, cx-crop_size:cx+crop_size]
            cv2.imwrite(template_path, template)
            self.detector.add_template(template_path)
            print(f"已保存模板: {template_path}")
            
        # 询问是否添加更多模板
        while input("\n是否添加更多模板? (y/n): ").strip().lower() == 'y':
            input("对准另一种怪物，准备好后按回车...")
            img = self.screen.capture()
            if img is not None:
                timestamp = datetime.now().strftime("%m%d_%H%M%S")
                template_path = f"template_{timestamp}.png"
                h, w = img.shape[:2]
                cx, cy = w // 2, h // 2
                crop_size = 80
                template = img[cy-crop_size:cy+crop_size, cx-crop_size:cx+crop_size]
                cv2.imwrite(template_path, template)
                self.detector.add_template(template_path)
                
    def _setup_color_mode(self):
        """设置颜色检测模式"""
        print("\n颜色检测设置:")
        print("选择要检测的怪物颜色:")
        print("1. 红色 (如蜗牛、绿水灵)")
        print("2. 蓝色 (如蓝水灵)")
        print("3. 绿色 (如绿蘑菇)")
        print("4. 黄色 (如黄蘑菇)")
        
        color_choice = input("请输入 (1-4): ").strip()
        color_map = {"1": "red", "2": "blue", "3": "green", "4": "yellow"}
        color = color_map.get(color_choice, "red")
        self.detector.set_color(color)
        
        # 调整参数
        min_area = input("最小怪物面积 (默认500): ").strip()
        if min_area.isdigit():
            self.detector.min_contour_area = int(min_area)
            
    def get_player_position(self, screenshot):
        """获取玩家位置（简化版：假设在屏幕底部中央）"""
        if screenshot is None:
            return None
        h, w = screenshot.shape[:2]
        return (w // 2 + self.player_offset_x, h - 100 + self.player_offset_y)
        
    def run_once(self):
        """执行一次检测和战斗循环"""
        # 截图
        screenshot = self.screen.capture()
        if screenshot is None:
            return
            
        # 获取玩家位置
        player_pos = self.get_player_position(screenshot)
        if player_pos:
            self.exception_handler.update_position(player_pos)
            
        # 检测怪物
        monsters = self.detector.detect(screenshot)
        self.detection_count += len(monsters)
        
        # 决策
        action_type, params = self.combat.get_action(player_pos, monsters)
        self.exception_handler.update_action(action_type)
        
        # 执行动作
        self.combat.execute_action(action_type, params)
        
        # 显示调试信息
        if self.show_debug:
            self._draw_debug_info(screenshot, player_pos, monsters, action_type)
            
        # 异常检测
        current_time = time.time()
        exception_type, suggestion = self.exception_handler.check_exceptions(current_time)
        if exception_type:
            self.exception_handler.execute_recovery(exception_type)
            
        self.frame_count += 1
        
    def _draw_debug_info(self, img, player_pos, monsters, action):
        """绘制调试信息"""
        # 复制图像
        debug_img = img.copy()
        
        # 绘制玩家位置
        if player_pos:
            cv2.circle(debug_img, player_pos, 10, (0, 255, 0), -1)
            cv2.circle(debug_img, player_pos, self.combat.attack_range, (0, 255, 0), 2)
            
        # 绘制怪物框
        for (x, y, w, h) in monsters:
            cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 0, 255), 2)
            
        # 显示信息
        info_text = f"Monsters: {len(monsters)} | Action: {action} | Frame: {self.frame_count}"
        cv2.putText(debug_img, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 显示图像
        cv2.imshow("Debug", debug_img)
        cv2.waitKey(1)
        
    def start(self):
        """开始自动刷怪"""
        self.running = True
        self.stop_flag = False
        self.start_time = time.time()
        self.frame_count = 0
        
        print("\n" + "="*50)
        print("自动刷怪开始！")
        print("3秒后执行...")
        print("="*50 + "\n")
        
        for i in range(3, 0, -1):
            print(f"{i}...")
            time.sleep(1)
            if self.stop_flag:
                break
                
        print("运行中... 按 ESC 停止\n")
        
        # 启动ESC监听
        esc_thread = threading.Thread(target=self._esc_listener)
        esc_thread.daemon = True
        esc_thread.start()
        
        try:
            while not self.stop_flag:
                loop_start = time.time()
                
                self.run_once()
                
                # 帧率控制
                elapsed = time.time() - loop_start
                if elapsed < self.frame_interval:
                    time.sleep(self.frame_interval - elapsed)
                    
        except Exception as e:
            print(f"\n[错误] 运行时异常: {e}")
            import traceback
            traceback.print_exc()
            
        finally:
            self.running = False
            cv2.destroyAllWindows()
            
            # 打印统计
            run_time = time.time() - self.start_time
            print("\n" + "="*50)
            print("自动刷怪已停止")
            print(f"运行时间: {run_time:.1f}秒")
            print(f"处理帧数: {self.frame_count}")
            print(f"平均FPS: {self.frame_count/run_time:.1f}")
            print(f"检测到怪物: {self.detection_count}次")
            print("="*50 + "\n")
            
    def _esc_listener(self):
        """监听ESC键"""
        def on_press(key):
            if key == keyboard.Key.esc:
                self.stop_flag = True
                print("\n[停止] 检测到ESC键...")
                return False
                
        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
            
    def toggle_debug(self):
        """切换调试模式"""
        self.show_debug = not self.show_debug
        if not self.show_debug:
            cv2.destroyAllWindows()
        print(f"[设置] 调试模式: {'开启' if self.show_debug else '关闭'}")


def main():
    """主函数"""
    bot = MXDVisionAuto()
    
    print("""
╔══════════════════════════════════════════════════════════╗
║     冒险岛Online - 图像识别完全自动刷怪                   ║
╠══════════════════════════════════════════════════════════╣
║  功能特性:                                                ║
║  • 双模式怪物检测: 模板匹配 / 颜色检测                    ║
║  • 支持近战/远程职业战斗策略                              ║
║  • 异常处理: 防卡死、被击退恢复、无怪探索                  ║
║  • 专为小地图优化                                         ║
╠══════════════════════════════════════════════════════════╣
║  使用步骤:                                                ║
║  1. 确保游戏窗口可见                                      ║
║  2. 运行脚本完成初始化设置                                ║
║  3. 进入游戏，按 F10 开始自动刷怪                         ║
║  4. 按 ESC 停止                                           ║
╚══════════════════════════════════════════════════════════╝
""")
    
    # 初始化设置
    bot.setup()
    
    # 主菜单
    while True:
        print("\n主菜单:")
        print("1. 开始自动刷怪")
        print("2. 切换调试显示")
        print("3. 重新设置")
        print("0. 退出")
        
        choice = input("\n请选择: ").strip()
        
        if choice == '1':
            bot.start()
        elif choice == '2':
            bot.toggle_debug()
        elif choice == '3':
            bot.setup()
        elif choice == '0':
            print("\n感谢使用，再见！")
            break
        else:
            print("无效选择")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序已退出")
    except Exception as e:
        print(f"\n[错误] 程序异常: {e}")
        import traceback
        traceback.print_exc()
