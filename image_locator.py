#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
===============================================================================
 局部图片定位工具（Windows 调试版）
===============================================================================
用途
    1. 启动后自动读取“程序所在文件夹 / 当前文件夹”下的 huaiyanggudao.jpg 作为原图；
    2. 按 Ctrl+Alt+A 全屏框选屏幕上原图的某个局部，松开后在选区内“双击”，
       该截图自动作为“待查找图片”送入程序；
    3. 程序用多尺度（可选小幅旋转）模板匹配，在原图上标出最可能的若干位置，
       按相似度排序，重叠候选自动去重，并可另存标注结果图；
    4. 结果以“图一”为基准给出坐标：左上角 (0, 0)，x 向右到 400，y 向下到 445
       （默认值，可在面板「坐标范围 X / Y」里改），框上方、结果列表、详情、
       保存的标注图、状态栏都会带上该坐标。

安装依赖
    pip install opencv-python numpy pillow

运行
    python image_locator.py

快捷键
    Ctrl+Alt+A   截图（如需改成别的键，改下面 HOTKEY_VK / HOTKEY_MODS / HOTKEY_LABEL）
    Enter        在截图浮层内确认选区
    Esc          取消截图

实现要点
    * 原图用 PIL 读取（cv2.imread 在中文路径下会失败），再转成 numpy 做匹配；
    * 匹配在后台线程执行，界面不卡，进度条实时刷新；
    * 归一化相关系数 + 多尺度 + 可选小角度旋转，跨尺度重叠候选做 IoU/包含度去重；
    * 像素坐标按 (像素/图宽*X上限, 像素/图高*Y上限) 换算成基准图坐标；
    * 可保存全分辨率标注图放大核对。
===============================================================================
"""

import os
import sys
import time
import queue
import ctypes
import threading
import traceback
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageTk, ImageGrab, ImageDraw, ImageFont, ImageOps
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------- 基础配置 --
APP_NAME = "局部图片定位工具"
ORIGIN_FILE = "huaiyanggudao.jpg"
# 找不到 huaiyanggudao.jpg 时依次尝试的其它后缀
ORIGIN_ALTS = (
    "huaiyanggudao.jpg", "huaiyanggudao.JPG", "huaiyanggudao.jpeg",
    "huaiyanggudao.JPEG", "huaiyanggudao.png", "huaiyanggudao.PNG",
    "huaiyanggudao.bmp",
)

HOTKEY_LABEL = "Ctrl+Alt+A"
HOTKEY_MOD_ALT = 0x0001
HOTKEY_MOD_CONTROL = 0x0002
HOTKEY_MOD_NOREPEAT = 0x4000
HOTKEY_MODS = HOTKEY_MOD_ALT | HOTKEY_MOD_CONTROL | HOTKEY_MOD_NOREPEAT
HOTKEY_VK = ord("A")
HOTKEY_ID = 0x4D31

# 匹配精度预设：尺度搜索范围 / 缩放步进比 / 旋转角度集合
PRESETS = {
    "快速": dict(lo=0.30, hi=1.05, ratio=1.22, angles=(0,)),
    "标准": dict(lo=0.20, hi=1.15, ratio=1.14, angles=(0, -3, 3)),
    "精细": dict(lo=0.15, hi=1.25, ratio=1.07, angles=(0, -2, 2, -4, 4, -6, 6)),
}
DEFAULT_PRESET = "精细"
DEFAULT_THRESHOLD = 0.39
DEFAULT_COUNT = 3
# 坐标基准：以“图一”为参照，左上角 (0,0)，x 向右到 MAP_W，y 向下到 MAP_H
DEFAULT_MAP_W = 400
DEFAULT_MAP_H = 445
MAX_SCREEN_PIXELS = 12_000_000   # 超过该像素数只截主屏，避免内存爆掉


# ---------------------------------------------------------------- 小工具 --
def enable_dpi_awareness():
    """让 Tk 的坐标与物理像素一致（否则高分屏下框选位置会偏移）。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # 每显示器 DPI 感知
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def system_dpi():
    if sys.platform != "win32":
        return 96
    try:
        return int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        return 96


def find_origin_image():
    """在程序目录 / 当前目录里找 huaiyanggudao.jpg，返回 Path 或 None。"""
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    else:
        roots.append(Path(__file__).resolve().parent)
    roots.append(Path.cwd())
    for root in roots:
        for name in ORIGIN_ALTS:
            p = root / name
            if p.is_file():
                return p
    return None


def load_rgb_image(path):
    """用 PIL 读图（兼容中文路径 / EXIF 方向），返回 (PIL.RGB, np RGB)。"""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        rgb = im.convert("RGB")
    return rgb, np.array(rgb)


def grab_screen():
    """抓屏，返回 (PIL.RGB 图像, (虚拟屏原点x, 原点y, 宽, 高))。"""
    if sys.platform == "win32":
        try:
            u = ctypes.windll.user32
            vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
            vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
            if vw > 0 and vh > 0 and vw * vh <= MAX_SCREEN_PIXELS:
                img = ImageGrab.grab(all_screens=True).convert("RGB")
                if img.size == (vw, vh):
                    return img, (vx, vy, vw, vh)
        except Exception:
            pass
    img = ImageGrab.grab().convert("RGB")
    return img, (0, 0, img.size[0], img.size[1])


_FONT_CACHE = {}


