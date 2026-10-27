"""纯 Python 生成 agenthub.ico（BMP 帧，无第三方依赖）。

与 UI favicon 同款：橙色圆角方块 + 深色两颗圆。直接采样 SVG 同款几何。
"""
import struct

SIZES = [16, 24, 32, 48, 64, 128, 256]
SS = 4  # 超采样倍数


def _rounded_rect_mask(n, radius):
    """返回 n*n 的 alpha 掩码（超采样后降采样）。"""
    big = n * SS
    rad = int(big * 0.25)  # 圆角比例与 favicon rx=8/32 一致
    mask = bytearray(big * big)
    r2 = rad * rad
    for y in range(big):
        for x in range(big):
            # 圆角判断：在四个角区域内时比较到圆心距离
            dx = dy = 0
            in_corner = False
            if x < rad and y < rad:
                dx, dy, in_corner = rad - x, rad - y, True
            elif x >= big - rad and y < rad:
                dx, dy, in_corner = x - (big - rad - 1), rad - y, True
            elif x < rad and y >= big - rad:
                dx, dy, in_corner = rad - x, y - (big - rad - 1), True
            elif x >= big - rad and y >= big - rad:
                dx, dy, in_corner = x - (big - rad - 1), y - (big - rad - 1), True
            if not in_corner or dx * dx + dy * dy <= r2:
                mask[y * big + x] = 255
    return mask, big


def _downsample(mask, big, n):
    out = bytearray(n * n)
    step = big // n
    for y in range(n):
        for x in range(n):
            acc = 0
            for yy in range(step):
                base = (y * step + yy) * big + x * step
                for xx in range(step):
                    acc += mask[base + xx]
            out[y * n + x] = acc // (step * step)
    return out


def _circle_layer(n, cx, cy, rad_ratio, color, alpha, bg):
    """在 bg 上叠一个实心圆（BGRA）。"""
    rad = rad_ratio * n
    r2 = rad * rad
    for y in range(n):
        for x in range(n):
            dx = x + 0.5 - cx * n
            dy = y + 0.5 - cy * n
            # 用平滑边缘
            d2 = dx * dx + dy * dy
            edge = rad
            if d2 <= (edge - 0.7) ** 2:
                cov = alpha
            elif d2 >= (edge + 0.7) ** 2:
                cov = 0
            else:
                t = (d2 ** 0.5 - (edge - 0.7)) / 1.4
                cov = int(alpha * (1 - max(0.0, min(1.0, t))))
            if cov:
                i = (y * n + x) * 4
                a = cov / 255
                bg[i] = int(color[0] * a + bg[i] * (1 - a))
                bg[i + 1] = int(color[1] * a + bg[i + 1] * (1 - a))
                bg[i + 2] = int(color[2] * a + bg[i + 2] * (1 - a))
                bg[i + 3] = max(bg[i + 3], cov)
    return bg


ORANGE = (60, 163, 226)   # BGR: #e2a33c
DARK = (19, 11, 8)        # BGR: #080b13


def make_frame(n):
    mask, big = _rounded_rect_mask(n, 0)
    alpha = _downsample(mask, big, n)
    bg = bytearray(n * n * 4)  # BGRA
    for i in range(n * n):
        a = alpha[i]
        bg[i * 4 + 0] = ORANGE[0]
        bg[i * 4 + 1] = ORANGE[1]
        bg[i * 4 + 2] = ORANGE[2]
        bg[i * 4 + 3] = a
    # 两颗圆：大圆 (12,12,r5)，小圆 (22,21,r3)，按 32 视格换算比例
    _circle_layer(n, 12 / 32, 12 / 32, 5 / 32, DARK, 255, bg)
    _circle_layer(n, 22 / 32, 21 / 32, 3 / 32, DARK, 153, bg)
    return bytes(bg)


def bmp_frame(n, pixels):
    """BITMAPINFOHEADER + 像素（自底向上）+ AND 掩码。"""
    hdr = struct.pack("<IiiHHIIiiII", 40, n, n * 2, 1, 32, 0, n * n * 4, 0, 0, 0, 0)
    rows = bytearray()
    for y in range(n - 1, -1, -1):
        rows += pixels[y * n * 4:(y + 1) * n * 4]
    and_stride = ((n + 31) // 32) * 4
    and_mask = b"\x00" * (and_stride * n)  # alpha 已表达透明，AND 全 0
    return hdr + bytes(rows) + and_mask


def build_ico(path):
    frames = []
    for n in SIZES:
        frames.append((n, bmp_frame(n, make_frame(n))))
    header_size = 6 + 16 * len(frames)
    offset = header_size
    entries = b""
    body = b""
    for n, data in frames:
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32,
                               len(data), offset)
        body += data
        offset += len(data)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(frames)) + entries + body)
    print("saved", path)


if __name__ == "__main__":
    build_ico(r"D:\agent-hub\agenthub.ico")
