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
import os
import shutil
import ctypes
import ctypes.wintypes
import cv2
import numpy as np
import mss
import pygetwindow as gw
from pathlib import Path
from datetime import datetime
from collections import deque
from pynput import keyboard
from pynput.keyboard import Controller, Key


class ProfileManager:
    """配置和模板集管理"""
    CONFIGS_DIR = "configs"
    TEMPLATES_DIR = "templates"

    @staticmethod
    def ensure_dirs():
        os.makedirs(ProfileManager.CONFIGS_DIR, exist_ok=True)
        os.makedirs(ProfileManager.TEMPLATES_DIR, exist_ok=True)

    # ---- 配置 ----
    @staticmethod
    def list_profiles():
        ProfileManager.ensure_dirs()
        files = sorted(Path(ProfileManager.CONFIGS_DIR).glob("*.json"))
        return [f.stem for f in files]

    @staticmethod
    def save_profile(name, config):
        ProfileManager.ensure_dirs()
        config["name"] = name
        config["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    # ---- 模板集 ----
    @staticmethod
    def list_template_sets():
        ProfileManager.ensure_dirs()
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
                gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
                templates.append(gray)
        return templates

    @staticmethod
    def save_template(template_img, template_set, index=None):
        """保存模板图片到模板集文件夹，返回文件路径"""
        ProfileManager.ensure_dirs()
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


class ScreenCapture:
    """屏幕捕获模块 - 使用mss实现高性能截图"""

    def __init__(self):
        self.sct = mss.mss()
        self.game_window = None
        self.game_hwnd = None      # 游戏窗口句柄
        self.manual_region = None  # 手动指定的截图区域

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
        # 优先类名匹配，其次面积最大的标题匹配
        by_class = [f for f in found if f['by_class']]
        if by_class:
            best = max(by_class, key=lambda f: f['area'])
            print(f"[窗口] 类名匹配: {best['title']} (hwnd={best['hwnd']}, class={best['class']})")
            return best['hwnd']
        found.sort(key=lambda f: f['area'], reverse=True)
        best = found[0]
        print(f"[窗口] 标题匹配: {best['title']} (hwnd={best['hwnd']})")
        return best['hwnd']

    def list_windows(self):
        """列出所有可见窗口供用户选择"""
        print("\n当前所有可见窗口:")
        print("-" * 50)
        try:
            all_windows = gw.getAllWindows()
            visible = [(i, w) for i, w in enumerate(all_windows) if w.visible and w.title]
            for idx, w in visible:
                print(f"  [{idx}] {w.title}")
            print("-" * 50)
            return all_windows
        except Exception as e:
            print(f"[屏幕] 获取窗口列表失败: {e}")
            return []

    def find_game_window(self, window_title=None):
        """查找游戏窗口，优先通过 EnumWindows 可靠匹配"""
        # 优先使用 EnumWindows + 类名匹配
        hwnd = self._find_game_hwnd_reliable()
        if hwnd:
            self.game_hwnd = hwnd
            try:
                all_windows = gw.getAllWindows()
                for w in all_windows:
                    if int(w._hWnd) == hwnd:
                        self.game_window = w
                        print(f"[屏幕] 已绑定游戏窗口: {w.title} (hwnd={self.game_hwnd})")
                        return True
            except Exception:
                pass
            print(f"[屏幕] 已绑定游戏窗口句柄: {self.game_hwnd}")
            return True

        # 回退：用户手动输入
        all_windows = self.list_windows()
        if window_title is None:
            window_title = input("\n请输入游戏窗口标题关键字 (直接回车跳过): ").strip()

        if window_title:
            matches = gw.getWindowsWithTitle(window_title)
            if matches:
                self.game_window = matches[0]
                self.game_hwnd = int(self.game_window._hWnd)
                print(f"[屏幕] 找到窗口: {self.game_window.title} (hwnd={self.game_hwnd})")
                return True
            else:
                print(f"[屏幕] 未找到包含 '{window_title}' 的窗口")

        # 让用户输入窗口编号
        if all_windows:
            try:
                idx_input = input("请输入窗口编号 (从上面的列表中选择，直接回车跳过): ").strip()
                if idx_input.isdigit():
                    idx = int(idx_input)
                    if 0 <= idx < len(all_windows) and all_windows[idx].title:
                        self.game_window = all_windows[idx]
                        self.game_hwnd = int(self.game_window._hWnd)
                        print(f"[屏幕] 已选择窗口: {self.game_window.title} (hwnd={self.game_hwnd})")
                        return True
            except Exception:
                pass

        print("[屏幕] 未匹配到游戏窗口，将使用手动区域或全屏截图")
        return False

    def select_region_interactive(self):
        """截取全屏后让用户鼠标拖拽选择截图区域，返回全屏截图和选区后的裁剪图"""
        print("\n即将截取全屏，请在弹出的窗口中用鼠标拖拽选择游戏区域...")
        print("操作: 鼠标拖拽选区 → 按空格或回车确认 → 按C取消重选")
        input("准备好后按回车截图...")

        # 截取全屏
        monitor = self.sct.monitors[1]
        screenshot = self.sct.grab(monitor)
        img = np.array(screenshot)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        # 用 OpenCV 让用户框选区域
        window_name = "选择游戏区域 - 拖拽选取后按空格/回车确认, C取消"
        x, y, w, h = cv2.selectROI(window_name, img, fromCenter=False, showCrosshair=True)
        cv2.destroyAllWindows()

        if w == 0 or h == 0:
            print("[屏幕] 未选择区域，将使用全屏截图")
            return img  # 返回全屏截图供后续复用

        # 添加全屏偏移量
        self.manual_region = {
            "left": int(monitor["left"]) + int(x),
            "top": int(monitor["top"]) + int(y),
            "width": int(w),
            "height": int(h),
        }
        print(f"[屏幕] 已选择区域: left={self.manual_region['left']}, "
              f"top={self.manual_region['top']}, "
              f"宽={self.manual_region['width']}, 高={self.manual_region['height']}")

        # 裁剪选区图像供后续复用
        cropped = img[y:y+h, x:x+w]
        return cropped

    def bring_to_front(self):
        """使用 Windows API 强制将游戏窗口切到前台"""
        # 通过 EnumWindows 可靠查找游戏窗口
        hwnd = self._find_game_hwnd_reliable()
        if hwnd:
            self.game_hwnd = hwnd
            try:
                all_windows = gw.getAllWindows()
                for w in all_windows:
                    if int(w._hWnd) == hwnd:
                        self.game_window = w
                        break
            except Exception:
                pass
        else:
            # 回退：手动区域坐标查找
            target = self.game_window
            if target is None and self.manual_region:
                try:
                    cx = self.manual_region["left"] + self.manual_region["width"] // 2
                    cy = self.manual_region["top"] + self.manual_region["height"] // 2
                    windows_at = gw.getWindowsAt(cx, cy)
                    if windows_at:
                        target = max(windows_at, key=lambda w: w.width * w.height)
                except Exception:
                    pass
            if target and hasattr(target, '_hWnd'):
                self.game_window = target
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

    def capture(self, region=None):
        """
        捕获屏幕区域
        region: (left, top, width, height) 或 None捕获游戏窗口/全屏
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
            elif self.manual_region:
                monitor = dict(self.manual_region)
            elif self.game_window:
                monitor = {
                    "left": self.game_window.left,
                    "top": self.game_window.top,
                    "width": self.game_window.width,
                    "height": self.game_window.height
                }
            else:
                monitor = self.sct.monitors[1]

            screenshot = self.sct.grab(monitor)
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
        self.templates = []     # 模板图像列表（灰度）
        self.template_threshold = 0.70  # 模板匹配阈值
        self.scales = [0.85, 1.0, 1.15]  # 缩放比例（减少到3个提升速度）

        # 颜色检测参数
        self.color_ranges = {
            "red": [(0, 100, 100), (10, 255, 255)],
            "red2": [(160, 100, 100), (180, 255, 255)],
            "blue": [(100, 100, 100), (130, 255, 255)],
            "green": [(40, 100, 100), (80, 255, 255)],
            "yellow": [(20, 100, 100), (35, 255, 255)],
        }
        self.target_color = "red"
        self.min_contour_area = 500
        self.max_contour_area = 50000

    def set_mode(self, mode):
        if mode in ["template", "color"]:
            self.mode = mode
            print(f"[检测] 切换到模式: {mode}")
            return True
        return False

    def add_template(self, image_path):
        """添加模板图像（转灰度存储）"""
        template = cv2.imread(image_path)
        if template is not None:
            gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            self.templates.append(gray)
            print(f"[检测] 添加模板: {image_path}, 尺寸: {template.shape[:2]}")
            return True
        else:
            print(f"[检测] 无法加载模板: {image_path}")
            return False

    def detect(self, screenshot):
        """检测怪物位置，返回 [(x, y, w, h), ...]"""
        if screenshot is None:
            return []
        if self.mode == "template":
            return self._detect_by_template(screenshot)
        else:
            return self._detect_by_color(screenshot)

    def _detect_by_template(self, screenshot):
        """模板匹配 - 灰度多目标检测"""
        if not self.templates:
            return []

        gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        monsters = []

        for tpl in self.templates:
            for scale in self.scales:
                resized = cv2.resize(tpl, None, fx=scale, fy=scale)
                rh, rw = resized.shape[:2]
                if rh > gray.shape[0] or rw > gray.shape[1]:
                    continue

                result = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)

                # 自适应峰值间隔：用模板尺寸的 40% 作为最小间距
                # 重叠怪物之间仍有间距，不会合并成一个峰
                sep = max(3, int(min(rw, rh) * 0.4))
                if sep % 2 == 0:
                    sep += 1
                dilated = cv2.dilate(result, np.ones((sep, sep)))
                peaks = (result == dilated) & (result >= self.template_threshold)

                for y, x in zip(*np.where(peaks)):
                    monsters.append((int(x), int(y), int(rw), int(rh)))

        return self._apply_nms(monsters, threshold=0.3)

    def _detect_by_color(self, screenshot):
        """颜色+轮廓检测，大团重叠怪物自动拆分"""
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)

        if self.target_color == "red":
            mask1 = cv2.inRange(hsv, np.array(self.color_ranges["red"][0]),
                                np.array(self.color_ranges["red"][1]))
            mask2 = cv2.inRange(hsv, np.array(self.color_ranges["red2"][0]),
                                np.array(self.color_ranges["red2"][1]))
            mask = cv2.bitwise_or(mask1, mask2)
        else:
            cr = self.color_ranges.get(self.target_color, self.color_ranges["red"])
            mask = cv2.inRange(hsv, np.array(cr[0]), np.array(cr[1]))

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # 用距离变换+阈值拆分粘连的重叠怪物
        dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        _, markers = cv2.connectedComponents((dist > 3).astype(np.uint8))
        # 用分水岭拆分粘连
        markers = markers + 1
        markers[mask == 0] = 0
        bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        cv2.watershed(bgr, markers)

        monsters = []
        for label_id in range(2, markers.max() + 1):
            component = (markers == label_id).astype(np.uint8) * 255
            contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if self.min_contour_area < area < self.max_contour_area:
                    x, y, w, h = cv2.boundingRect(cnt)
                    if 0.3 < w / float(h) < 3.0:
                        monsters.append((x, y, w, h))
        return monsters

    def _apply_nms(self, boxes, threshold=0.3):
        """非极大值抑制"""
        if not boxes:
            return boxes
        boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)
        result = []
        for box in boxes:
            keep = True
            for kept in result:
                if self._iou(box, kept) > threshold:
                    keep = False
                    break
            if keep:
                result.append(box)
        return result

    @staticmethod
    def _iou(box1, box2):
        x1, y1, w1, h1 = box1
        x2, y2, w2, h2 = box2
        xi1, yi1 = max(x1, x2), max(y1, y2)
        xi2, yi2 = min(x1 + w1, x2 + w2), min(y1 + h1, y2 + h2)
        inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        union = w1 * h1 + w2 * h2 - inter
        return inter / union if union > 0 else 0

    def set_color(self, color_name):
        if color_name in self.color_ranges:
            self.target_color = color_name
            print(f"[检测] 设置检测颜色: {color_name}")
            return True
        return False


class CombatStrategy:
    """战斗策略模块 - 支持近战/远程职业，PostMessage 直发按键"""

    # 虚拟键码映射
    VK_MAP = {
        Key.left: 0x25, Key.up: 0x26, Key.right: 0x27, Key.down: 0x28,
        Key.space: 0x20, Key.shift: 0x10, Key.ctrl: 0x11, Key.alt: 0x12,
        Key.tab: 0x09, Key.enter: 0x0D, Key.esc: 0x1B,
    }
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101

    def __init__(self):
        self.combat_type = "melee"
        self.attack_range = 50
        self.attack_key = 'x'
        self.skill_keys = ['a', 's']
        self.jump_key = Key.space
        self.has_dash = False
        self.dash_key = None
        self.controller = Controller()
        self.game_hwnd = None  # 游戏窗口句柄，用于 PostMessage

    def set_game_hwnd(self, hwnd):
        """设置游戏窗口句柄"""
        self.game_hwnd = hwnd

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

    def set_dash(self, has_dash, dash_key=None):
        """设置位移技能"""
        self.has_dash = has_dash
        self.dash_key = dash_key

    def get_action(self, player_pos, monsters):
        """根据怪物高度分层决策：同层优先 → 下落穿台 → 上跳攻击"""
        if not monsters:
            return "idle", None

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
            cluster_center, cluster = self._find_densest_cluster(same_layer, radius=120)
            if cluster_center and cluster:
                cx = cluster_center[0]
                any_in_range = any(abs(m[0] + m[2] // 2 - px) <= self.attack_range for m in cluster)
                if any_in_range:
                    if random.random() < 0.5 and self.skill_keys:
                        return "skill", random.choice(self.skill_keys)
                    return "attack", self.attack_key
                # 同层但超出范围 → 移向簇（带撞墙换向）
                going_left = cx < px
                if self._is_stuck_direction(going_left):
                    going_left = not going_left
                return ("move_left", None) if going_left else ("move_right", None)
            # fallback: 移向最近同层怪
            target = min(same_layer, key=lambda m: abs(m[0] + m[2] // 2 - px))
            tx = target[0] + target[2] // 2
            going_left = tx < px
            if self._is_stuck_direction(going_left):
                going_left = not going_left
            return ("move_left", None) if going_left else ("move_right", None)

        # === 优先级2: 同层没怪，下方有怪 → 下落穿台 ===
        if below_layer:
            return "drop_down", None

        # === 优先级3: 只有上方有怪 → 上跳攻击 ===
        if above_layer:
            cluster_center, _ = self._find_densest_cluster(above_layer, radius=120)
            cx = cluster_center[0] if cluster_center else px
            direction = Key.left if cx < px else Key.right
            return "jump_attack_up", direction

        return "idle", None

    def _is_stuck_direction(self, going_left):
        """检测是否撞墙：最近连续同方向移动超过10次"""
        if not hasattr(self, '_move_log'):
            self._move_log = deque(maxlen=15)
        self._move_log.append("left" if going_left else "right")
        if len(self._move_log) < 10:
            return False
        recent = list(self._move_log)[-10:]
        return all(d == recent[0] for d in recent)

    def _find_densest_cluster(self, monsters, radius=120):
        """
        用简单 BFS 聚类找怪物最密集的簇
        返回: ((cx, cy), [(mx,my,mw,mh), ...]) 或 (None, [])
        """
        if not monsters:
            return None, []

        # 计算每个怪物的中心
        centers = [(m[0] + m[2] // 2, m[1] + m[3] // 2) for m in monsters]
        n = len(centers)
        visited = [False] * n
        best_cluster = []
        best_center = None

        for i in range(n):
            if visited[i]:
                continue
            # BFS 聚类
            cluster_idx = [i]
            visited[i] = True
            queue = [i]
            while queue:
                curr = queue.pop(0)
                ccx, ccy = centers[curr]
                for j in range(n):
                    if visited[j]:
                        continue
                    jcx, jcy = centers[j]
                    if abs(ccx - jcx) < radius and abs(ccy - jcy) < radius:
                        visited[j] = True
                        cluster_idx.append(j)
                        queue.append(j)

            cluster = [monsters[k] for k in cluster_idx]
            if len(cluster) > len(best_cluster):
                best_cluster = cluster
                # 簇中心 = 所有怪物中心的加权平均
                cx = sum(centers[k][0] for k in cluster_idx) // len(cluster_idx)
                cy = sum(centers[k][1] for k in cluster_idx) // len(cluster_idx)
                best_center = (cx, cy)

        return best_center, best_cluster

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
            self._press_key(Key.left, duration=0.1)

        elif action_type == "move_right":
            self._press_key(Key.right, duration=0.1)

        elif action_type == "attack":
            key = params or self.attack_key
            self._press_key(key)

        elif action_type == "skill":
            key = params or self.skill_keys[0]
            self._press_key(key)

        elif action_type == "jump_attack_up":
            # 上方怪物：方向键 + 上键 + 二段跳 + 攻击
            direction = params
            try:
                self._key_down(direction)
                self._key_down(Key.up)          # 按住上键
                self._press_key(self.jump_key)  # 起跳
                self._press_key(self.jump_key)  # 二段跳（上键+跳=更高）
                self._press_key(self.attack_key)  # 空中攻击
            finally:
                self._key_up(Key.up)
                self._key_up(direction)

        elif action_type == "jump_attack_down":
            try:
                self._key_down(Key.down)
                self._press_key(self.jump_key)  # 下落穿台
                self._press_key(self.attack_key)  # 攻击
            finally:
                self._key_up(Key.down)

        elif action_type == "drop_down":
            # 下落穿台：按下+跳，不攻击（到下层后再打）
            try:
                self._key_down(Key.down)
                self._press_key(self.jump_key)
            finally:
                self._key_up(Key.down)

        print(f"  [动作] {action_type}", end='\r')

    def release_all_keys(self):
        """释放所有可能被按下的按键"""
        for key in [Key.left, Key.right, Key.up, Key.down,
                    Key.space, Key.shift, Key.ctrl, Key.alt]:
            self._key_up(key)
        for key in [self.attack_key] + self.skill_keys:
            self._key_up(key)
        if self.dash_key:
            self._key_up(self.dash_key)

    def _press_key(self, key, duration=0.03):
        """按下并释放按键"""
        try:
            self._key_down(key)
            time.sleep(duration)
        finally:
            self._key_up(key)


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

        # 可配置跳跃键
        self.jump_key = Key.space

    def set_jump_key(self, key):
        """设置跳跃键"""
        self.jump_key = key
        
    def update_position(self, player_pos):
        """更新位置历史"""
        self.position_history.append(player_pos)
        
    def update_action(self, action_type):
        """更新动作历史"""
        self.action_history.append(action_type)
        
    def check_exceptions(self, current_time):
        """检查各种异常情况，返回异常类型和恢复建议

        注意：玩家位置是估算值（屏幕固定坐标），不是真实追踪，
        因此禁用基于位置的卡死/被击退检测，只保留基于动作的检测。
        """

        # 无怪物检测 - 长时间idle
        if len(self.action_history) >= self.no_action_threshold:
            recent_actions = list(self.action_history)[-self.no_action_threshold:]
            idle_count = recent_actions.count("idle")
            if idle_count > self.no_action_threshold * 0.8:  # 80%时间idle
                if current_time - self.last_recovery_time > 5:
                    self.last_recovery_time = current_time
                    return "no_monsters", "尝试移动寻找怪物"

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
                controller.press(self.jump_key)
                time.sleep(0.1)
                controller.release(self.jump_key)
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
        self.target_fps = 30
        self.frame_interval = 1.0 / self.target_fps
        
        # 统计数据
        self.frame_count = 0
        self.detection_count = 0
        self.start_time = None
        
    # 特殊键字符串到 Key 对象的映射
    KEY_MAP = {
        'space': Key.space, 'shift': Key.shift, 'ctrl': Key.ctrl, 'alt': Key.alt,
        'tab': Key.tab, 'enter': Key.enter, 'up': Key.up, 'down': Key.down,
        'left': Key.left, 'right': Key.right,
    }

    def _parse_key(self, key_str):
        """将用户输入的按键字符串转换为 pynput Key 对象"""
        return self.KEY_MAP.get(key_str, key_str)

    def setup(self):
        """初始化设置 - 支持加载已保存配置"""
        print("\n" + "="*50)
        print("冒险岛图像识别自动刷怪 - 初始化")
        print("="*50 + "\n")

        # ============ 配置选择 ============
        loaded_config = self._select_profile()
        if loaded_config:
            self._apply_config(loaded_config)
            return

        # ============ 新建配置流程 ============
        cached_img = None
        print("\n截图区域设置:")
        print("1. 自动查找游戏窗口")
        print("2. 鼠标拖拽选择区域")
        print("3. 使用全屏截图")
        region_choice = input("请选择 (1-3, 默认3): ").strip() or '3'

        if region_choice == '2':
            cached_img = self.screen.select_region_interactive()
        else:
            if region_choice == '1':
                self.screen.find_game_window()
            cached_img = self.screen.capture()
            print("[屏幕] 已截取初始图像")

        # 选择检测模式
        print("\n选择怪物检测模式:")
        print("1. 模板匹配 (需要先截图保存怪物图片)")
        print("2. 颜色检测 (基于怪物颜色识别)")
        choice = input("请输入 (1-2): ").strip()

        detect_mode = "template" if choice == "1" else "color"
        template_set_name = None

        if detect_mode == "template":
            self.detector.set_mode("template")
            template_set_name = self._setup_template_mode(cached_img)
        else:
            self.detector.set_mode("color")
            self._setup_color_mode()

        # 绑定窗口句柄
        if self.screen.game_hwnd:
            self.combat.set_game_hwnd(self.screen.game_hwnd)
            print(f"[战斗] 已绑定游戏窗口句柄: {self.screen.game_hwnd}")
        else:
            print("[警告] 未获取到游戏窗口句柄，将使用普通按键发送")

        # 战斗类型
        print("\n选择职业类型:")
        print("1. 近战 (战士/飞侠等)")
        print("2. 远程 (法师/弓箭手等)")
        combat_choice = input("请输入 (1-2): ").strip()
        combat_type = "ranged" if combat_choice == "2" else "melee"
        default_range = 250 if combat_type == "ranged" else 80
        attack_range = input(f"攻击距离 (默认{default_range}像素): ").strip()
        attack_range = int(attack_range) if attack_range.isdigit() else default_range
        self.combat.set_combat_type(combat_type, attack_range)

        # 按键设置
        print("\n设置按键 (直接回车使用默认值):")
        attack = input("攻击键 (默认x): ").strip() or 'x'
        skills_input = input("技能键 (多个用逗号分隔，默认a,s): ").strip()
        skills = [s.strip() for s in skills_input.split(',')] if skills_input else ['a', 's']
        jump_input = input("跳跃键 (默认space): ").strip().lower() or 'space'
        jump_key = self._parse_key(jump_input)
        self.combat.set_keys(attack=attack, skills=skills, jump=jump_key)
        self.exception_handler.set_jump_key(jump_key)

        has_dash_input = input("是否有位移技能? (y/n, 默认n): ").strip().lower()
        dash_key = None
        if has_dash_input == 'y':
            dash_input = input("位移技能键 (默认f): ").strip().lower() or 'f'
            dash_key = self._parse_key(dash_input)
            self.combat.set_dash(True, dash_key)
        else:
            self.combat.set_dash(False)

        print("\n" + "="*50)
        print("初始化完成！")
        print(f"检测模式: {'模板匹配' if self.detector.mode=='template' else '颜色检测'}")
        print(f"战斗类型: {'近战' if self.combat.combat_type=='melee' else '远程'}")
        print(f"位移技能: {'已启用' if self.combat.has_dash else '未启用'}")
        print("按 F10 开始自动刷怪，ESC 停止")
        print("="*50 + "\n")

        # ============ 保存配置 ============
        save = input("\n是否保存当前配置? (y/n): ").strip().lower()
        if save == 'y':
            name = input("请输入配置名称 (如: 神秘河_花蛇): ").strip()
            if name:
                config = {
                    "capture_mode": region_choice,
                    "detect_mode": detect_mode,
                    "template_set": template_set_name,
                    "template_threshold": self.detector.template_threshold,
                    "target_color": self.detector.target_color,
                    "combat_type": combat_type,
                    "attack_range": attack_range,
                    "attack_key": attack,
                    "skill_keys": skills,
                    "jump_key": jump_input,
                    "has_dash": has_dash_input == 'y',
                    "dash_key": dash_input if has_dash_input == 'y' else None,
                }
                if self.screen.manual_region:
                    config["manual_region"] = self.screen.manual_region
                ProfileManager.save_profile(name, config)

    def _select_profile(self):
        """配置选择菜单，返回配置dict或None"""
        profiles = ProfileManager.list_profiles()
        if not profiles:
            print("[配置] 未找到已保存配置，将进入新建流程")
            return None

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
                return None
            elif choice == 'd':
                self._delete_profile_menu(profiles)
                return None
            elif choice.isdigit() and 1 <= int(choice) <= len(profiles):
                name = profiles[int(choice) - 1]
                config = ProfileManager.load_profile(name)
                if config:
                    print(f"[配置] 已加载: {name}")
                    return config
                else:
                    print("[配置] 加载失败")
                    return None
            print("输入无效，请重试")

    def _delete_profile_menu(self, profiles):
        """删除配置菜单"""
        if not profiles:
            print("[配置] 没有可删除的配置")
            return
        for i, name in enumerate(profiles, 1):
            print(f"  [{i}] {name}")
        choice = input("要删除的编号 (0取消): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(profiles):
            name = profiles[int(choice) - 1]
            confirm = input(f"确认删除配置 '{name}'? 同时删除关联模板集? (y=全部/n=仅配置/0取消): ").strip().lower()
            if confirm == 'y':
                config = ProfileManager.load_profile(name)
                ProfileManager.delete_profile(name)
                if config and config.get("template_set"):
                    ProfileManager.delete_template_set(config["template_set"])
            elif confirm == 'n':
                ProfileManager.delete_profile(name)

    def _apply_config(self, config):
        """从配置dict恢复所有设置"""
        # 截图区域
        capture_mode = config.get("capture_mode", "3")
        if capture_mode == '2' and config.get("manual_region"):
            self.screen.manual_region = config["manual_region"]
        elif capture_mode == '1':
            self.screen.find_game_window()

        # 检测模式
        detect_mode = config.get("detect_mode", "color")
        self.detector.set_mode(detect_mode)
        if detect_mode == "template":
            tpl_set = config.get("template_set")
            if tpl_set:
                templates = ProfileManager.load_templates(tpl_set)
                for tpl in templates:
                    self.detector.templates.append(tpl)
                print(f"[配置] 已加载模板集 '{tpl_set}' ({len(templates)}个模板)")
            self.detector.template_threshold = config.get("template_threshold", 0.70)
        else:
            color = config.get("target_color", "red")
            self.detector.set_color(color)

        # 窗口绑定
        hwnd = self.screen._find_game_hwnd_reliable()
        if hwnd:
            self.screen.game_hwnd = hwnd
            self.combat.set_game_hwnd(hwnd)

        # 战斗
        self.combat.set_combat_type(
            config.get("combat_type", "melee"),
            config.get("attack_range", 80)
        )
        jump_key = self._parse_key(config.get("jump_key", "space"))
        self.combat.set_keys(
            attack=config.get("attack_key", "x"),
            skills=config.get("skill_keys", ["a", "s"]),
            jump=jump_key
        )
        self.exception_handler.set_jump_key(jump_key)

        if config.get("has_dash"):
            dash_key = self._parse_key(config.get("dash_key", "f") or "f")
            self.combat.set_dash(True, dash_key)
        else:
            self.combat.set_dash(False)

        print("\n" + "="*50)
        print(f"配置 '{config.get('name', '?')}' 加载完成！")
        print(f"检测模式: {'模板匹配' if self.detector.mode=='template' else '颜色检测'}")
        print(f"战斗类型: {'近战' if self.combat.combat_type=='melee' else '远程'}")
        print("按 F10 开始自动刷怪，ESC 停止")
        print("="*50 + "\n")
        
    def _setup_template_mode(self, cached_img=None):
        """设置模板匹配模式 - 支持使用已保存模板集或新建"""
        print("\n模板匹配设置:")

        # 检查已有模板集
        tpl_sets = ProfileManager.list_template_sets()
        if tpl_sets:
            print("\n已保存的模板集:")
            for i, (name, count) in enumerate(tpl_sets, 1):
                print(f"  [{i}] {name} ({count}个模板)")

            print("\n请选择:")
            print("  编号: 使用已有模板集")
            print("  n: 新建模板集")
            print("  d: 删除模板集")
            choice = input("> ").strip().lower()
            if choice == 'd':
                self._delete_template_set_menu(tpl_sets)
                # 删除后继续走新建流程
            elif choice.isdigit() and 1 <= int(choice) <= len(tpl_sets):
                name = tpl_sets[int(choice) - 1][0]
                templates = ProfileManager.load_templates(name)
                for tpl in templates:
                    self.detector.templates.append(tpl)
                self._current_template_set = name
                print(f"[模板] 已加载模板集: {name} ({len(templates)}个模板)")
                return name

        # 新建模板集
        tpl_set_name = input("\n请输入新模板集名称 (如: 神秘河_花蛇): ").strip() or "default"
        self._current_template_set = tpl_set_name

        if cached_img is not None:
            img = cached_img
            print("使用之前的截图，请在图像中框选怪物模板")
        else:
            print("请先进入游戏，对准怪物，按回车截图")
            input("准备好后按回车...")
            img = self.screen.capture()

        if img is None:
            print("[错误] 无法获取截图")
            return tpl_set_name

        self._select_monster_template(img)
        while input("\n是否添加更多模板? (y/n): ").strip().lower() == 'y':
            img = self.screen.capture()
            if img is not None:
                self._select_monster_template(img)

        return tpl_set_name

    def _delete_template_set_menu(self, tpl_sets):
        if not tpl_sets:
            return
        for i, (name, count) in enumerate(tpl_sets, 1):
            print(f"  [{i}] {name} ({count}个模板)")
        choice = input("要删除的编号 (0取消): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(tpl_sets):
            name = tpl_sets[int(choice) - 1][0]
            if input(f"确认删除模板集 '{name}'? (y/n): ").strip().lower() == 'y':
                ProfileManager.delete_template_set(name)

    def _select_monster_template(self, img):
        """在截图上让用户框选怪物模板"""
        print("请在弹出的窗口中用鼠标框选怪物区域 (空格/回车确认, C取消)")
        x, y, w, h = cv2.selectROI("框选怪物模板", img, fromCenter=False, showCrosshair=True)
        cv2.destroyAllWindows()

        if w == 0 or h == 0:
            print("[跳过] 未选择区域")
            return

        template = img[y:y+h, x:x+w]
        tpl_set = getattr(self, '_current_template_set', 'default')
        path = ProfileManager.save_template(template, tpl_set)
        gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        self.detector.templates.append(gray)
        print(f"已保存模板: {path} ({w}x{h})")
                
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

        # 执行动作（PostMessage 直发，无需切前台）
        self.combat.execute_action(action_type, params)

        # 显示调试信息（放在动作之后，且不抢焦点）
        if self.show_debug:
            self._draw_debug_info(screenshot, player_pos, monsters, action_type)

        # 异常检测
        current_time = time.time()
        exception_type, suggestion = self.exception_handler.check_exceptions(current_time)
        if exception_type:
            self.exception_handler.execute_recovery(exception_type)
            
        self.frame_count += 1
        
    def _draw_debug_info(self, img, player_pos, monsters, action):
        """绘制调试信息（不抢焦点）"""
        debug_img = img.copy()

        if player_pos:
            cv2.circle(debug_img, player_pos, 10, (0, 255, 0), -1)
            cv2.circle(debug_img, player_pos, self.combat.attack_range, (0, 255, 0), 2)

        for (x, y, w, h) in monsters:
            cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 0, 255), 2)

        info_text = f"Monsters: {len(monsters)} | Action: {action} | Frame: {self.frame_count}"
        cv2.putText(debug_img, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("Debug", debug_img)
        # 不用 waitKey，用 pollKey 避免抢焦点
        cv2.pollKey()
        
    def start(self):
        """开始自动刷怪"""
        self.running = True
        self.stop_flag = False
        self.start_time = time.time()
        self.frame_count = 0

        print("\n" + "="*50)
        print("自动刷怪开始！")
        print("3秒后执行... (请切换到游戏窗口)")
        print("="*50 + "\n")

        for i in range(3, 0, -1):
            print(f"{i}...")
            time.sleep(1)
            if self.stop_flag:
                break

        # 倒计时结束后切到游戏窗口
        self.screen.bring_to_front()
        # 同步窗口句柄到战斗模块（bring_to_front 可能新发现了窗口）
        if self.screen.game_hwnd:
            self.combat.set_game_hwnd(self.screen.game_hwnd)
            print(f"[PostMessage] 已绑定窗口句柄: {self.screen.game_hwnd}")
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
            self.combat.release_all_keys()
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
