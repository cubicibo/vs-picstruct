#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIT License

Copyright (c) 2025-2026 cubicibo

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

import re

from argparse import ArgumentParser
from pathlib import Path
from fractions import Fraction
from vspicstruct import CodecConfig, VideoCodec, VideoFieldOrder, PulldownZone, VideoSequence, PicStructFileV1, VideoContext, PulldownType

def main():
    parser = ArgumentParser()
    parser.add_argument("-i", "--zonesfile", type=str, help="Set input zones file.", default='', required=True)
    parser.add_argument('-f', '--fps', help="Framerate, as a fraction: n/d (def:  %(default)s)", type=Fraction, required=True)
    parser.add_argument('-o', '--order', help="default field order (0: progressive, 1: bff, 2:tff)] (def:  %(default)s)", type=int, default=2, required=False)
    parser.add_argument('-c', '--codec', help="Target codec (AVC or HEVC).", type=str, required=True)
    parser.add_argument('-m', '--mixed', help="Flag to allow mixed interlaced+progressive pulldown.", action='store_true', default=False, required=False)
    parser.add_argument("output", type=str)
    args = parser.parse_args()

    args.zonesfile = Path(args.zonesfile).expanduser().resolve()
    assert args.zonesfile.exists(), "zones file does not exist."

    args.output = Path(args.output).expanduser().resolve()
    assert args.output.parent.exists(), "Output path seems incorrect (parent folder does not exist)."

    args.codec = args.codec.lower()
    if args.codec in ('avc', 'h264'):
        args.codec = VideoCodec.AVC
    elif args.codec in ('hevc', 'h265'):
        args.codec = VideoCodec.HEVC
    else:
        raise ValueError("Unknown/unsupported video codec. Expected AVC or HEVC.")

    assert args.order in range(0, 3), "Incorrect default frame-field order (expected 0, 1 or 2)."
    args.order = VideoFieldOrder(args.order)
    if args.order > 0 and args.codec == VideoCodec.HEVC:
        raise RuntimeError("Interlaced with HEVC is not supported. Specify --order 0 if you haven't.")

    args.fps = Fraction(args.fps)
    assert args.fps.numerator > 0

    codec = CodecConfig(args.fps, args.order, args.codec, not args.mixed)
    vcx = VideoContext(codec)
    zones = []

    with open(args.zonesfile, 'r') as f:
        for line in f.readlines():
            res = re.match(r"\s*?(\d+)\s+(\d+/\d+)\s+(\d)\s{0,}([a-zA-Z])?", line.strip())
            if res is None:
                continue
            groups = res.groups()
            assert len(groups) >= 3, f"Found incomplete line in zonesfile: {line}"
            num_frames = int(groups[0])
            fps = Fraction(groups[1])
            field_order = VideoFieldOrder(int(groups[2]))
            vidseq = VideoSequence(fps, field_order)
            if groups[3] is None:
                pulldown_type = vcx.select_pulldown(vidseq, False)
            else:
                pld_type = groups[3].strip().lower()
                assert pld_type in ('i', 'p'), "unknown pulldown type (expected i or p, got '{}')"
                pulldown_type = PulldownType.PROGRESSIVE if pld_type == 'p' else PulldownType.INTERLACED
            pdz = PulldownZone(vidseq, pulldown_type, num_frames)
            zones.append(pdz)
    ####
    if len(zones) == 0:
        raise RuntimeError("No valid zone identified in input file, giving up.")

    print("======== ZONES ======== ")
    print("Zones      Frames ranges    FPS     PictType  PldType")
    frames = 0
    for zk, zone in enumerate(zones):
        field_order_acronym = ''.join(x[0] for x in zone.sequence.field_order.name.split('_'))
        print(f"zone {zk:3}: {frames:7}->{(frames+zone.frames-1):7}, {zone.sequence.fps}, {field_order_acronym:3}  :  {zone.pulldown_type.name[0].lower()}")
        frames += zone.frames

    print("========= LOG ========= ")
    structs = vcx.find_structures(zones)

    psf = PicStructFileV1(args.output)
    psf.write(structs, zones)

    print(f"Wrote psfile at '{args.output}'.")
####

if __name__ == '__main__':
    main()
