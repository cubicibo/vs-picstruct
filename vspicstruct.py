#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIT License

Copyright (c) 2025 cubicibo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from typing import Generator, TextIO
from fractions import Fraction
from enum import IntEnum
from pathlib import Path

import vapoursynth as vs
core = vs.core

class PicStruct(IntEnum):
    PROGRESSIVE_FRAME = 0
    TOP               = 1  #PAFF, unsupported by x264
    BOTTOM            = 2  #PAFF, unsupported by x264
    TOP_BOTTOM        = 3
    BOTTOM_TOP        = 4
    TOP_BOTTOM_TOP    = 5
    BOTTOM_TOP_BOTTOM = 6
    FRAME_DOUBLING    = 7
    FRAME_TRIPLING    = 8
    TOP_PREVBOTTOM    = 9  #HEVC
    BOTTOM_PREVTOP    = 10 #HEVC
    TOP_NEXTBOTTOM    = 11 #HEVC
    BOTTOM_NEXTTOP    = 12 #HEVC

    @classmethod
    def get_via(cls, field_count: int, last_field: PROGRESSIVE_FRAME) -> 'PicStruct':
        if   field_count == 1 and last_field != cls.TOP:
            return cls(cls.TOP)
        elif field_count == 1 and last_field != cls.BOTTOM:
            return cls(cls.BOTTOM)
        elif field_count == 2 and last_field != cls.TOP:                
            return cls(cls.TOP_BOTTOM)
        elif field_count == 2 and last_field != cls.BOTTOM:                
            return cls(cls.BOTTOM_TOP)
        elif field_count == 3 and last_field != cls.TOP:
            return cls(cls.TOP_BOTTOM_TOP)
        elif field_count == 3 and last_field != cls.BOTTOM:
            return cls(cls.BOTTOM_TOP_BOTTOM)
        assert 0, f"No PicStruct to repeat {field_count} fields."
        
    @classmethod
    def get_via_p(cls, frame_count: int) -> 'PicStruct':
        if frame_count == 1:
            return cls(cls.PROGRESSIVE_FRAME)
        elif frame_count == 2:
            return cls(cls.FRAME_DOUBLING)
        elif frame_count == 3:
            return cls(cls.FRAME_TRIPLING)
        assert 0, f"No PicStruct to repeat {frame_count} frames."

    def get_last_field(self) -> 'PicStruct':
        if self.name.endswith("TOP"):
            return __class__(__class__.TOP)
        elif self.name.endswith('BOTTOM'):
            return __class__(__class__.BOTTOM)
        return __class__(__class__.PROGRESSIVE_FRAME)

    def is_progressive(self) -> bool:
        return self in [0, 7, 8]

class FrameFieldEncoding(IntEnum):
    P = 0
    BFF = 1
    TFF = 2

class VideoCodingFormat(IntEnum):
    H264 = 0
    H265 = 1

class Pulldown:
    def __init__(self, pattern: list[PicStruct]) -> None:
        if pattern is None:
            pattern = [PicStruct.PROGRESSIVE_FRAME]
        self._pattern = pattern
        self._state = 0

    def step(self) -> PicStruct:
        self._state = (self._state + 1) % len(self._pattern)
        return self._pattern[self._state]

###
# for those who don't trust the algorithm
class Pulldown32(Pulldown):
    def __init__(self) -> None:
        super().__init__([PicStruct.TOP_BOTTOM,
                          PicStruct.TOP_BOTTOM_TOP,
                          PicStruct.BOTTOM_TOP,
                          PicStruct.BOTTOM_TOP_BOTTOM])

class Pulldown64(Pulldown):
    def __init__(self) -> None:
        super().__init__([PicStruct.FRAME_DOUBLING,
                          PicStruct.FRAME_TRIPLING])

class SoftDoubling(Pulldown):
    def __init__(self) -> None:
        super().__init__([PicStruct.FRAME_DOUBLING])

class SoftTripling(Pulldown):
    def __init__(self) -> None:
        super().__init__([PicStruct.FRAME_TRIPLING])

class PulldownEU(Pulldown):
    def __init__(self) -> None:
        super().__init__([PicStruct.TOP_BOTTOM] +      [PicStruct.TOP_BOTTOM_TOP] +\
                         [PicStruct.BOTTOM_TOP] * 11 + [PicStruct.BOTTOM_TOP_BOTTOM] +\
                         [PicStruct.TOP_BOTTOM] * 10)

class Pulldown22(Pulldown):
    def __init__(self) -> None:
        super().__init__([PicStruct.TOP_BOTTOM])
##

