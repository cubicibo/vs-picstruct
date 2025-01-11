# VS-PicStruct
Tool to analyze a VFR clip and produce a list of H.26x "pic struct" instructions to store the VFR clip in a CFR container exploiting soft pulldown.

## Purpose
Use with this [x264 mod](https://github.com/cubicibo/x264), and more specifically the `--psfile`parameter.

## Usage

```python
from vspicstruct import PicStructFileV1

container_fpsnum = 30000
container_fpsden = 1001
default_field_order = 2 # TFF
psfile_out = 'some/path/file.txt'

psf = PicStructFileV1(container_fpsnum, container_fpsden, psfile_out, default_field_order)

# E.g. final clip is made of three different parts:
#23.976p
clip1 = core.std.BlankClip(..., fpsnum=24000, fpsden=1001)
clip1 = core.std.SetFieldBased(clip1, 0)

#29.97p
clip2 = core.std.BlankClip(..., fpsnum=30000, fpsden=1001)
clip2 = core.std.SetFieldBased(clip2, 0)

#59.94i TFF
clip3 = core.std.BlankClip(..., fpsnum=30000, fpsden=1001)
clip3 = core.std.SetFieldBased(clip3, 2)

clip = clip1 + clip2 + clip3

#write index file
psf.index(clip)

#output clip
clip.set_output()
```

Then, you can use the generated `file.txt` with the aforementionned custom x264:<br/>
`x264 [...] --psfile "some/path/file.txt" --fps 30000/1001 [...] -o out.264`<br/>

- You must specify the container framerate to x264 via `--fps`.
- If your clip contains solely 23.976p and 29.97p, `--fake-interlaced` must be specified.
- If your clip contains real interlaced footage (temporally disjoint field pairs), you must specify the field order (`--tff` or `--bff`).

## Supported combination
Any sane pulldown is supported. I.e as long as `container_fps/clip_fps` = `repetitions/cycles` is a well-behaved fraction with cycles <= round(framerate).

Film content at 18/24/48 fps should first be converted to the closest NTSC framerate. For example, `18 fps` in a `29.97` container has no solution, while `18000/1001 fps` will produce the desired pic struct sequence:
`Frame-Doubling -> Top-Bottom-Top -> Bottom-Top-Bottom.`

## Example index
Here's an index for a clip with 23.976p, 59.94i and 29.97p sections.
```
# picstruct format v1
# format: frame_id frame_field_order pic_struct

#TB TBT BT BTB, (24000/1001), P
0 0 5
1 0 4
2 0 6
3 0 3
4 0 5
5 0 4
...

#TB, (30000/1001), TFF
20 2 3
...

#PF, (30000/1001), P
35 0 0
...
```