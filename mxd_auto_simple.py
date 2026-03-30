#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒险岛Online - 简易按键记录自动刷怪
快速使用方法：
1. 运行脚本
2. 按 'r' 开始录制你的刷怪按键（如：左右移动+攻击+技能）
3. 按 ESC 停止录制
4. 按 'p' 开始自动刷怪（3秒后开始，按ESC停止）
"""

import random
import threading
import time
from datetime import datetime

from pynput import keyboard
from pynput.keyboard import Controller, Key


class MXDAutoSimple:
    """简易版自动刷怪脚本"""
    
    SPECIAL_KEYS = {
        'Key.left': Key.left,
        'Key.right': Key.right,
        'Key.up': Key.up,
        'Key.down': Key.down,
        'Key.space': Key.space,
        'Key.shift': Key.shift,
        'Key.ctrl': Key.ctrl,
        'Key.alt': Key.alt,
        'Key.tab': Key.tab,
        'Key.enter': Key.enter,
        'Key.esc': Key.esc,
        'Key.delete': Key.delete,
        'Key.insert': Key.insert,
        'Key.home': Key.home,
        'Key.end': Key.end,
        'Key.page_up': Key.page_up,
        'Key.page_down': Key.page_down,
        'Key.f1': Key.f1, 'Key.f2': Key.f2, 'Key.f3': Key.f3, 'Key.f4': Key.f4,
        'Key.f5': Key.f5, 'Key.f6': Key.f6, 'Key.f7': Key.f7, 'Key.f8': Key.f8,
        'Key.f9': Key.f9, 'Key.f10': Key.f10, 'Key.f11': Key.f11, 'Key.f12': Key.f12,
    }
    
    def __init__(self):
        self.controller = Controller()
        self.events = []  # 记录的事件
        self.recording = False
        self.playing = False
        self.stop_flag = False
        self.key_states = {}
        self.last_time = None
        
        # 可配置参数
        self.min_delay = 0.05      # 最小随机延迟(秒)
        self.max_delay = 0.25      # 最大随机延迟(秒)
        self.loop_count = 0        # 0=无限循环
        
    def _key_to_str(self, key):
        """按键转字符串"""
        try:
            return key.char
        except:
            return str(key)
    
    def _str_to_key(self, s):
        """字符串转按键"""
        return self.SPECIAL_KEYS.get(s, s)
    
    def on_press(self, key):
        """按键按下"""
        if not self.recording:
            return
        
        key_str = self._key_to_str(key)
        now = time.time()
        
        if key_str not in self.key_states:
            self.key_states[key_str] = now
            interval = now - self.last_time if self.last_time else 0
            self.events.append({'key': key_str, 'interval': interval})
            self.last_time = now
            print(f"  [录] {key_str} (距上次{interval:.2f}s)", end='\r')
    
    def on_release(self, key):
        """按键释放"""
        if not self.recording:
            return
        
        key_str = self._key_to_str(key)
        now = time.time()
        
        if key_str in self.key_states:
            duration = now - self.key_states.pop(key_str)
            # 更新最后事件的duration
            for e in reversed(self.events):
                if e['key'] == key_str and 'duration' not in e:
                    e['duration'] = duration
                    break
        
        if key == keyboard.Key.esc:
            return False
    
    def record(self):
        """开始录制"""
        self.events = []
        self.key_states = {}
        self.recording = True
        self.last_time = None
        
        print("\n【开始录制】请在3秒内切换到游戏窗口...")
        time.sleep(3)
        print("正在录制... 按 ESC 停止\n")
        
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as l:
            l.join()
        
        self.recording = False
        print(f"\n【录制完成】共 {len(self.events)} 个按键\n")
    
    def play(self):
        """回放录制"""
        if not self.events:
            print("请先录制!")
            return
        
        self.playing = True
        self.stop_flag = False
        loop = 0
        
        print("\n【开始回放】3秒后自动执行，按 ESC 停止...")
        for i in range(3, 0, -1):
            print(f"{i}...")
            time.sleep(1)
        
        # ESC监听
        def check_esc(k):
            if k == keyboard.Key.esc:
                self.stop_flag = True
                return False
        
        listener = keyboard.Listener(on_press=check_esc)
        listener.start()
        
        try:
            while not self.stop_flag:
                loop += 1
                if self.loop_count > 0 and loop > self.loop_count:
                    break
                
                print(f"\n[第{loop}轮]", end=' ')
                
                for evt in self.events:
                    if self.stop_flag:
                        break
                    
                    key = self._str_to_key(evt['key'])
                    dur = evt.get('duration', 0.05)
                    delay = evt['interval'] + random.uniform(self.min_delay, self.max_delay)
                    
                    if delay > 0:
                        time.sleep(delay)
                    
                    self.controller.press(key)
                    time.sleep(dur)
                    self.controller.release(key)
                    print(".", end='', flush=True)
                
                # 循环间隔
                if not self.stop_flag:
                    time.sleep(random.uniform(0.3, 0.8))
        
        except Exception as e:
            print(f"\n错误: {e}")
        
        self.playing = False
        listener.stop()
        print("\n【回放停止】\n")
    
    def show_events(self):
        """显示录制的事件"""
        if not self.events:
            print("无录制内容")
            return
        print("\n已录制的事件:")
        for i, e in enumerate(self.events, 1):
            dur = e.get('duration', 0)
            print(f"  {i}. {e['key']:<8} 按住{dur:.2f}s  间隔{e['interval']:.2f}s")
        print()
    
    def save(self, name=None):
        """保存录制"""
        if not self.events:
            print("无内容可保存")
            return
        
        import json
        if name is None:
            name = f"mxd_rec_{datetime.now().strftime('%m%d_%H%M%S')}.json"
        
        with open(name, 'w', encoding='utf-8') as f:
            json.dump({
                'events': self.events,
                'min_delay': self.min_delay,
                'max_delay': self.max_delay
            }, f, ensure_ascii=False, indent=2)
        print(f"已保存: {name}")
    
    def load(self, name):
        """加载录制"""
        import json
        from pathlib import Path
        
        if not Path(name).exists():
            print(f"文件不存在: {name}")
            return
        
        with open(name, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.events = data['events']
        self.min_delay = data.get('min_delay', 0.05)
        self.max_delay = data.get('max_delay', 0.25)
        print(f"已加载: {name} ({len(self.events)}个事件)")
    
    def set_delay(self):
        """设置延迟"""
        try:
            self.min_delay = float(input(f"最小延迟(当前{self.min_delay}s): ") or self.min_delay)
            self.max_delay = float(input(f"最大延迟(当前{self.max_delay}s): ") or self.max_delay)
            print(f"随机延迟: {self.min_delay}~{self.max_delay}s")
        except:
            print("输入错误")
    
    def run(self):
        """主循环"""
        print("""
╔══════════════════════════════════════════╗
║     冒险岛简易自动刷怪脚本                ║
╠══════════════════════════════════════════╣
║  r - 录制按键                            ║
║  p - 回放执行                            ║
║  v - 查看录制                            ║
║  s - 保存录制                            ║
║  l - 加载录制                            ║
║  d - 设置随机延迟                        ║
║  q - 退出                                ║
╚══════════════════════════════════════════╝
""")
        
        while True:
            cmd = input("命令(r/p/v/s/l/d/q): ").strip().lower()
            
            if cmd == 'r':
                self.record()
            elif cmd == 'p':
                self.play()
            elif cmd == 'v':
                self.show_events()
            elif cmd == 's':
                self.save()
            elif cmd == 'l':
                fname = input("文件名: ").strip()
                if fname:
                    self.load(fname)
            elif cmd == 'd':
                self.set_delay()
            elif cmd == 'q':
                print("再见!")
                break


if __name__ == '__main__':
    try:
        MXDAutoSimple().run()
    except KeyboardInterrupt:
        print("\n已退出")