class TimingContext:
    def __init__(self,
        fpsnum: int,
        fpsden: int,
        field_based: int,
    ) -> None:
        assert fpsden > 0 and fpsnum > 0
        self.fps = Fraction(fpsnum, fpsden)
        self.field_based = field_based

    def determine_pulldown(self,
        clip_fpsnum: int,
        clip_fpsden: int,
        override_field_based: FrameFieldEncoding | int = FrameFieldEncoding.TFF,
        prefer_progressive: bool = False,
    ) -> Pulldown:
        assert clip_fpsnum > 0 and clip_fpsden > 0
        fps = Fraction(clip_fpsnum, clip_fpsden)

        ratio = self.fps/fps
        assert ratio >= 1, "clip FPS cannot exceed container FPS."
        assert ratio.denominator < round(self.fps), "No pattern within one second"
        can_force_progressive = float(ratio).is_integer() and override_field_based == FrameFieldEncoding.P

        if self.field_based > 0 and not can_force_progressive:
            if override_field_based == FrameFieldEncoding.P:
                try:
                    #See if we have a progressive sequence
                    sequence_p = __class__._determine_for_progressive(ratio)
                except AssertionError:
                    sequence_p = None
                else:
                    if prefer_progressive:
                        return Pulldown(sequence_p)
            try:
                sequence = self._determine_field_reps(ratio, self.field_based if 0 == override_field_based else override_field_based)
            except AssertionError as ae:
                if sequence_p is None:
                    raise ae
                sequence = sequence_p
        else:
            assert override_field_based == FrameFieldEncoding.P or can_force_progressive
            sequence = __class__._determine_for_progressive(ratio)
        return Pulldown(sequence)

    def _determine_field_reps(self, ratio: Fraction, field_order: int) -> list[PicStruct]:
        if field_order == 2:
            new_ps = PicStruct.BOTTOM
        elif field_order == 1:
            new_ps = PicStruct.TOP
        else: #does not matter
            new_ps = PicStruct.PROGRESSIVE_FRAME
        psf = []
        error_sum = 0
        for _ in range(ratio.denominator):
            current = round(2*ratio + error_sum)
            error_sum += 2*ratio - current
            new_ps = PicStruct.get_via(current, new_ps.get_last_field())
            psf.append(new_ps)
        return psf

    @staticmethod
    def _determine_for_progressive(ratio: Fraction) -> list[PicStruct]:
        psf = []
        error_sum = 0
        for _ in range(ratio.denominator):
            current = round(ratio + error_sum)
            error_sum += ratio - current
            psf.append(PicStruct.get_via_p(current))
        return psf

class PicStructFileV1:
    def __init__(self,
        fps_num: int,
        fps_den: int,
        file: Path | str,
        field_based: FrameFieldEncoding | int = FrameFieldEncoding.TFF,
    ) -> None:
        self._fp = Path(file)
        assert self._fp.parent.exists()
        self._fps = Fraction(fps_num, fps_den)
        assert 0 <= field_based <= 2
        self.field_based = field_based

    def _write_header(self, f: TextIO) -> None:
        f.write("# picstruct format v1\n\n")
        f.write("# format: frame_id frame_field_order pic_struct\n")

    @staticmethod
    def _extract_props(props) -> tuple[int, int, int, int]:
        fb = props.get('_FieldBased', 0) #if unset, then it is probably progressive
        tbd = props.get('_DurationNum')
        tbn = props.get('_DurationDen')
        prefer_progressive = props.get('FavorProgressive', False)
        return fb, tbd, tbn, prefer_progressive

    def generate(self, clip: vs.VideoNode) -> Generator[tuple[int, int, PicStruct], None, None]:
        tc = TimingContext(self._fps.numerator, self._fps.denominator, field_based=self.field_based)
        cfps, cfo = None, None

        for k in range(len(clip)):
            fb, tbd, tbn, prefer_progressive = __class__._extract_props(clip.get_frame(k).props)
            if cfps != Fraction(tbn, tbd) or fb != cfo:
                pdc = tc.determine_pulldown(tbn, tbd, fb, prefer_progressive)
                cfo = fb
                cfps = Fraction(tbn, tbd)
            yield (k, fb, pdc.step())

    def index(self, clip: vs.VideoNode) -> None:
        tc = TimingContext(self._fps.numerator, self._fps.denominator,
                           field_based=self.field_based)
        cfps, cfo = None, None

        with open(self._fp, 'w') as f:
            self._write_header(f)
            for k in range(len(clip)):
                fb, tbd, tbn, prefer_progressive = __class__._extract_props(clip.get_frame(k).props)
                if cfps != Fraction(tbn, tbd) or fb != cfo:
                    pdc = tc.determine_pulldown(tbn, tbd, fb, prefer_progressive)
                    cfo = fb
                    f.write("\n#" + ' '.join(map(lambda x: ''.join(map(lambda y: y[0], x.name.split('_'))), pdc._pattern)) + f", ({tbn}/{tbd}), {FrameFieldEncoding(fb).name} fp={int(prefer_progressive)}\n")
                    cfps = Fraction(tbn, tbd)
                f.write(f"{k} {fb} {pdc.step()}\n")
