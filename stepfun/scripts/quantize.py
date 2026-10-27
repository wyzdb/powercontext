#!/usr/bin/env python3
"""Reproduce an INT8 dynamic-quantized variant of bge-small-zh-v1.5.

The published Transformers.js file (model_int8.onnx) was produced with
per-channel quantization and reduce_range=True. This script defaults to
reduce_range=False so the two variants can be compared; pass --reduce-range to
match the published configuration.

Usage:
  python scripts/quantize.py \
    --input public/models/Xenova/bge-small-zh-v1.5/onnx/model.onnx \
    --output public/models/Xenova/bge-small-zh-v1.5/onnx/model_int8_self.onnx
"""
from __future__ import annotations

import argparse
from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reduce-range", action="store_true")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"input not found: {args.input}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    quantize_dynamic(
        model_input=str(args.input),
        model_output=str(args.output),
        weight_type=QuantType.QInt8,
        per_channel=True,
        reduce_range=args.reduce_range,
    )

    before = args.input.stat().st_size
    after = args.output.stat().st_size
    print(f"input : {before:,} bytes ({before / 1024 / 1024:.2f} MiB)")
    print(f"output: {after:,} bytes ({after / 1024 / 1024:.2f} MiB)")
    print(f"compression: {before / after:.2f}x")
    print(f"reduce_range: {args.reduce_range}")
    print(
        "To test this file in Transformers.js, copy it over onnx/model_int8.onnx "
        "and reload with dtype='int8'."
    )


if __name__ == "__main__":
    main()
