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
import json
import os
import shutil
from pathlib import Path
import ctypes
import ctypes.wintypes
from collections import deque

import cv2
import numpy as np
import mss
import pygetwindow as gw
from pynput import keyboard
from pynput.keyboard import Controller, Key


class ProfileManager:
    """配置和模板管理"""
    CONFIGS_DIR = "configs"
    TEMPLATES_DIR = "templates"

    @staticmethod
    def _ensure_dirs():
        os.makedirs(ProfileManager.CONFIGS_DIR, exist_ok=True)
        os.makedirs(ProfileManager.TEMPLATES_DIR, exist_ok=True)

    @staticmethod
    def list_profiles():
        ProfileManager._ensure_dirs()
        files = sorted(Path(ProfileManager.CONFIGS_DIR).glob("*.json"))
        return [f.stem for f in files]

    @staticmethod
    def save_profile(name, config):
        ProfileManager._ensure_dirs()
        config["name"] = name
        config["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
        path = Path(ProfileManager.CONFIGS_DIR) / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"[配置] 已保存: {name}")

    @staticmethod
    def load_profile(name):
        path = Path(ProfileManager.CONFIGS_DIR) / f"{name}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def delete_profile(name):
        path = Path(ProfileManager.CONFIGS_DIR) / f"{name}.json"
        if path.exists():
            path.unlink()
            print(f"[配置] 已删除: {name}")

    @staticmethod
    def list_template_sets():
        ProfileManager._ensure_dirs()
        dirs = sorted(Path(ProfileManager.TEMPLATES_DIR).iterdir())
        result = []
        for d in dirs:
            if d.is_dir():
                count = len(list(d.glob("*.png")))
                result.append((d.name, count))
        return result

    @staticmethod
    def load_templates(name):
        folder = Path(ProfileManager.TEMPLATES_DIR) / name
        if not folder.exists():
            return []
        templates = []
        for p in sorted(folder.glob("*.png")):
            tpl = cv2.imread(str(p))
            if tpl is not None:
                templates.append(tpl)
        return templates

    @staticmethod
    def save_template(template_img, template_set, index=None):
        ProfileManager._ensure_dirs()
        folder = Path(ProfileManager.TEMPLATES_DIR) / template_set
        folder.mkdir(parents=True, exist_ok=True)
        if index is None:
            existing = len(list(folder.glob("*.png")))
            index = existing + 1
        path = folder / f"template_{index}.png"
        cv2.imwrite(str(path), template_img)
        return str(path)

    @staticmethod
    def delete_template_set(name):
        folder = Path(ProfileManager.TEMPLATES_DIR) / name
        if folder.exists():
            shutil.rmtree(folder)
            print(f"[模板] 已删除模板集: {name}")


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

    @staticmethod
    def _find_game_hwnd_reliable():
        """通过 EnumWindows API 可靠查找冒险岛游戏窗口句柄（优先类名匹配）"""
        user32 = ctypes.windll.user32
        GAME_CLASSES = ["MapleStoryClass", "MapleStory"]
        GAME_TITLES = ["MapleStory", "冒险岛", "新枫之谷"]
        found = []

        def callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            title_buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title_buf, 256)
            title = title_buf.value
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cls = cls_buf.value
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w < 200 or h < 200:
                return True
            matched_class = cls in GAME_CLASSES
            matched_title = any(t in title for t in GAME_TITLES)
            if matched_class or matched_title:
                found.append({
                    'hwnd': hwnd, 'class': cls, 'title': title,
                    'area': w * h, 'by_class': matched_class
                })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        cb = WNDENUMPROC(callback)
        user32.EnumWindows(cb, 0)

        if not found:
            return None
        by_class = [f for f in found if f['by_class']]
        if by_class:
            best = max(by_class, key=lambda f: f['area'])
            print(f"[窗口] 类名匹配: {best['title']} (hwnd={best['hwnd']}, class={best['class']})")
            return best['hwnd']
        found.sort(key=lambda f: f['area'], reverse=True)
        best = found[0]
        print(f"[窗口] 标题匹配: {best['title']} (hwnd={best['hwnd']})")
        return best['hwnd']

    # 扩展键集合
    EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}

    def _get_vk(self, key):
        """获取虚拟键码"""
        if key in self.VK_MAP:
            return self.VK_MAP[key]
        if isinstance(key, str) and len(key) == 1:
            return ord(key.upper())
        return None

    def _key_down(self, key):
        """按下按键 - keybd_event 模拟硬件输入（DirectInput 可接收）"""
        vk = self._get_vk(key)
        if self.game_hwnd and vk:
            scan_code = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
            flags = 0x0008 if vk in self.EXTENDED_VKS else 0  # KEYEVENTF_EXTENDEDKEY
            ctypes.windll.user32.keybd_event(vk, scan_code, flags, 0)
        else:
            self.controller.press(key)

    def _key_up(self, key):
        """释放按键"""
        vk = self._get_vk(key)
        if self.game_hwnd and vk:
            scan_code = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
            flags = 0x0002 | (0x0008 if vk in self.EXTENDED_VKS else 0)  # KEYEVENTF_KEYUP | EXTENDEDKEY
            ctypes.windll.user32.keybd_event(vk, scan_code, flags, 0)
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
            # 即使窗口截图选择失败，也尝试可靠查找游戏句柄
            hwnd = self._find_game_hwnd_reliable()
            if hwnd:
                self.game_hwnd = hwnd
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
                # 可靠查找游戏窗口句柄
                hwnd = self._find_game_hwnd_reliable()
                if hwnd:
                    self.game_hwnd = hwnd
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
        """模板匹配 - 灰度多目标检测"""
        if not self.templates:
            return []
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        monsters = []
        for tpl_color in self.templates:
            tpl = cv2.cvtColor(tpl_color, cv2.COLOR_BGR2GRAY) if len(tpl_color.shape) == 3 else tpl_color
            for scale in [0.85, 1.0, 1.15]:
                resized = cv2.resize(tpl, None, fx=scale, fy=scale)
                rh, rw = resized.shape[:2]
                if rh > gray.shape[0] or rw > gray.shape[1]:
                    continue
                result = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
                # 自适应峰值间隔
                sep = max(3, int(min(rw, rh) * 0.4))
                if sep % 2 == 0:
                    sep += 1
                dilated = cv2.dilate(result, np.ones((sep, sep)))
                peaks = (result == dilated) & (result >= 0.70)
                for y, x in zip(*np.where(peaks)):
                    monsters.append((int(x), int(y), int(rw), int(rh)))
        return self._nms(monsters)
    
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

    def _nms(self, boxes, threshold=0.3):
        """NMS 去重"""
        if not boxes:
            return boxes
        boxes = sorted(boxes, key=lambda b: b[2]*b[3], reverse=True)
        result = []
        for box in boxes:
            keep = True
            for kept in result:
                x1,y1,w1,h1 = box; x2,y2,w2,h2 = kept
                xi1,yi1 = max(x1,x2), max(y1,y2)
                xi2,yi2 = min(x1+w1,x2+w2), min(y1+h1,y2+h2)
                inter = max(0,xi2-xi1)*max(0,yi2-yi1)
                union = w1*h1+w2*h2-inter
                if union > 0 and inter/union > threshold:
                    keep = False; break
            if keep:
                result.append(box)
        return result

    def get_nearest(self, player_pos, monsters):
        """找怪物最密集的簇中心"""
        if not monsters:
            return None

        if len(monsters) <= 2:
            # 少量怪物直接取最近的
            return min(monsters, key=lambda m: abs(m[0]+m[2]//2 - player_pos[0]))

        # BFS 聚类找最密集的簇
        centers = [(m[0]+m[2]//2, m[1]+m[3]//2) for m in monsters]
        n = len(centers)
        visited = [False] * n
        best_cluster = []

        for i in range(n):
            if visited[i]:
                continue
            cluster = [i]
            visited[i] = True
            queue = [i]
            while queue:
                curr = queue.pop(0)
                for j in range(n):
                    if visited[j]:
                        continue
                    if abs(centers[curr][0]-centers[j][0]) < 120 and abs(centers[curr][1]-centers[j][1]) < 120:
                        visited[j] = True
                        cluster.append(j)
                        queue.append(j)
            if len(cluster) > len(best_cluster):
                best_cluster = cluster

        # 返回簇中心的怪物
        px = player_pos[0]
        nearest_in_cluster = min(best_cluster,
            key=lambda i: abs(centers[i][0] - px))
        return monsters[nearest_in_cluster]
    
    def action(self, player_pos, monsters):
        """按高度分层决策：同层优先 → 下落穿台 → 上跳攻击"""
        if not monsters:
            self.action_history.append("idle")
            return "idle"

        px, py = player_pos

        # 按高度分层：同层 / 上方 / 下方
        SAME_H = 50
        same_layer, above_layer, below_layer = [], [], []
        for m in monsters:
            mc_y = m[1] + m[3] // 2
            diff = py - mc_y  # 正值=怪物在上方
            if abs(diff) <= SAME_H:
                same_layer.append(m)
            elif diff > SAME_H:
                above_layer.append(m)
            else:
                below_layer.append(m)

        # === 优先级1: 同层有怪 → 攻击或移向怪物 ===
        if same_layer:
            target = self.get_nearest(player_pos, same_layer)
            mx, my, mw, mh = target
            monster_x = mx + mw // 2
            dist = abs(monster_x - px)

            if dist <= self.attack_range:
                key = random.choice(self.skill_keys) if random.random() < 0.5 else self.attack_key
                self._press(key)
                self.action_history.append("attack")
                return "attack"
            else:
                going_left = monster_x < px
                if self._is_stuck(going_left):
                    going_left = not going_left
                if going_left:
                    self._press(Key.left, 0.1)
                    self.action_history.append("left")
                    return "left"
                else:
                    self._press(Key.right, 0.1)
                    self.action_history.append("right")
                    return "right"

        # === 优先级2: 同层没怪，下方有怪 → 下落穿台 ===
        if below_layer:
            try:
                self._key_down(Key.down)
                self._press(self.jump_key)
            finally:
                self._key_up(Key.down)
            self.action_history.append("drop_down")
            return "drop_down"

        # === 优先级3: 只有上方有怪 → 上跳攻击 ===
        if above_layer:
            target = self.get_nearest(player_pos, above_layer)
            mx, my, mw, mh = target
            monster_x = mx + mw // 2
            direction = Key.left if monster_x < px else Key.right
            try:
                self._key_down(direction)
                self._key_down(Key.up)          # 按住上键
                self._press(self.jump_key)      # 起跳
                self._press(self.jump_key)      # 二段跳（上键+跳=更高）
                self._press(self.attack_key)    # 空中攻击
            finally:
                self._key_up(Key.up)
                self._key_up(direction)
            self.action_history.append("jump_attack_up")
            return "jump_attack_up"

        self.action_history.append("idle")
        return "idle"

    def _is_stuck(self, going_left):
        """撞墙检测：最近连续同方向超过10次"""
        if not hasattr(self, '_move_dir_log'):
            self._move_dir_log = deque(maxlen=15)
        self._move_dir_log.append("left" if going_left else "right")
        if len(self._move_dir_log) < 10:
            return False
        recent = list(self._move_dir_log)[-10:]
        return all(d == recent[0] for d in recent)
    
    def _press(self, key, duration=0.03):
        """按键"""
        try:
            self._key_down(key)
            time.sleep(duration)
        finally:
            self._key_up(key)

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
            if elapsed < 0.03:  # 最快约30fps
                time.sleep(0.08 - elapsed)
    
    def capture_template(self):
        """截图保存模板"""
        input("对准怪物后按回车截图...")
        img = self.capture()
        if img is None:
            return
        self._select_template(img)

    def _select_template(self, img, template_set=None):
        """在截图上让用户框选怪物模板"""
        print("请在弹出的窗口中框选怪物区域 (空格/回车确认, C取消)")
        x, y, w, h = cv2.selectROI("框选怪物模板", img, fromCenter=False, showCrosshair=True)
        cv2.destroyAllWindows()

        if w == 0 or h == 0:
            print("[跳过] 未选择区域")
            return

        template = img[y:y+h, x:x+w]
        if template_set:
            path = ProfileManager.save_template(template, template_set)
        else:
            path = f"template_{int(time.time())}.png"
            cv2.imwrite(path, template)
        self.templates.append(template)
        print(f"已保存模板: {path} ({w}x{h})")

    def setup(self):
        """初始化 - 支持配置保存/加载"""
        print("\n" + "="*40)
        print("冒险岛图像识别自动刷怪")
        print("="*40)

        # ====== 配置选择 ======
        profiles = ProfileManager.list_profiles()
        if profiles:
            print("\n已保存的配置:")
            for i, name in enumerate(profiles, 1):
                print(f"  [{i}] {name}")
            print("\n请选择:")
            print("  编号: 使用已保存的配置")
            print("  n: 新建配置")
            print("  d: 删除配置")
            while True:
                choice = input("> ").strip().lower()
                if choice == 'n':
                    break
                elif choice == 'd':
                    for i, name in enumerate(profiles, 1):
                        print(f"  [{i}] {name}")
                    dc = input("要删除的编号 (0取消): ").strip()
                    if dc.isdigit() and 1 <= int(dc) <= len(profiles):
                        dn = profiles[int(dc)-1]
                        ProfileManager.delete_profile(dn)
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(profiles):
                    if self._load_profile(profiles[int(choice)-1]):
                        return
                    print("[配置] 加载失败，进入新建流程")
                    break
                print("输入无效")

        # ====== 新建配置 ======
        cached_img = self._setup_capture()

        # 检测模式
        mode = input("\n检测模式 (c=颜色/t=模板): ").strip().lower()
        self.detect_mode = "template" if mode == 't' else "color"
        template_set = None

        if self.detect_mode == "template":
            # 优先选择已有模板集
            tpl_sets = ProfileManager.list_template_sets()
            if tpl_sets:
                print("\n已保存的模板集:")
                for i, (ts_name, count) in enumerate(tpl_sets, 1):
                    print(f"  [{i}] {ts_name} ({count}个模板)")
                print(f"  [n] 新建模板集")
                tpl_choice = input("请选择: ").strip().lower()
                if tpl_choice.isdigit() and 1 <= int(tpl_choice) <= len(tpl_sets):
                    ts_name = tpl_sets[int(tpl_choice)-1][0]
                    templates = ProfileManager.load_templates(ts_name)
                    for tpl in templates:
                        self.templates.append(tpl)
                    print(f"[模板] 已加载 '{ts_name}' ({len(templates)}个模板)")
                else:
                    template_set = input("新模板集名称: ").strip() or f"templates_{int(time.time())}"
                    if cached_img is not None:
                        self._select_template(cached_img, template_set)
                    while input("添加更多模板? (y/n): ") == 'y':
                        img = self.capture()
                        if img is not None:
                            self._select_template(img, template_set)
            else:
                template_set = input("新模板集名称: ").strip() or f"templates_{int(time.time())}"
                if cached_img is not None:
                    self._select_template(cached_img, template_set)
                while input("添加更多模板? (y/n): ") == 'y':
                    img = self.capture()
                    if img is not None:
                        self._select_template(img, template_set)

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

        # 攻击键
        attack_key = input("攻击键 (默认x): ").strip() or 'x'
        self.attack_key = attack_key

        # 技能键
        skills_input = input("技能键 (逗号分隔, 默认a,s): ").strip()
        self.skill_keys = [s.strip() for s in skills_input.split(',')] if skills_input else ['a', 's']

        # 位移技能
        has_dash_input = input("是否有位移技能? (y/n, 默认n): ").strip().lower()
        dash_key_str = None
        if has_dash_input == 'y':
            dash_key_str = input("位移技能键 (默认f): ").strip().lower() or 'f'
            self.has_dash = True
            self.dash_key = KEY_MAP.get(dash_key_str, dash_key_str)
            print(f"[配置] 位移技能已启用, 按键: {dash_key_str}")

        print(f"\n配置完成: {'模板' if self.detect_mode=='template' else '颜色'}检测 + {'远程' if self.combat_type=='ranged' else '近战'}")
        if self.game_hwnd:
            print(f"[PostMessage] 已绑定窗口句柄: {self.game_hwnd}")
        print("按 F10 开始，ESC 停止\n")

        # ====== 保存配置 ======
        save = input("是否保存配置? (y/n): ").strip().lower()
        if save == 'y':
            name = input("配置名称 (如: 神秘河_花蛇): ").strip()
            if name:
                config = {
                    "detect_mode": self.detect_mode,
                    "template_set": template_set,
                    "combat_type": self.combat_type,
                    "attack_range": self.attack_range,
                    "attack_key": self.attack_key,
                    "skill_keys": self.skill_keys,
                    "jump_key": jump_input,
                    "has_dash": self.has_dash,
                    "dash_key": dash_key_str,
                }
                if self.capture_monitor:
                    config["capture_monitor"] = self.capture_monitor
                ProfileManager.save_profile(name, config)

    def _load_profile(self, name):
        """从配置文件恢复设置"""
        config = ProfileManager.load_profile(name)
        if not config:
            return False

        # 截图区域
        if config.get("capture_monitor"):
            self.capture_monitor = config["capture_monitor"]

        # 检测模式
        self.detect_mode = config.get("detect_mode", "color")
        if self.detect_mode == "template":
            tpl_set = config.get("template_set")
            if tpl_set:
                templates = ProfileManager.load_templates(tpl_set)
                for tpl in templates:
                    self.templates.append(tpl)
                print(f"[模板] 已加载 '{tpl_set}' ({len(templates)}个模板)")

        # 战斗
        self.combat_type = config.get("combat_type", "melee")
        self.attack_range = config.get("attack_range", 80)
        self.attack_key = config.get("attack_key", "x")
        self.skill_keys = config.get("skill_keys", ["a", "s"])

        KEY_MAP = {
            'space': Key.space, 'shift': Key.shift, 'ctrl': Key.ctrl, 'alt': Key.alt,
            'tab': Key.tab, 'enter': Key.enter, 'up': Key.up, 'down': Key.down,
            'left': Key.left, 'right': Key.right,
        }
        jump_str = config.get("jump_key", "space")
        self.jump_key = KEY_MAP.get(jump_str, jump_str)

        if config.get("has_dash"):
            dk = config.get("dash_key", "f") or "f"
            self.has_dash = True
            self.dash_key = KEY_MAP.get(dk, dk)
        else:
            self.has_dash = False

        # 窗口句柄
        hwnd = self._find_game_hwnd_reliable()
        if hwnd:
            self.game_hwnd = hwnd

        print(f"\n[配置] 已加载: {name}")
        print(f"  检测: {'模板' if self.detect_mode=='template' else '颜色'} | "
              f"战斗: {'远程' if self.combat_type=='ranged' else '近战'} | "
              f"位移: {'是' if self.has_dash else '否'}")
        if self.game_hwnd:
            print(f"  窗口句柄: {self.game_hwnd}")
        print("按 F10 开始，ESC 停止\n")
        return True
    
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
        # 通过 EnumWindows 可靠查找游戏窗口
        hwnd = self._find_game_hwnd_reliable()
        if hwnd:
            self.game_hwnd = hwnd
        else:
            # 回退：手动区域坐标查找
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
            if target and hasattr(target, '_hWnd'):
                self.game_hwnd = int(target._hWnd)

        if not self.game_hwnd:
            return

        try:
            fg = ctypes.windll.user32.GetForegroundWindow()
            if self.game_hwnd == fg:
                return
            ctypes.windll.user32.ShowWindow(self.game_hwnd, 9)
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            ctypes.windll.user32.SetForegroundWindow(self.game_hwnd)
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
