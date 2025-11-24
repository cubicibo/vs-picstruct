# VS-PicStruct
Tool to analyze a VFR clip and produce a list of H.26x "pic struct" instructions to store the VFR clip in a CFR container exploiting soft pulldown.

## Purpose
Use with this [x264 mod](https://github.com/cubicibo/x264), and more specifically the `--psfile` parameter.

## Usage

```python
from vspicstruct import PicStructFileV1

psfile_out = 'some/path/psfile.txt'

#Tag container as interlaced (TFF), as one section has a 59.94 field rate.
default_field_order = 2
container_fpsnum = 30000
container_fpsden = 1001

psf = PicStructFileV1(container_fpsnum, container_fpsden, psfile_out, default_field_order)

# E.g. final 29.97 clip is made of five different parts:
#23.976p
clip1 = core.std.BlankClip(..., fpsnum=24000, fpsden=1001)
clip1 = core.std.SetFieldBased(clip1, 0) # optional, by default sections are assumed progressive

#59.94i TFF
clip2 = core.std.BlankClip(..., fpsnum=30000, fpsden=1001)
clip2 = core.std.SetFieldBased(clip2, 2)

#29.97p
clip3 = core.std.BlankClip(..., fpsnum=30000, fpsden=1001)

#18p
clip4 = core.std.BlankClip(..., fpsnum=18000, fpsden=1001)

#23.976, and prefer a progressive pull-down sequence over an interlaced one (more jarring to the viewer)
clip5 = core.std.BlankClip(..., fpsnum=24000, fpsden=1001)
clip5 = core.std.SetFrameProps(clip5, FavorProgressive=True)

clip = clip1 + clip2 + clip3 + clip4 + clip5

#write psfile index
psf.index(clip)

#output clip
clip.set_output()
```

Then, you can use the generated `psfile.txt` with the aforementionned custom x264 binary:<br/>
`x264 [...] --psfile "some/path/psfile.txt" --fps 30000/1001 [...] -o out.264`<br/>

- You must specify the container framerate to x264 via `--fps`.
- If your clip has temporally disjoint field pairs at a point, you must specify the field order (`--tff` or `--bff`) in the command.
- For BD exports, you must ensure the GOP duration does not exceed 1 second at any time. In the custom x264 builds, `--keyint` unit is defined with respect to the container rate.
    - For one second GOP `--keyint` must equal the integer framerate of the container (e.g. 30 for 29.97 fps)
    - In other words, `--keyint` is no longer defined as a frame count but by the number of container refreshes. E.g. if you use `--pulldown 32` on a 23.976 input, then `--keyint` would no longer be 24, but 30!
- `--fake-interlaced` should be specified for progressive-only sequences in interlaced containers.


## Supported combination
Any sane pulldown is supported. I.e as long as `container_fps/clip_fps` = `repetitions/cycles` is a well-behaved fraction with `cycles <= round(framerate)`.

Film content at 18/24/48 fps should first be converted to the closest NTSC framerate. For example, `18 fps` in a `29.97` container has no solution, while `18000/1001 fps` will produce the desired pic struct sequence:
`Frame-Doubling -> Progressive Frame -> Frame-Doubling.`

## Example index
Here's the output index for the above example:
```
# picstruct format v1
# format: frame_id frame_field_order pic_struct

#TB TBT BT BTB, (24000/1001), P, fp=0
0 0 5
1 0 4
2 0 6
3 0 3
4 0 5
5 0 4
...

#TB, (30000/1001), TFF fp=0
20 2 3
...

#PF, (30000/1001), P fp=0
35 0 0
...

#FD PF FD, (18000/1001), P fp=0
50 0 0
51 0 7
52 0 7
53 0 0
...

#PF FD PF PF, (24000/1001), P fp=1
70 0 7
71 0 0
72 0 0
73 0 0
74 0 7
...
```

## References
- ITU-T Rec H.264 (Table D-1 notably)
- ITU-T Rec H.265 (Table D-2)
- x264 and x265 source code.