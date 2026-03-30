#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒险岛Online - 按键记录式自动刷怪脚本
功能：记录键盘操作（按键+时长），然后循环回放，每次按键间有随机时间间隔
"""

import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path

from pynput import keyboard
from pynput.keyboard import Controller, Key


class KeyRecorder:
    """按键记录器 - 录制和回放键盘操作"""
    
    # 特殊键映射表
    SPECIAL_KEYS = {
        'Key.alt': Key.alt,
        'Key.alt_l': Key.alt_l,
        'Key.alt_r': Key.alt_r,
        'Key.alt_gr': Key.alt_gr,
        'Key.backspace': Key.backspace,
        'Key.caps_lock': Key.caps_lock,
        'Key.cmd': Key.cmd,
        'Key.cmd_l': Key.cmd_l,
        'Key.cmd_r': Key.cmd_r,
        'Key.ctrl': Key.ctrl,
        'Key.ctrl_l': Key.ctrl_l,
        'Key.ctrl_r': Key.ctrl_r,
        'Key.delete': Key.delete,
        'Key.down': Key.down,
        'Key.end': Key.end,
        'Key.enter': Key.enter,
        'Key.esc': Key.esc,
        'Key.f1': Key.f1,
        'Key.f2': Key.f2,
        'Key.f3': Key.f3,
        'Key.f4': Key.f4,
        'Key.f5': Key.f5,
        'Key.f6': Key.f6,
        'Key.f7': Key.f7,
        'Key.f8': Key.f8,
        'Key.f9': Key.f9,
        'Key.f10': Key.f10,
        'Key.f11': Key.f11,
        'Key.f12': Key.f12,
        'Key.home': Key.home,
        'Key.insert': Key.insert,
        'Key.left': Key.left,
        'Key.menu': Key.menu,
        'Key.num_lock': Key.num_lock,
        'Key.page_down': Key.page_down,
        'Key.page_up': Key.page_up,
        'Key.pause': Key.pause,
        'Key.print_screen': Key.print_screen,
        'Key.right': Key.right,
        'Key.scroll_lock': Key.scroll_lock,
        'Key.shift': Key.shift,
        'Key.shift_l': Key.shift_l,
        'Key.shift_r': Key.shift_r,
        'Key.space': Key.space,
        'Key.tab': Key.tab,
        'Key.up': Key.up,
    }
    
    def __init__(self):
        self.keyboard_controller = Controller()
        self.recorded_events = []  # 记录的事件列表
        self.is_recording = False
        self.is_playing = False
        self.stop_playback = False
        self.key_states = {}  # 记录按键按下时间
        self.start_time = None
        self.last_event_time = None
        
        # 可配置参数
        self.min_interval = 0.1  # 最小随机间隔(秒)
        self.max_interval = 0.5  # 最大随机间隔(秒)
        self.loop_count = 0  # 0表示无限循环
        self.current_loop = 0
        
    def set_random_interval(self, min_sec: float, max_sec: float):
        """设置按键间的随机时间间隔范围"""
        self.min_interval = min_sec
        self.max_interval = max_sec
        print(f"[配置] 随机间隔设置为: {min_sec}~{max_sec}秒")
        
    def set_loop_count(self, count: int):
        """设置循环次数，0表示无限循环"""
        self.loop_count = count
        print(f"[配置] 循环次数设置为: {'无限' if count == 0 else count}次")
        
    def _on_key_press(self, key):
        """按键按下回调"""
        if not self.is_recording:
            return
            
        current_time = time.time()
        key_str = self._key_to_string(key)
        
        # 记录按键按下时间
        if key_str not in self.key_states:
            self.key_states[key_str] = current_time
            
            # 记录事件间隔（从前一个事件到现在的时间）
            interval = 0
            if self.last_event_time is not None:
                interval = current_time - self.last_event_time
                
            self.recorded_events.append({
                'type': 'press',
                'key': key_str,
                'interval': round(interval, 3),
                'timestamp': current_time - self.start_time
            })
            self.last_event_time = current_time
            print(f"[录制] 按下: {key_str} (间隔: {interval:.3f}s)")
    
    def _on_key_release(self, key):
        """按键释放回调"""
        if not self.is_recording:
            return
            
        current_time = time.time()
        key_str = self._key_to_string(key)
        
        if key_str in self.key_states:
            press_time = self.key_states.pop(key_str)
            duration = current_time - press_time
            
            # 更新最后一个press事件的duration
            for event in reversed(self.recorded_events):
                if event['type'] == 'press' and event['key'] == key_str:
                    event['duration'] = round(duration, 3)
                    break
                    
            print(f"[录制] 释放: {key_str} (按住: {duration:.3f}s)")
            
        # 按ESC停止录制
        if key == keyboard.Key.esc and self.is_recording:
            print("[录制] 检测到ESC，停止录制...")
            return False
            
    def _key_to_string(self, key) -> str:
        """将按键对象转换为字符串"""
        try:
            return key.char
        except AttributeError:
            return str(key)
    
    def _string_to_key(self, key_str: str):
        """将字符串转换回按键对象"""
        if key_str in self.SPECIAL_KEYS:
            return self.SPECIAL_KEYS[key_str]
        else:
            return key_str
    
    def start_recording(self):
        """开始录制按键"""
        if self.is_recording:
            print("[错误] 已经在录制中!")
            return
            
        self.recorded_events = []
        self.key_states = {}
        self.is_recording = True
        self.start_time = time.time()
        self.last_event_time = None
        
        print("\n" + "="*50)
        print("开始录制键盘操作...")
        print("提示: 操作完成后按 ESC 键停止录制")
        print("="*50 + "\n")
        
        # 启动键盘监听
        with keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        ) as listener:
            listener.join()
            
        self.is_recording = False
        
        print("\n" + "="*50)
        print(f"录制完成! 共记录 {len(self.recorded_events)} 个按键事件")
        print("="*50 + "\n")
        
    def stop_recording(self):
        """停止录制"""
        self.is_recording = False
        
    def save_recording(self, filename: str = None):
        """保存录制内容到文件"""
        if not self.recorded_events:
            print("[错误] 没有可保存的录制内容!")
            return
            
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.json"
            
        filepath = Path(filename)
        data = {
            'recorded_at': datetime.now().isoformat(),
            'total_events': len(self.recorded_events),
            'events': self.recorded_events
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        print(f"[保存] 录制内容已保存到: {filepath.absolute()}")
        return filepath
    
    def load_recording(self, filename: str):
        """从文件加载录制内容"""
        filepath = Path(filename)
        if not filepath.exists():
            print(f"[错误] 文件不存在: {filename}")
            return False
            
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        self.recorded_events = data['events']
        print(f"[加载] 已加载 {len(self.recorded_events)} 个事件 from {filename}")
        return True
    
    def play_recording(self):
        """回放录制的按键"""
        if not self.recorded_events:
            print("[错误] 没有可回放的录制内容!")
            return
            
        if self.is_playing:
            print("[错误] 已经在播放中!")
            return
            
        self.is_playing = True
        self.stop_playback = False
        self.current_loop = 0
        
        print("\n" + "="*50)
        print("开始回放按键操作...")
        print(f"循环次数: {'无限' if self.loop_count == 0 else self.loop_count}")
        print(f"随机间隔: {self.min_interval}~{self.max_interval}秒")
        print("提示: 按 ESC 键停止回放")
        print("="*50 + "\n")
        
        # 启动ESC监听线程
        esc_listener = threading.Thread(target=self._listen_for_stop)
        esc_listener.daemon = True
        esc_listener.start()
        
        # 等待3秒让用户切换到游戏窗口
        print("3秒后开始回放...")
        for i in range(3, 0, -1):
            if self.stop_playback:
                break
            print(f"{i}...")
            time.sleep(1)
            
        while not self.stop_playback:
            self.current_loop += 1
            if self.loop_count > 0 and self.current_loop > self.loop_count:
                print(f"\n已完成 {self.loop_count} 次循环")
                break
                
            print(f"\n--- 第 {self.current_loop} 次循环 ---")
            
            for i, event in enumerate(self.recorded_events):
                if self.stop_playback:
                    break
                    
                key = self._string_to_key(event['key'])
                duration = event.get('duration', 0.1)
                original_interval = event.get('interval', 0)
                
                # 添加随机时间间隔（基于原始间隔加上随机偏移）
                random_delay = random.uniform(self.min_interval, self.max_interval)
                total_delay = original_interval + random_delay
                
                if total_delay > 0:
                    time.sleep(total_delay)
                    
                # 按下按键
                self.keyboard_controller.press(key)
                time.sleep(duration)  # 保持按键时长
                self.keyboard_controller.release(key)
                
                print(f"[回放] {event['key']} (按住{duration:.2f}s, 等待{total_delay:.2f}s)")
                
            if not self.stop_playback and (self.loop_count == 0 or self.current_loop < self.loop_count):
                # 循环间添加随机间隔
                loop_delay = random.uniform(0.5, 1.5)
                print(f"循环间等待: {loop_delay:.2f}s")
                time.sleep(loop_delay)
                
        self.is_playing = False
        print("\n" + "="*50)
        print("回放已停止")
        print("="*50 + "\n")
        
    def _listen_for_stop(self):
        """监听ESC键停止回放"""
        def on_press(key):
            if key == keyboard.Key.esc:
                self.stop_playback = True
                print("\n[停止] 检测到ESC，正在停止...")
                return False
                
        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
            
    def preview_recording(self):
        """预览录制的内容"""
        if not self.recorded_events:
            print("[提示] 没有录制内容")
            return
            
        print("\n" + "="*50)
        print("录制内容预览:")
        print("="*50)
        for i, event in enumerate(self.recorded_events, 1):
            duration = event.get('duration', 0)
            interval = event.get('interval', 0)
            print(f"{i}. 按键: {event['key']:<10} 按住: {duration:.3f}s  间隔: {interval:.3f}s")
        print("="*50 + "\n")


def show_menu():
    """显示主菜单"""
    print("""