def load_font(size):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    cands = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc", "arialbd.ttf"):
            cands.append(os.path.join(windir, "Fonts", name))
    cands.append("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    font = None
    for p in cands:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                break
            except Exception:
                continue
    if font is None:
        try:
            font = ImageFont.load_default(size)
        except TypeError:
            font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


# ---------------------------------------------------------------- 全局热键 --
class GlobalHotkey(threading.Thread):
    """Windows RegisterHotKey + 独立消息循环，无需第三方库、无需管理员权限。"""

    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    def __init__(self, on_press, mods=HOTKEY_MODS, vk=HOTKEY_VK, hid=HOTKEY_ID):
        super().__init__(daemon=True)
        self.on_press = on_press
        self.mods = mods
        self.vk = vk
        self.hid = hid
        self.ok = None
        self._tid = None
        self._ready = threading.Event()

    def start(self):
        if sys.platform != "win32":
            self.ok = False
            return False
        super().start()
        self._ready.wait(1.5)
        return bool(self.ok)

    def run(self):
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._tid = kernel32.GetCurrentThreadId()

        ok = user32.RegisterHotKey(None, self.hid, self.mods, self.vk)
        if not ok:                                  # 去掉 NOREPEAT 再试一次
            ok = user32.RegisterHotKey(None, self.hid, self.mods & ~HOTKEY_MOD_NOREPEAT, self.vk)
        self.ok = bool(ok)
        self._ready.set()
        if not ok:
            return

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == self.WM_HOTKEY and int(msg.wParam) == self.hid:
                try:
                    self.on_press()
                except Exception:
                    pass
        try:
            user32.UnregisterHotKey(None, self.hid)
        except Exception:
            pass

    def stop(self):
        if sys.platform == "win32" and self._tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._tid, self.WM_QUIT, 0, 0)
            except Exception:
                pass


# ---------------------------------------------------------------- 截图浮层 --
class SnipOverlay:
    """
    冻结屏幕 -> 变暗 -> 拖拽框选 -> 选区内“双击”确认 -> 回调裁剪图。
    """

    def __init__(self, master, on_confirm, on_close=None):
        self.on_confirm = on_confirm
        self.on_close = on_close
        self.img, (self.vx, self.vy, self.vw, self.vh) = grab_screen()

        self.box = None
        self.selected = False
        self.start = None
        self.rect_id = None
        self._sel_photo = None

        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry("%dx%d+%d+%d" % (self.vw, self.vh, self.vx, self.vy))
        self.win.configure(bg="#000000")

        self.canvas = tk.Canvas(self.win, width=self.vw, height=self.vh,
                                highlightthickness=0, bd=0, cursor="crosshair",
                                bg="#000000")
        self.canvas.pack(fill="both", expand=True)

        dark = Image.blend(self.img, Image.new("RGB", self.img.size, (0, 0, 0)), 0.60)
        self._bg_photo = ImageTk.PhotoImage(dark)
        self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo)

        self.hint = self.canvas.create_text(
            self.vw // 2, 36,
            text="按住左键拖动框选  ·  松开后在选区内双击即送入程序  ·  Esc 取消",
            fill="#FFFFFF", font=("Microsoft YaHei UI", 13), tags="hint")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<Button-3>", lambda e: self.close())
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.bind("<Return>", lambda e: self._confirm())

        self.canvas.focus_set()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    # ---------------- 内部 ----------------
    def _inside(self, x, y):
        if not self.box:
            return False
        x0, y0, x1, y1 = self.box
        return x0 <= x <= x1 and y0 <= y <= y1

    def _clear_size(self):
        self.canvas.delete("size")

    def _draw_size(self, w, h, cx, cy):
        self._clear_size()
        txt = "%d × %d" % (w, h)
        tx = min(max(cx + 14, 8), self.vw - 110)
        ty = min(max(cy + 18, 8), self.vh - 30)
        bg = self.canvas.create_rectangle(tx - 4, ty - 3, tx + 96, ty + 22,
                                          fill="#000000", outline="", tags="size")
        self.canvas.create_text(tx + 44, ty + 10, text=txt, fill="#00E5FF",
                                font=("Consolas", 11), tags="size")
        self.canvas.tag_raise(bg, "size")

    def _on_press(self, e):
        if self.selected and self._inside(e.x, e.y):
            return                         # 选区内的单击交给双击事件处理
        if self.selected:
            self._reset()
        self.start = (e.x, e.y)
        self.rect_id = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                    outline="#00E5FF", width=2)

    def _on_drag(self, e):
        if self.start is None:
            return
        x0, y0 = self.start
        self.canvas.coords(self.rect_id, x0, y0, e.x, e.y)
        self._draw_size(abs(e.x - x0), abs(e.y - y0), e.x, e.y)

    def _on_release(self, e):
        if self.start is None:
            return
        x0, y0 = self.start
        self.start = None
        x1, y1 = e.x, e.y
        box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        self._clear_size()
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            self.canvas.delete(self.rect_id)
            self.rect_id = None
            return

        self.box = box
        self.selected = True
        crop = self.img.crop(box)
        self._sel_photo = ImageTk.PhotoImage(crop)
        self.canvas.create_image(box[0], box[1], anchor="nw",
                                 image=self._sel_photo, tags="sel")
        self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(*box, outline="#00E5FF", width=2)
        self._show_confirm_hint(box)
        self.canvas.tag_raise("hint")
        self.canvas.tag_raise("size")

    def _show_confirm_hint(self, box):
        self.canvas.delete("chint")
        x0, y0, x1, y1 = box
        txt = "双击确认  /  Enter 确认  /  Esc 取消"
        ty = y1 + 22 if y1 + 40 < self.vh else y0 - 22
        tx = (x0 + x1) / 2.0
        tx = min(max(tx, len(txt) * 6 + 20), self.vw - len(txt) * 6 - 20)
        self.canvas.create_text(tx, ty, text=txt, fill="#00E5FF",
                                font=("Microsoft YaHei UI", 12), tags="chint")
        self.canvas.tag_raise("chint")

    def _on_double(self, e):
        if self.selected and self._inside(e.x, e.y):
            self._confirm()

    def _reset(self):
        self.canvas.delete("sel")
        self.canvas.delete("chint")
        self._clear_size()
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None
        self._sel_photo = None
        self.box = None
        self.selected = False
        self.start = None
        self.canvas.itemconfigure(
            self.hint,
            text="按住左键拖动框选  ·  松开后在选区内双击即送入程序  ·  Esc 取消")

    def _confirm(self):
        if not self.selected or not self.box:
            return
        crop = self.img.crop(self.box)
        self.close()
        try:
            self.on_confirm(crop)
        except Exception:
            traceback.print_exc()

    def close(self):
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass


