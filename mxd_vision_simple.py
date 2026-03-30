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
import ctypes
from collections import deque

import cv2
import numpy as np
import mss
import pygetwindow as gw
from pynput import keyboard
from pynput.keyboard import Controller, Key


class VisionBot:
    """简化版图像识别刷怪机器人"""

    # 虚拟键码映射
    VK_MAP = {
        Key.left: 0x25, Key.up: 0x26, Key.right: 0x27, Key.down: 0x28,
        Key.space: 0x20, Key.shift: 0x10, Key.ctrl: 0x11, Key.alt: 0x12,
        Key.tab: 0x09, Key.enter: 0x0D, Key.esc: 0x1B,
    }
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101

    def __init__(self):
        self.sct = mss.mss()
        self.controller = Controller()
        self.game_hwnd = None  # 游戏窗口句柄，用于 PostMessage

        # 配置
        self.detect_mode = "color"  # color/template
        self.combat_type = "melee"  # melee/ranged
        self.attack_range = 80
        self.attack_key = 'x'
        self.skill_keys = ['a', 's']
        self.jump_key = Key.space  # 跳跃键，用户可配置
        self.has_dash = False      # 是否有位移技能
        self.dash_key = None       # 位移技能键

        # 截图区域
        self.capture_monitor = None  # None 表示使用默认全屏

        # 状态
        self.running = False
        self.stop_flag = False
        self.templates = []

        # 异常处理
        self.action_history = deque(maxlen=50)
        self.last_move_time = time.time()

    def _get_vk(self, key):
        """获取虚拟键码"""
        if key in self.VK_MAP:
            return self.VK_MAP[key]
        if isinstance(key, str) and len(key) == 1:
            return ord(key.upper())
        return None

    def _key_down(self, key):
        """按下按键 - 优先 PostMessage 直发到游戏窗口"""
        vk = self._get_vk(key)
        if self.game_hwnd and vk:
            ctypes.windll.user32.PostMessageW(self.game_hwnd, self.WM_KEYDOWN, vk, 0)
        else:
            self.controller.press(key)

    def _key_up(self, key):
        """释放按键"""
        vk = self._get_vk(key)
        if self.game_hwnd and vk:
            ctypes.windll.user32.PostMessageW(self.game_hwnd, self.WM_KEYUP, vk, 0xC0000001)
        else:
            self.controller.release(key)

    def _setup_capture(self):
        """设置截图区域，返回缓存的截图（如果有）"""
        print("\n截图区域设置:")
        print("1. 自动查找游戏窗口")
        print("2. 鼠标拖拽选择区域")
        print("3. 使用全屏截图")

        choice = input("请选择 (1-3, 默认3): ").strip() or '3'

        if choice == '1':
            # 列出所有窗口
            print("\n当前所有可见窗口:")
            print("-" * 40)
            try:
                all_windows = gw.getAllWindows()
                visible = [(i, w) for i, w in enumerate(all_windows) if w.visible and w.title]
                for idx, w in visible:
                    print(f"  [{idx}] {w.title}")
                print("-" * 40)
            except Exception as e:
                print(f"获取窗口列表失败: {e}")
                all_windows = []

            title_input = input("输入窗口标题关键字或编号: ").strip()
            if title_input.isdigit():
                idx = int(title_input)
                if 0 <= idx < len(all_windows):
                    w = all_windows[idx]
                    self.capture_monitor = {
                        "left": w.left, "top": w.top,
                        "width": w.width, "height": w.height,
                    }
                    self.game_hwnd = int(w._hWnd)
                    print(f"[截图] 已选择窗口: {w.title} (hwnd={self.game_hwnd})")
                    return None
            elif title_input:
                matches = gw.getWindowsWithTitle(title_input)
                if matches:
                    w = matches[0]
                    self.capture_monitor = {
                        "left": w.left, "top": w.top,
                        "width": w.width, "height": w.height,
                    }
                    self.game_hwnd = int(w._hWnd)
                    print(f"[截图] 已选择窗口: {w.title} (hwnd={self.game_hwnd})")
                    return None
            print("[截图] 未匹配到窗口，将使用全屏截图")
            return None

        elif choice == '2':
            print("\n即将截取全屏，请在弹出的窗口中用鼠标拖拽选择游戏区域...")
            print("操作: 鼠标拖拽选区 → 按空格或回车确认 → 按C取消重选")
            input("准备好后按回车截图...")

            monitor = self.sct.monitors[1]
            screenshot = self.sct.grab(monitor)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            window_name = "选择游戏区域 - 拖拽选取后按空格/回车确认, C取消"
            x, y, w, h = cv2.selectROI(window_name, img, fromCenter=False, showCrosshair=True)
            cv2.destroyAllWindows()

            if w == 0 or h == 0:
                print("[截图] 未选择区域，将使用全屏截图")
                return img  # 仍返回全屏截图供后续复用
            else:
                self.capture_monitor = {
                    "left": int(monitor["left"]) + int(x),
                    "top": int(monitor["top"]) + int(y),
                    "width": int(w),
                    "height": int(h),
                }
                print(f"[截图] 已选择区域: left={self.capture_monitor['left']}, "
                      f"top={self.capture_monitor['top']}, "
                      f"宽={self.capture_monitor['width']}, 高={self.capture_monitor['height']}")
                return img[y:y+h, x:x+w]  # 返回裁剪后的图像
        else:
            print("[截图] 使用主显示器全屏截图")
            # 截一张图缓存供模板匹配复用
            try:
                monitor = self.sct.monitors[1]
                screenshot = self.sct.grab(monitor)
                img = np.array(screenshot)
                return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            except Exception:
                return None

    def capture(self):
        """截图"""
        try:
            monitor = self.capture_monitor or self.sct.monitors[1]
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
            self.action_history.append("idle")
            return "idle"

        mx, my, mw, mh = nearest
        monster_x = mx + mw // 2
        monster_y = my + mh // 2
        px, py = player_pos
        dist = abs(monster_x - px)
        height_diff = py - monster_y  # 正值=怪物在上方, 负值=怪物在下方

        # 怪物在上方超过50px
        if height_diff > 50:
            direction = Key.left if monster_x < px else Key.right
            if self.has_dash:
                try:
                    self._key_down(direction)
                    time.sleep(0.05)
                    self._press(self.dash_key, 0.1)
                finally:
                    self._key_up(direction)
                self.action_history.append("dash_up")
                return "dash_up"
            else:
                try:
                    self._key_down(direction)
                    time.sleep(0.05)
                    self._press(self.jump_key, 0.05)
                    self._press(self.jump_key, 0.05)
                finally:
                    self._key_up(direction)
                self.action_history.append("double_jump")
                return "double_jump"

        # 怪物在下方超过30px
        if height_diff < -30:
            if self.has_dash:
                try:
                    self._key_down(Key.down)
                    time.sleep(0.05)
                    self._press(self.dash_key, 0.1)
                finally:
                    self._key_up(Key.down)
                self.action_history.append("dash_down")
                return "dash_down"
            else:
                try:
                    self._key_down(Key.down)
                    time.sleep(0.05)
                    self._press(self.jump_key, 0.1)
                finally:
                    self._key_up(Key.down)
                self.action_history.append("jump_down")
                return "jump_down"

        # 水平攻击范围
        if dist <= self.attack_range:
            key = random.choice(self.skill_keys) if random.random() < 0.3 else self.attack_key
            self._press(key)
            self.action_history.append("attack")
            return "attack"
        else:
            if monster_x < px:
                self._press(Key.left, 0.2)
                self.action_history.append("left")
                return "left"
            else:
                self._press(Key.right, 0.2)
                self.action_history.append("right")
                return "right"
    
    def _press(self, key, duration=0.1):
        """按键 - 使用 PostMessage 或 pynput"""
        try:
            self._key_down(key)
            time.sleep(duration)
        finally:
            self._key_up(key)
        time.sleep(random.uniform(0.05, 0.15))

    def release_all_keys(self):
        """释放所有可能被按下的按键"""
        for key in [Key.left, Key.right, Key.up, Key.down,
                    Key.space, Key.shift, Key.ctrl, Key.alt]:
            self._key_up(key)
        for key in [self.attack_key] + self.skill_keys:
            self._key_up(key)
        if self.dash_key:
            self._key_up(self.dash_key)
    
    def check_stuck(self):
        """检查卡死 - 基于动作历史而非位置（位置是估算值不可靠）"""
        if len(self.action_history) < 30:
            return False
        recent = list(self.action_history)[-30:]
        attack_count = recent.count("attack") + recent.count("dash_up") + recent.count("double_jump")
        move_count = recent.count("left") + recent.count("right")
        # 30帧内没有任何攻击或移动，可能卡死
        if attack_count == 0 and move_count < 3:
            print("[异常] 长时间无攻击无移动，尝试恢复...")
            for _ in range(3):
                self._press(self.jump_key, 0.1)
                self._press(Key.left if random.random()<0.5 else Key.right, 0.3)
            self.action_history.clear()
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

            # PostMessage 直发按键，无需每帧切前台
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
        self._select_template(img)

    def _select_template(self, img):
        """在截图上让用户框选怪物模板"""
        print("请在弹出的窗口中框选怪物区域 (空格/回车确认, C取消)")
        x, y, w, h = cv2.selectROI("框选怪物模板", img, fromCenter=False, showCrosshair=True)
        cv2.destroyAllWindows()

        if w == 0 or h == 0:
            print("[跳过] 未选择区域")
            return

        template = img[y:y+h, x:x+w]
        path = f"template_{int(time.time())}.png"
        cv2.imwrite(path, template)
        self.templates.append(template)
        print(f"已保存模板: {path} ({w}x{h})")
    
    def setup(self):
        """初始化"""
        print("\n" + "="*40)
        print("冒险岛图像识别自动刷怪")
        print("="*40)

        # 截图区域
        cached_img = self._setup_capture()

        # 检测模式
        mode = input("\n检测模式 (c=颜色/t=模板): ").strip().lower()
        self.detect_mode = "template" if mode == 't' else "color"

        if self.detect_mode == "template":
            if cached_img is not None:
                print("使用之前的截图，请在图像中框选怪物模板")
                self._select_template(cached_img)
                while input("添加更多模板? (y/n): ") == 'y':
                    self.capture_template()
            else:
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
        if self.game_hwnd:
            print(f"[PostMessage] 已绑定窗口句柄: {self.game_hwnd}")
        else:
            print("[警告] 未获取到窗口句柄，将使用普通按键（需游戏在前台）")
        print("按 F10 开始，ESC 停止\n")
    
    def start(self):
        """开始"""
        self.stop_flag = False

        print("\n3秒后开始... (请切换到游戏窗口)")
        for i in range(3, 0, -1):
            print(i)
            time.sleep(1)

        # 倒计时结束后切到游戏窗口，并更新句柄
        self._bring_game_to_front()

    def _bring_game_to_front(self):
        """强制将游戏窗口切到前台"""
        target = None
        if self.capture_monitor:
            try:
                cx = self.capture_monitor["left"] + self.capture_monitor["width"] // 2
                cy = self.capture_monitor["top"] + self.capture_monitor["height"] // 2
                windows_at = gw.getWindowsAt(cx, cy)
                if windows_at:
                    target = max(windows_at, key=lambda w: w.width * w.height)
            except Exception:
                pass

        if target is None:
            try:
                for title in ["冒险岛", "MapleStory", "新枫之谷", "Maple"]:
                    matches = gw.getWindowsWithTitle(title)
                    if matches:
                        target = matches[0]
                        break
            except Exception:
                pass

        # 更新 game_hwnd
        if target and hasattr(target, '_hWnd'):
            self.game_hwnd = int(target._hWnd)

        if not target:
            return

        try:
            hwnd = int(target._hWnd) if hasattr(target, '_hWnd') else 0
            if hwnd:
                fg = ctypes.windll.user32.GetForegroundWindow()
                if hwnd == fg:
                    return  # 已经在前台
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.05)
            else:
                target.activate()
                time.sleep(0.05)
        except Exception:
            pass
        
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
        try:
            self.run_loop()
        finally:
            self.release_all_keys()
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
