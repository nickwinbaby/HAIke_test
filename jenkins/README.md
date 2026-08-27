# Jenkins entry points

These wrapper scripts use ASCII paths so Jenkins Windows batch files do not need
to contain Chinese path text.

Layered JSON suite:

```bat
D:
cd /d C:\Users\G1006871\Desktop\BIANYI
D:\Python310\python.exe jenkins\run_layered_suite.py
```

Basic fixed flow:

```bat
D:
cd /d C:\Users\G1006871\Desktop\BIANYI
D:\Python310\python.exe jenkins\run_basic_case.py
```

Dry-run check:

```bat
D:\Python310\python.exe jenkins\run_layered_suite.py --dry-run --time-scale 0.01
```