# ---------------------------------------------------------------- 匹配算法 --
def build_scales(lo, hi, ratio):
    scales, s = [], float(lo)
    while s <= hi + 1e-6:
        scales.append(round(s, 4))
        s *= ratio
    return scales or [1.0]


def rotate_gray(gray, angle):
    h, w = gray.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(round(h * sin + w * cos)), int(round(h * cos + w * sin))
    M[0, 2] += nw / 2.0 - cx
    M[1, 2] += nh / 2.0 - cy
    return cv2.warpAffine(gray, M, (nw, nh), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def top_peaks(res, thr, k, tw, th):
    """在相关度图里取 k 个阈值以上的局部峰值（取到就屏蔽周围）。"""
    peaks = []
    h, w = res.shape[:2]
    for _ in range(max(1, k)):
        _mn, mx, _mnl, mxl = cv2.minMaxLoc(res)
        if not np.isfinite(mx) or mx < thr:
            break
        x, y = int(mxl[0]), int(mxl[1])
        peaks.append((float(mx), x, y))
        x0, x1 = max(0, x - tw // 2), min(w, x + tw // 2 + 1)
        y0, y1 = max(0, y - th // 2), min(h, y + th // 2 + 1)
        res[y0:y1, x0:x1] = -1.0
    return peaks


def _inter(a, b):
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    iw = max(0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0, min(ay1, by1) - max(ay0, by0))
    return iw * ih


def duplicate(a, b):
    """跨尺度去重：IoU 大，或小框被大框高度包含。"""
    ia = _inter(a, b)
    if ia <= 0:
        return False
    aa = a["w"] * a["h"]
    ab = b["w"] * b["h"]
    iou = ia / float(aa + ab - ia)
    contain = ia / float(min(aa, ab))
    return iou > 0.25 or contain > 0.65


def texture_ok(origin_gray, x, y, tw, th, tpl_std):
    """候选区域的纹理反差是否与模板相当（抑制平坦/纯噪声区域的误报）。"""
    patch = origin_gray[max(0, y):y + th, max(0, x):x + tw]
    if patch.size < 16:
        return False
    if tpl_std < 2.0:
        return True
    ratio = float(patch.std()) / tpl_std
    return 0.40 <= ratio <= 2.60


def suppress(cands, top_n):
    cands.sort(key=lambda c: c.get("rank", c["score"]), reverse=True)
    kept = []
    for c in cands:
        if any(duplicate(c, k) for k in kept):
            continue
        kept.append(c)
        if len(kept) >= top_n:
            break
    return kept


def match_template_multiscale(origin_rgb, tpl_rgb, threshold=DEFAULT_THRESHOLD, top_n=DEFAULT_COUNT,
                              preset=DEFAULT_PRESET, allow_rotate=True,
                              progress=None):
    """多尺度（可选旋转）模板匹配，返回按相似度排序的候选列表。"""
    cfg = PRESETS.get(preset, PRESETS[DEFAULT_PRESET])
    angles = cfg["angles"] if allow_rotate else (0,)
    scales = build_scales(cfg["lo"], cfg["hi"], cfg["ratio"])

    origin_gray = cv2.cvtColor(np.ascontiguousarray(origin_rgb), cv2.COLOR_RGB2GRAY)
    tpl_gray = cv2.cvtColor(np.ascontiguousarray(tpl_rgb), cv2.COLOR_RGB2GRAY)
    H, W = origin_gray.shape[:2]

    cands = []
    total = max(1, len(scales) * len(angles))
    step = 0

    for scale in scales:
        for angle in angles:
            step += 1
            try:
                tg = rotate_gray(tpl_gray, angle) if abs(angle) > 1e-6 else tpl_gray
                tw = int(round(tg.shape[1] * scale))
                th = int(round(tg.shape[0] * scale))
                if tw < 8 or th < 8 or tw >= W or th >= H:
                    continue
                tg = cv2.resize(tg, (tw, th),
                                interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR)
                if float(tg.std()) < 2.0:            # 纯色模板：CCOEFF 会出 NaN
                    res = 1.0 - cv2.matchTemplate(origin_gray, tg, cv2.TM_SQDIFF_NORMED)
                else:
                    res = cv2.matchTemplate(origin_gray, tg, cv2.TM_CCOEFF_NORMED)
                res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
                tpl_std = float(tg.std())
                area_ratio = (tw * th) / float(W * H)
                tiny_penalty = 0.06 if area_ratio < 0.002 else 0.0
                for score, x, y in top_peaks(res, threshold, 3, tw, th):
                    if not texture_ok(origin_gray, x, y, tw, th, tpl_std):
                        continue
                    cands.append(dict(score=score, rank=score - tiny_penalty,
                                      x=x, y=y, w=tw, h=th,
                                      scale=scale, angle=angle))
            finally:
                if progress:
                    progress(min(1.0, step / float(total)))
    return suppress(cands, top_n)


# ---------------------------------------------------------------- 坐标换算 --
def norm_point(px, py, img_w, img_h, map_w, map_h):
    """原图像素坐标 -> 基准图坐标（左上 0,0，x 0..map_w，y 0..map_h）。"""
    if img_w <= 0 or img_h <= 0:
        return 0.0, 0.0
    return px / float(img_w) * map_w, py / float(img_h) * map_h


def hit_norm(hit, img_w, img_h, map_w, map_h):
    """返回该候选的 (中心坐标, 区域左上, 区域右下)，均为基准图坐标。"""
    cx, cy = hit["x"] + hit["w"] / 2.0, hit["y"] + hit["h"] / 2.0
    center = norm_point(cx, cy, img_w, img_h, map_w, map_h)
    tl = norm_point(hit["x"], hit["y"], img_w, img_h, map_w, map_h)
    br = norm_point(hit["x"] + hit["w"], hit["y"] + hit["h"],
                    img_w, img_h, map_w, map_h)
    return center, tl, br


# ---------------------------------------------------------------- 结果绘制 --
def render_annotated(origin_rgb, hits, highlight=None, map_size=(DEFAULT_MAP_W, DEFAULT_MAP_H)):
    """在原图副本上画框并标注基准坐标，返回 PIL.Image（全分辨率）。"""
    img = Image.fromarray(np.ascontiguousarray(origin_rgb))
    if not hits:
        return img
    draw = ImageDraw.Draw(img)
    W, H = img.size
    map_w, map_h = map_size
    base_w = max(3, int(min(W, H) / 400.0))
    fsize = max(15, int(min(W, H) / 28.0))
    font = load_font(fsize)
    for i, h in enumerate(hits):
        color = (0, 215, 70) if i == 0 else (255, 145, 0)
        if highlight is not None and i == highlight:
            color = (255, 225, 0)
        width = base_w + (4 if (i == 0 or i == highlight) else 0)
        x0, y0 = h["x"], h["y"]
        x1, y1 = x0 + h["w"], y0 + h["h"]
        draw.rectangle([x0, y0, x1, y1], outline=color, width=width)
        cx, cy = x0 + h["w"] / 2.0, y0 + h["h"] / 2.0
        nx, ny = norm_point(cx, cy, W, H, map_w, map_h)
        label = "#%d  %.3f  (%.0f, %.0f)" % (i + 1, h["score"], nx, ny)
        try:
            tb = draw.textbbox((0, 0), label, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
        except Exception:
            tw, th = len(label) * fsize * 0.6, fsize
        ty = y0 - th - 10
        if ty < 4:
            ty = y0 + 4
        tx = min(max(x0, 4), max(4, W - tw - 14))
        draw.rectangle([tx - 4, ty - 3, tx + tw + 8, ty + th + 7], fill=(0, 0, 0))
        draw.text((tx + 2, ty), label, fill=color, font=font)
    return img


# ---------------------------------------------------------------- 主界面 --
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("%s · %s 截图定位" % (APP_NAME, HOTKEY_LABEL))
        self.root.geometry("1240x820")
        self.root.minsize(1040, 700)
        self.root.configure(bg="#202020")
        try:
            self.root.tk.call("tk", "scaling", max(1.0, system_dpi() / 72.0))
        except Exception:
            pass

        self.origin_path = None
        self.origin_pil = None
        self.origin_rgb = None
        self.tpl_pil = None
        self.tpl_rgb = None
        self.hits = None
        self.highlight = None
        self.display_pil = None
        self._photo = None
        self._tpl_photo = None
        self._resize_job = None
        self._iid_map = {}
        self.busy = False
        self.job_q = None
        self.hot_q = queue.Queue()
        self.hotkey = None
        self.snip = None

        self._build_ui()
        self._load_origin()
        self._start_hotkey()
        self.root.after(120, self._poll_hotkey)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ UI 搭建 --
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except Exception:
            pass
        style.configure("Big.TButton", font=("Microsoft YaHei UI", 10, "bold"))

        # 顶部信息条
        top = tk.Frame(self.root, bg="#202020")
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.title_lbl = tk.Label(top, text=APP_NAME, bg="#202020", fg="#EDEDED",
                                  font=("Microsoft YaHei UI", 12, "bold"))
        self.title_lbl.pack(side="left")
        self.origin_lbl = tk.Label(top, text="原图：读取中…", bg="#202020", fg="#9E9E9E",
                                   font=("Microsoft YaHei UI", 9))
        self.origin_lbl.pack(side="left", padx=14)

        body = tk.Frame(self.root, bg="#202020")
        body.pack(fill="both", expand=True, padx=12, pady=4)

        # 左侧画布
        left = tk.Frame(body, bg="#202020")
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, bg="#2B2B2B", highlightthickness=1,
                                highlightbackground="#3A3A3A")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # 右侧面板
        right = tk.Frame(body, bg="#202020", width=308)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        # 待查找图片
        grp1 = tk.LabelFrame(right, text=" 待查找图片 ", bg="#202020", fg="#DDDDDD",
                             font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        grp1.pack(fill="x", pady=(0, 8))
        self.tpl_canvas = tk.Canvas(grp1, width=272, height=168, bg="#2B2B2B",
                                    highlightthickness=0)
        self.tpl_canvas.pack(padx=8, pady=8)
        self.tpl_canvas.create_text(136, 84, text="按 Ctrl+Alt+A 截图\n双击选区即载入",
                                    fill="#8A8A8A", font=("Microsoft YaHei UI", 9),
                                    justify="center", tags="empty")
        self.tpl_info = tk.Label(grp1, text="未载入", bg="#202020", fg="#9E9E9E",
                                 font=("Microsoft YaHei UI", 9))
        self.tpl_info.pack(pady=(0, 4))

        btn_row = tk.Frame(grp1, bg="#202020")
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        self.btn_snip = tk.Button(btn_row, text="截图 %s" % HOTKEY_LABEL,
                                  command=self.start_snip,
                                  font=("Microsoft YaHei UI", 9, "bold"),
                                  bg="#2F6FEB", fg="white", activebackground="#2457BC",
                                  activeforeground="white", bd=0, padx=10, pady=5,
                                  cursor="hand2")
        self.btn_snip.pack(side="left", expand=True, fill="x")
        self.btn_clear_tpl = tk.Button(btn_row, text="清空", command=self.clear_template,
                                       font=("Microsoft YaHei UI", 9), bd=1, padx=8, pady=5)
        self.btn_clear_tpl.pack(side="left", padx=(6, 0))

        # 匹配设置
        grp2 = tk.LabelFrame(right, text=" 匹配设置 ", bg="#202020", fg="#DDDDDD",
                             font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        grp2.pack(fill="x", pady=(0, 8))

        row = tk.Frame(grp2, bg="#202020")
        row.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(row, text="灵敏度", bg="#202020", fg="#DDDDDD",
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        self.thr_lbl = tk.Label(row, text="%.2f" % DEFAULT_THRESHOLD, bg="#202020", fg="#00E5FF",
                                font=("Consolas", 10))
        self.thr_lbl.pack(side="right")
        self.thr_var = tk.DoubleVar(value=DEFAULT_THRESHOLD)
        self.thr = tk.Scale(grp2, from_=0.30, to=0.95, resolution=0.01,
                            orient="horizontal", variable=self.thr_var,
                            showvalue=False, bg="#202020", fg="#DDDDDD",
                            highlightthickness=0, troughcolor="#3A3A3A",
                            command=lambda v: self.thr_lbl.config(text="%.2f" % float(v)))
        self.thr.pack(fill="x", padx=8)

        row = tk.Frame(grp2, bg="#202020")
        row.pack(fill="x", padx=8, pady=2)
        tk.Label(row, text="候选数量", bg="#202020", fg="#DDDDDD",
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        self.count_var = tk.StringVar(value=str(DEFAULT_COUNT))
        tk.Spinbox(row, from_=1, to=10, width=4, textvariable=self.count_var,
                   font=("Consolas", 10)).pack(side="right")

        row = tk.Frame(grp2, bg="#202020")
        row.pack(fill="x", padx=8, pady=2)
        tk.Label(row, text="搜索精度", bg="#202020", fg="#DDDDDD",
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        ttk.Combobox(row, textvariable=self.preset_var, values=list(PRESETS.keys()),
                     state="readonly", width=6).pack(side="right")

        row = tk.Frame(grp2, bg="#202020")
        row.pack(fill="x", padx=8, pady=2)
        tk.Label(row, text="坐标范围 X / Y", bg="#202020", fg="#DDDDDD",
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        self.map_h_var = tk.StringVar(value=str(DEFAULT_MAP_H))
        self.map_w_var = tk.StringVar(value=str(DEFAULT_MAP_W))
        tk.Spinbox(row, from_=1, to=100000, width=4, textvariable=self.map_h_var,
                   font=("Consolas", 10)).pack(side="right")
        tk.Label(row, text="/", bg="#202020", fg="#DDDDDD",
                 font=("Consolas", 10)).pack(side="right", padx=2)
        tk.Spinbox(row, from_=1, to=100000, width=4, textvariable=self.map_w_var,
                   font=("Consolas", 10)).pack(side="right")
        self._map_guard = False
        self.map_w_var.trace_add("write", self._on_map_changed)
        self.map_h_var.trace_add("write", self._on_map_changed)

        row = tk.Frame(grp2, bg="#202020")
        row.pack(fill="x", padx=8, pady=(2, 8))
        self.rotate_var = tk.BooleanVar(value=True)
        tk.Checkbutton(row, text="允许小幅旋转（±6°）", variable=self.rotate_var,
                       bg="#202020", fg="#DDDDDD", selectcolor="#2B2B2B",
                       activebackground="#202020", activeforeground="#DDDDDD",
                       font=("Microsoft YaHei UI", 9)).pack(side="left")

        self.btn_match = tk.Button(right, text="开始查找", command=lambda: self.start_match(),
                                   font=("Microsoft YaHei UI", 11, "bold"),
                                   bg="#17A34A", fg="white", activebackground="#12803B",
                                   activeforeground="white", bd=0, pady=8, cursor="hand2")
        self.btn_match.pack(fill="x", pady=(0, 6))

        self.pbar = ttk.Progressbar(right, mode="determinate", maximum=100)
        self.pbar.pack(fill="x", pady=(0, 8))

        # 结果
        grp3 = tk.LabelFrame(right, text=" 匹配结果 ", bg="#202020", fg="#DDDDDD",
                             font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        grp3.pack(fill="both", expand=True)

        cols = ("no", "score", "coord", "scale")
        self.tree = ttk.Treeview(grp3, columns=cols, show="headings", height=6)
        for c, t, w in (("no", "#", 26), ("score", "相似度", 60),
                        ("coord", "坐标 (x, y)", 118), ("scale", "缩放", 48)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        self.detail_lbl = tk.Label(grp3, text="坐标以图一为基准：左上角 (0, 0)",
                                   bg="#202020", fg="#9E9E9E", justify="left",
                                   anchor="w", wraplength=288,
                                   font=("Microsoft YaHei UI", 9))
        self.detail_lbl.pack(fill="x", padx=8, pady=(0, 4))

        brow1 = tk.Frame(grp3, bg="#202020")
        brow1.pack(fill="x", padx=8, pady=(0, 4))
        tk.Button(brow1, text="保存标注图", command=self.save_annotated,
                  font=("Microsoft YaHei UI", 9), bd=1, padx=8, pady=4).pack(side="left")
        tk.Button(brow1, text="复制坐标", command=self.copy_coord,
                  font=("Microsoft YaHei UI", 9), bd=1, padx=8, pady=4).pack(side="left", padx=6)

        brow2 = tk.Frame(grp3, bg="#202020")
        brow2.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(brow2, text="清除标注", command=self.clear_marks,
                  font=("Microsoft YaHei UI", 9), bd=1, padx=8, pady=4).pack(side="left")
        tk.Button(brow2, text="重载原图", command=self._load_origin,
                  font=("Microsoft YaHei UI", 9), bd=1, padx=8, pady=4).pack(side="left", padx=6)

        # 状态栏
        self.status = tk.Label(self.root, text="就绪", anchor="w", bg="#1A1A1A",
                               fg="#BDBDBD", font=("Microsoft YaHei UI", 9), padx=10, pady=5)
        self.status.pack(fill="x", side="bottom")

    # ------------------------------------------------------------ 原图载入 --
    def _load_origin(self):
        path = find_origin_image()
        if path is None:
            self.origin_path = None
            self.origin_pil = None
            self.origin_rgb = None
            self.origin_lbl.config(text="原图：未找到 %s" % ORIGIN_FILE, fg="#FF7A7A")
            self._set_status("未找到 %s —— 请把它放到程序所在文件夹（或当前文件夹），然后点「重载原图」" % ORIGIN_FILE)
            self._update_display()
            return
        try:
            pil, rgb = load_rgb_image(path)
        except Exception as e:
            self.origin_lbl.config(text="原图：读取失败", fg="#FF7A7A")
            messagebox.showerror(APP_NAME, "读取原图失败：\n%s\n\n%s" % (path, e))
            return
        self.origin_path = path
        self.origin_pil = pil
        self.origin_rgb = rgb
        self.hits = None
        self.highlight = None
        self._clear_tree()
        self._update_detail(None)
        self.origin_lbl.config(text="原图：%s（%d × %d）" % (path.name, pil.size[0], pil.size[1]),
                               fg="#9E9E9E")
        self._set_status("已载入原图 %s  %d × %d" % (path.name, pil.size[0], pil.size[1]))
        if self.tpl_rgb is not None:
            self.start_match()
        else:
            self._update_display()

    # ------------------------------------------------------------ 热键/截图 --
    def _start_hotkey(self):
        self.hotkey = GlobalHotkey(lambda: self.hot_q.put("snip"))
        ok = self.hotkey.start()
        if not ok:
            self.root.after(600, lambda: self._set_status(
                "提示：%s 全局热键注册失败（可能被微信/QQ/其它截图工具占用）。"
                "可点面板上的「截图」按钮，或修改文件顶部 HOTKEY_VK / HOTKEY_LABEL。" % HOTKEY_LABEL))

    def _poll_hotkey(self):
        try:
            while True:
                self.hot_q.get_nowait()
                self.start_snip()
        except queue.Empty:
            pass
        self.root.after(150, self._poll_hotkey)

    def start_snip(self):
        if self.snip is not None:
            return
        if sys.platform != "win32":
            messagebox.showinfo(APP_NAME, "截图功能仅在 Windows 下可用。")
            return
        try:
            self.snip = SnipOverlay(self.root, self._on_snip_done, self._on_snip_closed)
        except Exception as e:
            self.snip = None
            messagebox.showerror(APP_NAME, "截图失败：%s" % e)

    def _on_snip_closed(self):
        if self.snip is not None and self.snip.box is None:
            self._set_status("已取消截图")
        self.snip = None

    def _on_snip_done(self, pil_img):
        self.snip = None
        self.set_template(pil_img)
        self.root.lift()
        self.root.focus_force()

    def set_template(self, pil_img):
        rgb = np.array(pil_img.convert("RGB"))
        if rgb.shape[0] < 8 or rgb.shape[1] < 8:
            self._set_status("截图区域太小（需大于 8×8 像素），请重新框选")
            return
        self.tpl_pil = pil_img.convert("RGB")
        self.tpl_rgb = rgb
        self.hits = None
        self.highlight = None
        self._clear_tree()
        self._update_detail(None)
        self._show_template_preview()
        self._set_status("已载入待查找图片 %d × %d，开始自动查找…" % (rgb.shape[1], rgb.shape[0]))
        self.start_match()

    def clear_template(self):
        self.tpl_pil = None
        self.tpl_rgb = None
        self.hits = None
        self.highlight = None
        self._clear_tree()
        self._update_detail(None)
        self.tpl_canvas.delete("all")
        self.tpl_canvas.create_text(136, 84, text="按 %s 截图\n双击选区即载入" % HOTKEY_LABEL,
                                    fill="#8A8A8A", font=("Microsoft YaHei UI", 9),
                                    justify="center")
        self.tpl_info.config(text="未载入")
        self._update_display()
        self._set_status("已清空待查找图片")

    def _show_template_preview(self):
        self.tpl_canvas.delete("all")
        w, h = self.tpl_pil.size
        cw, ch = 272, 168
        s = min(cw / float(w), ch / float(h))
        nw, nh = max(1, int(w * s)), max(1, int(h * s))
        disp = self.tpl_pil.resize((nw, nh), Image.LANCZOS if s < 1 else Image.BICUBIC)
        self._tpl_photo = ImageTk.PhotoImage(disp)
        self.tpl_canvas.create_image(cw // 2, ch // 2, image=self._tpl_photo, anchor="center")
        self.tpl_info.config(text="待查找图片：%d × %d 像素" % (w, h))

    # ------------------------------------------------------------ 显示 --
    def _on_canvas_resize(self, _e):
        if self._resize_job:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(140, self._update_display)

    def _update_display(self):
        self._resize_job = None
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        self.canvas.delete("all")
        if self.origin_rgb is None:
            msg = ("未找到原图 %s\n把它放到程序所在文件夹（或当前文件夹）后点“重载原图”" % ORIGIN_FILE)
            self.canvas.create_text(cw // 2, ch // 2, text=msg, fill="#8A8A8A",
                                    font=("Microsoft YaHei UI", 12), justify="center")
            self._photo = None
            return
        base = self.display_pil if self.display_pil is not None else self.origin_pil
        iw, ih = base.size
        s = min(cw / float(iw), ch / float(ih), 2.0)
        nw, nh = max(1, int(iw * s)), max(1, int(ih * s))
        resample = Image.LANCZOS if s < 1 else Image.BICUBIC
        disp = base.resize((nw, nh), resample)
        self._photo = ImageTk.PhotoImage(disp)
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo, anchor="center")
        if self.hits:
            mw, mh = self._read_map_size()
            self.canvas.create_text(
                12, ch - 14, anchor="w",
                text="坐标为图一基准坐标（0–%d / 0–%d）· 显示比例 %.0f%% · 绿框=最佳 · 黄框=选中"
                     % (mw, mh, s * 100),
                fill="#9E9E9E", font=("Microsoft YaHei UI", 9))

    def _on_map_changed(self, *_):
        """坐标范围被修改时，按新基准重算标注与列表。"""
        if self._map_guard or not self.hits:
            return
        self._map_guard = True
        try:
            self._refresh_annotated()
            self._fill_tree(self.hits)
        finally:
            self._map_guard = False

    def _read_map_size(self):
        """读取“坐标范围 X / Y”，非法值回落到默认 400 / 445。"""
        try:
            mw = int(float(self.map_w_var.get()))
            mh = int(float(self.map_h_var.get()))
            if mw <= 0 or mh <= 0:
                raise ValueError
        except Exception:
            mw, mh = DEFAULT_MAP_W, DEFAULT_MAP_H
            self.map_w_var.set(str(mw))
            self.map_h_var.set(str(mh))
        return mw, mh

    def _refresh_annotated(self):
        if self.origin_rgb is None:
            self.display_pil = None
        else:
            mw, mh = self._read_map_size()
            self.display_pil = render_annotated(self.origin_rgb, self.hits,
                                                self.highlight, (mw, mh))
        self._update_display()

    # ------------------------------------------------------------ 匹配流程 --
    def _read_options(self):
        try:
            top_n = max(1, min(10, int(self.count_var.get())))
        except Exception:
            top_n = DEFAULT_COUNT
            self.count_var.set(str(DEFAULT_COUNT))
        return dict(threshold=float(self.thr_var.get()), top_n=top_n,
                    preset=self.preset_var.get(), allow_rotate=bool(self.rotate_var.get()))

    def start_match(self):
        if self.busy:
            return
        if self.origin_rgb is None:
            self._set_status("还没有原图，无法查找。请先放入 %s 或手动选择。" % ORIGIN_FILE)
            return
        if self.tpl_rgb is None:
            self._set_status("还没有待查找图片：按 %s 框选后双击选区。" % HOTKEY_LABEL)
            return
        opt = self._read_options()
        pix = self.origin_rgb.shape[0] * self.origin_rgb.shape[1]
        if pix > 36_000_000:
            if not messagebox.askyesno(APP_NAME, "原图较大（%.1f 百万像素），查找可能较慢，继续？" % (pix / 1e6)):
                return

        self.busy = True
        self.btn_match.config(state="disabled", text="查找中…")
        self.pbar.config(value=0)
        self._set_status("开始匹配（%s / 灵敏度 %.2f / 候选 %d）…" % (opt["preset"], opt["threshold"], opt["top_n"]))

        self.job_q = queue.Queue()
        args = (self.origin_rgb.copy(), self.tpl_rgb.copy(), opt, self.job_q)

        def worker():
            try:
                hits = match_template_multiscale(
                    args[0], args[1], threshold=opt["threshold"], top_n=opt["top_n"],
                    preset=opt["preset"], allow_rotate=opt["allow_rotate"],
                    progress=lambda f: self.job_q.put(("progress", f)))
                self.job_q.put(("done", hits))
            except Exception:
                self.job_q.put(("error", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()
        self.t0 = time.time()
        self.root.after(60, self._poll_job)

    def _poll_job(self):
        finished = False
        try:
            while True:
                msg = self.job_q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self.pbar.config(value=max(0.0, min(1.0, msg[1])) * 100.0)
                elif kind == "done":
                    finished = True
                    self._on_match_done(msg[1])
                elif kind == "error":
                    finished = True
                    self._on_match_error(msg[1])
        except queue.Empty:
            pass
        if not finished and self.busy:
            self.root.after(80, self._poll_job)
        elif finished:
            self.busy = False
            self.btn_match.config(state="normal", text="开始查找")
            self.pbar.config(value=100)

    def _on_match_done(self, hits):
        elapsed = time.time() - getattr(self, "t0", time.time())
        self.hits = hits
        self.highlight = 0 if hits else None
        self._refresh_annotated()
        self._fill_tree(hits)
        if hits:
            best = hits[0]
            mw, mh = self._read_map_size()
            W, H = self.origin_pil.size
            c, _tl, _br = hit_norm(best, W, H, mw, mh)
            self._set_status("找到 %d 处候选，最佳相似度 %.3f，坐标 (%.1f, %.1f)"
                             "（范围 0–%d / 0–%d），耗时 %.1fs"
                             % (len(hits), best["score"], c[0], c[1], mw, mh, elapsed))
        else:
            self._set_status("没有达到阈值的匹配（已用 %.1fs）。可降低“灵敏度”或换更大的选区后重试。" % elapsed)

    def _on_match_error(self, tb):
        self.busy = False
        self.btn_match.config(state="normal", text="开始查找")
        self._set_status("匹配出错，详见弹窗")
        messagebox.showerror(APP_NAME, "匹配出错：\n" + tb[-1200:])

    def _clear_tree(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    def _fill_tree(self, hits):
        self._clear_tree()
        self._iid_map = {}
        mw, mh = self._read_map_size()
        W, H = self.origin_pil.size if self.origin_pil else (1, 1)
        for i, h in enumerate(hits):
            iid = "i%d" % i
            c, _tl, _br = hit_norm(h, W, H, mw, mh)
            self.tree.insert("", "end", iid=iid, values=(
                i + 1, "%.3f" % h["score"],
                "%.1f, %.1f" % (c[0], c[1]), "%.2f×" % h["scale"]))
            self._iid_map[iid] = i
        if hits:
            first = "i0"
            self.tree.selection_set(first)
            self.tree.focus(first)
        self._update_detail(0 if hits else None)

    def _update_detail(self, idx):
        if idx is None or not self.hits:
            self.detail_lbl.config(text="坐标以图一为基准：左上角 (0, 0)")
            return
        mw, mh = self._read_map_size()
        W, H = self.origin_pil.size if self.origin_pil else (1, 1)
        h = self.hits[idx]
        c, tl, br = hit_norm(h, W, H, mw, mh)
        self.detail_lbl.config(text=(
            "#%d 中心 (%.1f, %.1f)\n区域 (%.1f, %.1f) → (%.1f, %.1f)\n"
            "原图像素 (%d, %d)，%d×%d，缩放 %.2f"
            % (idx + 1, c[0], c[1], tl[0], tl[1], br[0], br[1],
               h["x"], h["y"], h["w"], h["h"], h["scale"])))

    def _on_tree_select(self, _e):
        if not self.hits:
            return
        sel = self.tree.selection()
        if not sel:
            return
        idx = self._iid_map.get(sel[0])
        if idx is None:
            return
        self.highlight = idx
        self._update_detail(idx)
        self._refresh_annotated()

    # ------------------------------------------------------------ 保存/清除 --
    def save_annotated(self):
        if self.origin_rgb is None:
            messagebox.showinfo(APP_NAME, "还没有原图。")
            return
        if not self.hits:
            messagebox.showinfo(APP_NAME, "还没有匹配结果可保存。")
            return
        default_dir = str(self.origin_path.parent) if self.origin_path else os.getcwd()
        default_name = "%s_标注_%s.jpg" % (
            (self.origin_path.stem if self.origin_path else "result"),
            time.strftime("%Y%m%d_%H%M%S"))
        path = filedialog.asksaveasfilename(
            title="保存标注图", initialdir=default_dir, initialfile=default_name,
            defaultextension=".jpg",
            filetypes=[("JPEG 图片", "*.jpg"), ("PNG 图片", "*.png")])
        if not path:
            return
        try:
            mw, mh = self._read_map_size()
            img = render_annotated(self.origin_rgb, self.hits, highlight=None,
                                   map_size=(mw, mh))
            if path.lower().endswith(".png"):
                img.save(path, "PNG")
            else:
                img.save(path, "JPEG", quality=92)
            self._set_status("已保存标注图：%s" % path)
            messagebox.showinfo(APP_NAME, "已保存：\n%s" % path)
        except Exception as e:
            messagebox.showerror(APP_NAME, "保存失败：%s" % e)

    def copy_coord(self):
        if not self.hits:
            messagebox.showinfo(APP_NAME, "还没有匹配结果。")
            return
        idx = self.highlight if self.highlight is not None else 0
        idx = min(max(idx, 0), len(self.hits) - 1)
        mw, mh = self._read_map_size()
        W, H = self.origin_pil.size if self.origin_pil else (1, 1)
        c, tl, br = hit_norm(self.hits[idx], W, H, mw, mh)
        text = "#%d 中心 (%.1f, %.1f)  区域 (%.1f, %.1f) → (%.1f, %.1f)" % (
            idx + 1, c[0], c[1], tl[0], tl[1], br[0], br[1])
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("已复制到剪贴板：" + text)

    def clear_marks(self):
        self.hits = None
        self.highlight = None
        self.display_pil = None
        self._clear_tree()
        self._update_detail(None)
        self._update_display()
        self._set_status("已清除标注")

    # ------------------------------------------------------------ 杂项 --
    def _set_status(self, text):
        self.status.config(text=text)

    def _on_close(self):
        try:
            if self.hotkey:
                self.hotkey.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def app_dir():
    """程序所在目录（打包成 exe 后是 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main():
    enable_dpi_awareness()
    try:
        App().run()
    except Exception:
        tb = traceback.format_exc()
        # 打包后没有控制台，把堆栈写到 exe 同目录的日志里，方便排查
        try:
            log = app_dir() / "image_locator_error.log"
            log.write_text(tb, encoding="utf-8")
        except Exception:
            pass
        try:
            messagebox.showerror(
                APP_NAME,
                "程序启动失败，详细信息已写入：\n%s\n\n%s" % (
                    app_dir() / "image_locator_error.log", tb[-600:]))
        except Exception:
            pass


if __name__ == "__main__":
    main()