╔══════════════════════════════════════════════════════════╗
║        冒险岛Online - 按键记录式自动刷怪脚本              ║
╠══════════════════════════════════════════════════════════╣
║  功能说明:                                                ║
║  1. 录制键盘操作（按键+按住时长）                         ║
║  2. 循环回放，每次按键间有随机时间间隔（防检测）          ║
╠══════════════════════════════════════════════════════════╣
║  操作说明:                                                ║
║  • 录制时按 ESC 停止录制                                  ║
║  • 回放时按 ESC 停止回放                                  ║
║  • 建议先进入游戏再开始回放                               ║
╚══════════════════════════════════════════════════════════╝
""")


def main():
    """主程序"""
    recorder = KeyRecorder()
    
    # 设置默认参数
    recorder.set_random_interval(0.05, 0.3)  # 随机间隔0.05~0.3秒
    recorder.set_loop_count(0)  # 默认无限循环
    
    show_menu()
    
    while True:
        print("\n主菜单:")
        print("1. 开始录制键盘操作")
        print("2. 回放录制的操作")
        print("3. 预览录制内容")
        print("4. 保存录制到文件")
        print("5. 从文件加载录制")
        print("6. 设置循环次数")
        print("7. 设置随机时间间隔")
        print("0. 退出程序")
        
        choice = input("\n请选择操作 (0-7): ").strip()
        
        if choice == '1':
            recorder.start_recording()
            
        elif choice == '2':
            recorder.play_recording()
            
        elif choice == '3':
            recorder.preview_recording()
            
        elif choice == '4':
            filename = input("请输入保存文件名(直接回车使用默认名): ").strip()
            if filename:
                recorder.save_recording(filename)
            else:
                recorder.save_recording()
                
        elif choice == '5':
            filename = input("请输入要加载的文件名: ").strip()
            if filename:
                recorder.load_recording(filename)
            else:
                print("[错误] 文件名不能为空")
                
        elif choice == '6':
            try:
                count = int(input("请输入循环次数 (0表示无限循环): ").strip())
                recorder.set_loop_count(count)
            except ValueError:
                print("[错误] 请输入有效数字")
                
        elif choice == '7':
            try:
                min_val = float(input("请输入最小随机间隔(秒,如0.05): ").strip())
                max_val = float(input("请输入最大随机间隔(秒,如0.3): ").strip())
                if min_val >= 0 and max_val > min_val:
                    recorder.set_random_interval(min_val, max_val)
                else:
                    print("[错误] 最小值必须>=0且最大值必须大于最小值")
            except ValueError:
                print("[错误] 请输入有效数字")
                
        elif choice == '0':
            print("\n感谢使用，再见!")
            break
            
        else:
            print("[错误] 无效的选择，请重新输入")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序已退出")
    except Exception as e:
        print(f"\n[错误] 程序异常: {e}")
