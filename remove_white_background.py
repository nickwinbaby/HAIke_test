from collections import deque
from pathlib import Path
from PIL import Image

src = Path(r"D:\Program Files\Tencent\xwechat_files\wxid_9513365134312_8e67\temp\RWTemp\2026-09\dee8094b4a3ef1944f37762d9a2960e9\a593e94387c08ce7e4be5e469197ca6a.png")
dst = Path("a593e94387c08ce7e4be5e469197ca6a_transparent.png")

im = Image.open(src).convert("RGBA")
w, h = im.size
px = im.load()

# Flood-fill only near-white pixels connected to the image boundary. This keeps
# isolated white details inside the illustration (e.g. the pin center).
seen = bytearray(w * h)
q = deque()
for x in range(w):
    q.append((x, 0)); q.append((x, h - 1))
for y in range(1, h - 1):
    q.append((0, y)); q.append((w - 1, y))

def is_background(c):
    r, g, b, a = c
    return a > 0 and r >= 242 and g >= 242 and b >= 242 and max(r, g, b) - min(r, g, b) <= 8

while q:
    x, y = q.popleft()
    i = y * w + x
    if seen[i] or not is_background(px[x, y]):
        continue
    seen[i] = 1
    if x: q.append((x - 1, y))
    if x + 1 < w: q.append((x + 1, y))
    if y: q.append((x, y - 1))
    if y + 1 < h: q.append((x, y + 1))

# Remove connected background and soften only the near-white fringe.
for y in range(h):
    for x in range(w):
        i = y * w + x
        if seen[i]:
            px[x, y] = (px[x, y][0], px[x, y][1], px[x, y][2], 0)
        else:
            r, g, b, a = px[x, y]
            if a and r >= 225 and g >= 225 and b >= 225 and max(r, g, b) - min(r, g, b) <= 12:
                # Preserve light artwork while reducing a white halo at the cutout.
                whiteness = min(r, g, b)
                alpha = max(0, min(255, int((255 - whiteness) * 8)))
                if alpha < a:
                    px[x, y] = (r, g, b, alpha)

im.save(dst, "PNG")
print(dst.resolve())
