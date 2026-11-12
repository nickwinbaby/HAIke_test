import sys

import cv2
import numpy as np


source, model_path, output = sys.argv[1:4]
start_seconds = float(sys.argv[4])
duration_seconds = float(sys.argv[5])

cap = cv2.VideoCapture(source)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
cap.set(cv2.CAP_PROP_POS_MSEC, start_seconds * 1000.0)

sr = cv2.dnn_superres.DnnSuperResImpl_create()
sr.readModel(model_path)
sr.setModel("fsrcnn", 2)

writer = cv2.VideoWriter(
    output,
    cv2.VideoWriter_fourcc(*"mp4v"),
    fps,
    (1920, 1080),
)

frame_limit = round(duration_seconds * fps)
for index in range(frame_limit):
    ok, frame = cap.read()
    if not ok:
        break

    # Remove low-level chroma noise without smearing faces, then run real 2x
    # neural super-resolution.  The final downsample suppresses model ringing.
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    cr = cv2.GaussianBlur(cr, (3, 3), 0.55)
    cb = cv2.GaussianBlur(cb, (3, 3), 0.55)
    cleaned = cv2.cvtColor(cv2.merge((y, cr, cb)), cv2.COLOR_YCrCb2BGR)
    enlarged = sr.upsample(cleaned)
    content = cv2.resize(enlarged, (1320, 1080), interpolation=cv2.INTER_AREA)

    blur = cv2.GaussianBlur(content, (0, 0), 1.05)
    content = cv2.addWeighted(content, 1.62, blur, -0.62, 0)

    canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
    canvas[:, 300:1620] = content
    writer.write(canvas)

    if index % 30 == 0:
        print(f"processed {index}/{frame_limit}", flush=True)

writer.release()
cap.release()
print(f"wrote {output}", flush=True)
