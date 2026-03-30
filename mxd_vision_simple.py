#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒险岛Online - 图像识别自动刷怪 (简化版)
快速开始：
  1. python mxd_vision_simple.py
  2. 选择检测模式 (c=颜色/t=模板)
  3. 选择职业类型 (m=近战/r=远程)
  4. 进入游戏，按 F10 开始，ESC 停止
"""

import random
import threading
import time
from collections import deque

import cv2
import numpy as np
import mss
from pynput import keyboard
from pynput.keyboard import Controller, Key


class VisionBot:
    """简化版图像识别刷怪机器人"""
    
    def __init__(self):
        self.sct = mss.mss()
        self.controller = Controller()
        
        # 配置
        self.detect_mode = "color"  # color/template
        self.combat_type = "melee"  # melee/ranged
        self.attack_range = 80
        self.attack_key = 'x'
        self.skill_keys = ['a', 's']
        self.jump_key = Key.space  # 跳跃键，用户可配置
        self.has_dash = False      # 是否有位移技能
        self.dash_key = None       # 位移技能键

        # 状态
        self.running = False
        self.stop_flag = False
        self.templates = []
        
        # 异常处理
        self.pos_history = deque(maxlen=20)
        self.last_move_time = time.time()
        
    def capture(self):
        """截图"""
        try:
            monitor = self.sct.monitors[1]
            screenshot = self.sct.grab(monitor)
            img = np.array(screenshot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except:
            return None
    
    def detect_monsters(self, img):
        """检测怪物"""
        if img is None:
            return []
            
        if self.detect_mode == "template" and self.templates:
            return self._detect_template(img)
        else:
            return self._detect_color(img)
    
    def _detect_template(self, img):
        """模板匹配"""
        monsters = []
        for template in self.templates:
            result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= 0.7:
                h, w = template.shape[:2]
                monsters.append((*max_loc, w, h))
        return monsters
    
    def _detect_color(self, img):
        """颜色检测 - 红色怪物"""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # 红色范围
        mask1 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
        mask2 = cv2.inRange(hsv, np.array([160, 100, 100]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(mask1, mask2)
        
        # 去噪
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        monsters = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 300 < area < 50000:
                x, y, w, h = cv2.boundingRect(cnt)
                if 0.3 < w/h < 3.0:
                    monsters.append((x, y, w, h))
        return monsters
    
    def get_nearest(self, player_pos, monsters):
        """找最近的怪物"""
        if not monsters:
            return None
        nearest = min(monsters, key=lambda m: abs(m[0]+m[2]//2 - player_pos[0]))
        return nearest
    
    def action(self, player_pos, monsters):
        """决定并执行动作"""
        nearest = self.get_nearest(player_pos, monsters)

        if nearest is None:
            return "idle"

        mx, my, mw, mh = nearest
        monster_x = mx + mw // 2
        monster_y = my + mh // 2
        px, py = player_pos
        dist = abs(monster_x - px)
        height_diff = py - monster_y  # 正值=怪物在上方, 负值=怪物在下方

        # 记录位置用于异常检测
        self.pos_history.append(px)

        # 怪物在上方超过50px
        if height_diff > 50:
            direction = Key.left if monster_x < px else Key.right
            if self.has_dash:
                # 方向键 + 位移键
                self.controller.press(direction)
                time.sleep(0.05)
                self.controller.press(self.dash_key)
                time.sleep(0.1)
                self.controller.release(self.dash_key)
                self.controller.release(direction)
                time.sleep(random.uniform(0.05, 0.15))
            else:
                # 方向键 + 连按两次跳跃
                self.controller.press(direction)
                time.sleep(0.05)
                self._press(self.jump_key, 0.05)
                self._press(self.jump_key, 0.05)
                self.controller.release(direction)
            return "dash_up" if self.has_dash else "double_jump"

        # 怪物在下方超过30px
        if height_diff < -30:
            if self.has_dash:
                # 下 + 位移键
                self.controller.press(Key.down)
                time.sleep(0.05)
                self.controller.press(self.dash_key)
                time.sleep(0.1)
                self.controller.release(self.dash_key)
                self.controller.release(Key.down)
                time.sleep(random.uniform(0.05, 0.15))
            else:
                # 下 + 跳跃
                self.controller.press(Key.down)
                time.sleep(0.05)
                self._press(self.jump_key, 0.1)
                self.controller.release(Key.down)
            return "dash_down" if self.has_dash else "jump_down"

        # 水平攻击范围
        if dist <= self.attack_range:
            key = random.choice(self.skill_keys) if random.random() < 0.3 else self.attack_key
            self._press(key)
            return "attack"
        else:
            if monster_x < px:
                self._press(Key.left, 0.2)
                return "left"
            else:
                self._press(Key.right, 0.2)
                return "right"
    
    def _press(self, key, duration=0.1):
        """按键"""
        self.controller.press(key)
        time.sleep(duration)
        self.controller.release(key)
        time.sleep(random.uniform(0.05, 0.15))
    
    def check_stuck(self):
        """检查卡死"""
        if len(self.pos_history) < 15:
            return False
        recent = list(self.pos_history)[-15:]
        if max(recent) - min(recent) < 15:  # 15帧基本没动
            print("[异常] 卡死，尝试恢复...")
            # 跳跃和反向移动
            for _ in range(3):
                self._press(self.jump_key, 0.1)
                self._press(Key.left if random.random()<0.5 else Key.right, 0.3)
            self.pos_history.clear()
            return True
        return False
    
    def run_loop(self):
        """主循环"""
        while not self.stop_flag:
            t0 = time.time()
            
            img = self.capture()
            h, w = img.shape[:2] if img is not None else (0, 0)
            player_pos = (w//2, h-100)
            
            monsters = self.detect_monsters(img)
            action = self.action(player_pos, monsters)
            
            # 异常处理
            if action == "idle":
                if time.time() - self.last_move_time > 5:
                    # 5秒没动，左右探索
                    self._press(Key.left, 0.4)
                    self._press(Key.right, 0.4)
                    self.last_move_time = time.time()
            else:
                self.last_move_time = time.time()
            
            self.check_stuck()
            
            # 控制帧率
            elapsed = time.time() - t0
            if elapsed < 0.08:  # 约12fps
                time.sleep(0.08 - elapsed)
    
    def capture_template(self):
        """截图保存模板"""
        input("对准怪物后按回车截图...")
        img = self.capture()
        if img is None:
            return
        h, w = img.shape[:2]
        # 截取中央区域
        template = img[h//2-40:h//2+40, w//2-40:w//2+40]
        path = f"template_{int(time.time())}.png"
        cv2.imwrite(path, template)
        self.templates.append(template)
        print(f"已保存模板: {path}")
    
    def setup(self):
        """初始化"""
        print("\n" + "="*40)
        print("冒险岛图像识别自动刷怪")
        print("="*40)
        
        # 检测模式
        mode = input("\n检测模式 (c=颜色/t=模板): ").strip().lower()
        self.detect_mode = "template" if mode == 't' else "color"
        
        if self.detect_mode == "template":
            while input("添加模板? (y/n): ") == 'y':
                self.capture_template()
        
        # 职业类型
        combat = input("职业类型 (m=近战/r=远程): ").strip().lower()
        self.combat_type = "ranged" if combat == 'r' else "melee"
        self.attack_range = 250 if self.combat_type == "ranged" else 80

        # 跳跃键
        KEY_MAP = {
            'space': Key.space, 'shift': Key.shift, 'ctrl': Key.ctrl, 'alt': Key.alt,
            'tab': Key.tab, 'enter': Key.enter, 'up': Key.up, 'down': Key.down,
            'left': Key.left, 'right': Key.right,
        }
        jump_input = input("跳跃键 (默认space): ").strip().lower() or 'space'
        self.jump_key = KEY_MAP.get(jump_input, jump_input)

        # 位移技能
        has_dash_input = input("是否有位移技能? (y/n, 默认n): ").strip().lower()
        if has_dash_input == 'y':
            dash_input = input("位移技能键 (默认f): ").strip().lower() or 'f'
            self.has_dash = True
            self.dash_key = KEY_MAP.get(dash_input, dash_input)
            print(f"[配置] 位移技能已启用, 按键: {dash_input}")

        print(f"\n配置完成: {'模板' if self.detect_mode=='template' else '颜色'}检测 + {'远程' if self.combat_type=='ranged' else '近战'}")
        print(f"跳跃键: {jump_input}")
        print(f"位移技能: {'已启用' if self.has_dash else '未启用'}")
        print("按 F10 开始，ESC 停止\n")
    
    def start(self):
        """开始"""
        self.stop_flag = False
        print("\n3秒后开始...")
        for i in range(3, 0, -1):
            print(i)
            time.sleep(1)
        
        # ESC监听
        def esc_listener():
            def on_press(k):
                if k == keyboard.Key.esc:
                    self.stop_flag = True
                    return False
            with keyboard.Listener(on_press=on_press) as l:
                l.join()
        
        t = threading.Thread(target=esc_listener)
        t.daemon = True
        t.start()
        
        print("运行中...\n")
        self.run_loop()
        print("\n已停止")


def main():
    bot = VisionBot()
    bot.setup()
    
    while True:
        cmd = input("\n命令 (s=开始/q=退出): ").strip().lower()
        if cmd == 's':
            bot.start()
        elif cmd == 'q':
            break


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出")
