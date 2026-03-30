#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒险岛自动刷怪 - 配置文件
根据需要修改以下参数
"""

# ==================== 随机延迟设置 ====================
# 按键间的随机延迟范围（秒）
# 建议值: 0.03 ~ 0.5 之间
# 太小容易被检测，太大效率低
MIN_RANDOM_DELAY = 0.05   # 最小延迟
MAX_RANDOM_DELAY = 0.25   # 最大延迟

# ==================== 循环设置 ====================
# 循环次数，0 表示无限循环
LOOP_COUNT = 0

# 每次循环之间的额外延迟（秒）
# 模拟人工休息，建议 0.5~2 秒
LOOP_DELAY_MIN = 0.5
LOOP_DELAY_MAX = 1.5

# ==================== 录制设置 ====================
# 录制前准备时间（秒）
RECORD_PREPARE_TIME = 3

# 回放前准备时间（秒）
PLAY_PREPARE_TIME = 3

# ==================== 冒险岛常用按键参考 ====================
# 你可以根据自己的键位修改
KEY_LEFT = 'left'      # 左移动
KEY_RIGHT = 'right'    # 右移动
KEY_UP = 'up'          # 上移动/爬梯子
KEY_DOWN = 'down'      # 下移动/爬梯子
KEY_JUMP = 'space'     # 跳跃 (通常是空格)
KEY_ATTACK = 'x'       # 普通攻击 (通常是X)
KEY_PICKUP = 'z'       # 拾取 (通常是Z)

# 技能键 (通常是A,S,D,F,G,H等)
SKILL_KEYS = ['a', 's', 'd', 'f', 'g', 'h']

# 药水快捷键
HP_POTION = 'q'        # 红药
MP_POTION = 'w'        # 蓝药
