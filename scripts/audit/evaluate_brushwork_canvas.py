#!/usr/bin/env python3
"""
scripts/audit/evaluate_brushwork_canvas.py

Programmatic HTML Canvas Brushwork Evaluator for Slender Gold Calligraphy.
Executes rendering in headless Chrome (google-chrome --headless --no-sandbox --disable-gpu --dump-dom)
and inspects both compileStrokePhysics vector state and ctx.getImageData(0, 0, 792, 792)
pixel arrays without saving or reading PNG files.

Metrics:
  M1: Retrograde Boundary Folds (retrograde_steps, min_edge_dot_tangent, self_intersections)
  M2: High-Frequency Boundary Sawtooth / Jitter (edge_jitter_ratio, normal_sign_flip_rate)
  M3: Hook Trajectory & Splice Discontinuity (hook_tip_error_px, hook_angle_error_deg, hook_splice_jump_px)
  M4: Raster Medial-Axis / Cross-Section Width Profile (max_width_step_px, tip_width_px, kvg_endpoint_unreached_px)
  M5: Mechanical Barcode Kasure Detection (max_cross_section_gaps, regular_kasure_stripes)
  M6: Longitudinal Spine Tone Oscillation / Polka-Dot Pooling (spine_tone_oscillation, spine_tone_std_diff)
  M7: Topological Integrity (disconnected_components)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import ids_parser
import glyph_service

DEFAULT_BENCHMARK_CHARS = ["永", "水", "嵐", "成", "九", "子", "心", "道", "鬱", "涙"]
APP_JS_PATH = BASE_DIR / "static" / "app.js"

# Thresholds for categorizing defects
THRESHOLDS = {
    "m1_retrograde_steps": 1,
    "m1_self_intersections": 1,
    "m2_edge_d2_px": 0.08,
    "m2_normal_sign_flip_rate": 0.25,
    "m3_hook_tip_error_px": 12.0,
    "m3_hook_angle_error_deg": 10.0,
    "m3_hook_splice_jump_px": 6.0,
    "m4_max_width_step_px": 6.0,
    "m4_kvg_endpoint_unreached_px": 4.0,
    "m5_max_cross_section_gaps": 3,
    "m6_spine_tone_oscillation": 3,
    "m6_spine_tone_ripple": 1.2,
    "m7_disconnected_components": 2,
    "m8_max_tip_ratio": 0.16,
    "m8_min_u80_ratio": 0.35,
    "m8_min_u90_ratio": 0.20,
    "m8_max_slope_dev": 0.08,
    "m9_max_mid_bulge_ratio": 1.05,
    "m9_max_body_ratio": 1.14,
    "m9_max_mid_arch_excess_px": 1.0,
}


def build_evaluation_html(char_stroke_map: dict[str, list[dict[str, Any]]], app_js_content: str) -> str:
    """Builds a self-contained HTML page that runs JS evaluation in headless Chrome."""
    payload_json = json.dumps(char_stroke_map)

    eval_script = r"""
(function() {
  const charStrokeMap = """ + payload_json + r""";
  const results = {};

  // Segment intersection helper for polyline self-intersection checks
  function checkSegmentsIntersect(p1, p2, p3, p4) {
    function ccw(A, B, C) {
      return (C.y - A.y) * (B.x - A.x) - (B.y - A.y) * (C.x - A.x);
    }
    const min1x = Math.min(p1.x, p2.x), max1x = Math.max(p1.x, p2.x);
    const min1y = Math.min(p1.y, p2.y), max1y = Math.max(p1.y, p2.y);
    const min2x = Math.min(p3.x, p4.x), max2x = Math.max(p3.x, p4.x);
    const min2y = Math.min(p3.y, p4.y), max2y = Math.max(p3.y, p4.y);
    if (max1x < min2x || max2x < min1x || max1y < min2y || max2y < min1y) return false;
    const c1 = ccw(p1, p2, p3);
    const c2 = ccw(p1, p2, p4);
    const c3 = ccw(p3, p4, p1);
    const c4 = ccw(p3, p4, p2);
    return ((c1 > 0 && c2 < 0) || (c1 < 0 && c2 > 0)) && ((c3 > 0 && c4 < 0) || (c3 < 0 && c4 > 0));
  }

  function countSelfIntersections(chain) {
    if (!chain || chain.length < 4) return 0;
    let count = 0;
    for (let i = 0; i < chain.length - 1; i++) {
      for (let j = i + 2; j < chain.length - 1; j++) {
        if (checkSegmentsIntersect(chain[i], chain[i+1], chain[j], chain[j+1])) {
          count++;
        }
      }
    }
    return count;
  }

  // Exact 1x1 8-connected component labeling on stroke bounding box
  function countConnectedComponents(imgData, W, H) {
    let minX = W, maxX = -1, minY = H, maxY = -1;
    const data = imgData.data;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const a = data[(y * W + x) * 4 + 3];
        if (a >= 32) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    if (maxX < minX || maxY < minY) return 0;

    const subW = maxX - minX + 1;
    const subH = maxY - minY + 1;
    const grid = new Uint8Array(subW * subH);

    for (let sy = 0; sy < subH; sy++) {
      const py = minY + sy;
      for (let sx = 0; sx < subW; sx++) {
        const px = minX + sx;
        grid[sy * subW + sx] = data[(py * W + px) * 4 + 3] >= 32 ? 1 : 0;
      }
    }

    const visited = new Uint8Array(subW * subH);
    let componentCount = 0;
    const queueX = new Int32Array(subW * subH);
    const queueY = new Int32Array(subW * subH);

    for (let y = 0; y < subH; y++) {
      for (let x = 0; x < subW; x++) {
        const idx = y * subW + x;
        if (grid[idx] === 1 && visited[idx] === 0) {
          visited[idx] = 1;
          let head = 0, tail = 0;
          queueX[tail] = x;
          queueY[tail] = y;
          tail++;
          let pixelCount = 0;

          while (head < tail) {
            const cx = queueX[head];
            const cy = queueY[head];
            head++;
            pixelCount++;

            for (let dy = -1; dy <= 1; dy++) {
              const ny = cy + dy;
              if (ny < 0 || ny >= subH) continue;
              for (let dx = -1; dx <= 1; dx++) {
                if (dx === 0 && dy === 0) continue;
                const nx = cx + dx;
                if (nx < 0 || nx >= subW) continue;
                const nIdx = ny * subW + nx;
                if (grid[nIdx] === 1 && visited[nIdx] === 0) {
                  visited[nIdx] = 1;
                  queueX[tail] = nx;
                  queueY[tail] = ny;
                  tail++;
                }
              }
            }
          }

          if (pixelCount >= 6) {
            componentCount++;
          }
        }
      }
    }
    return componentCount;
  }

  // Master execution for each character
  for (const [char, strokes] of Object.entries(charStrokeMap)) {
    const totalStrokes = strokes.length;
    const strokeEvals = [];

    // Container for full character verification via setupCalligraphySumiCanvas
    const targetElement = document.createElement("div");
    document.body.appendChild(targetElement);
    const svgElem = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    targetElement.appendChild(svgElem);

    const strokeEntries = strokes.map((s, idx) => ({
      d: s.d,
      type: s.type || "",
      component: s.component || "",
      index: idx + 1,
      id: s.id || `s-${idx + 1}`
    }));

    // Test full character canvas setup
    let fullRenderSuccess = false;
    let fullInkPixels = 0;
    try {
      setupCalligraphySumiCanvas(targetElement, svgElem, strokeEntries);
      const fullCanvas = targetElement.querySelector("canvas.calligraphy-sumi-canvas");
      if (fullCanvas) {
        const fullCtx = fullCanvas.getContext("2d");
        const fullImg = fullCtx.getImageData(0, 0, 792, 792);
        for (let i = 3; i < fullImg.data.length; i += 4) {
          if (fullImg.data[i] >= 32) fullInkPixels++;
        }
        fullRenderSuccess = fullInkPixels > 0;
      }
    } catch (e) {
      fullRenderSuccess = false;
    }

    // Process each stroke in isolation
    for (let sIdx = 0; sIdx < totalStrokes; sIdx++) {
      const stroke = strokes[sIdx];
      const strokeObj = {
        d: stroke.d,
        type: stroke.type || "",
        component: stroke.component || "",
        index: sIdx + 1
      };

      const compiled = compileStrokePhysics(strokeObj, 0, 0, 792, totalStrokes);
      if (!compiled || !compiled.samples || compiled.samples.length < 2) {
        continue;
      }

      const pts = compiled.samples;
      const numPts = pts.length;
      const hf = compiled.hookFeature;
      // Lock evaluation heel index to genuine hook vertex - 4 so heelIdx inflation cannot truncate evaluation
      const heelIdx = hf ? Math.max(4, hf.index - 4) : -1;
      let stopIdx = numPts - 1;
      if (hf && numPts - 1 > heelIdx) {
        stopIdx = heelIdx;
      }

      // Filter out any synthetic/auxiliary corner features; only genuine corner peaks count
      const genuineCorners = (compiled.cornerFeatures || []).filter(cf => !cf.isAuxiliary && cf.angle > 0.35);

      // Render isolated stroke onto 792x792 canvas
      const strokeCanvas = document.createElement("canvas");
      strokeCanvas.width = 792;
      strokeCanvas.height = 792;
      const strokeCtx = strokeCanvas.getContext("2d");

      renderFullCompiledStroke(strokeCtx, compiled, { toneMode: "sumi", opacity: 1.0 });
      const imgData = strokeCtx.getImageData(0, 0, 792, 792);
      const imgRaw = imgData.data;

      // -----------------------------------------------------------------------
      // Metric 1: Retrograde Boundary Folds
      // -----------------------------------------------------------------------
      let retrogradeSteps = 0;
      let minEdgeDotTangent = Infinity;
      let minEdgeUnitDotTangent = Infinity;

      for (let i = 0; i < stopIdx; i++) {
        const p = pts[i];
        const pNext = pts[i+1];
        let nearSharpCorner = false;
        for (const cf of genuineCorners) {
          if (cf.angle > 0.45 && (Math.abs(p.s - cf.s) <= 4.5 || Math.abs(pNext.s - cf.s) <= 4.5)) {
            nearSharpCorner = true;
            break;
          }
        }
        const dLx = pNext.lx - p.lx;
        const dLy = pNext.ly - p.ly;
        const dRx = pNext.rx - p.rx;
        const dRy = pNext.ry - p.ry;
        const dotL = dLx * p.tx + dLy * p.ty;
        const dotR = dRx * p.tx + dRy * p.ty;
        const lenL = Math.hypot(dLx, dLy) || 1e-6;
        const lenR = Math.hypot(dRx, dRy) || 1e-6;
        const uDotL = dotL / lenL;
        const uDotR = dotR / lenR;

        if (!nearSharpCorner && (dotL < -0.10 || dotR < -0.10)) {
          retrogradeSteps++;
        }
        if (!nearSharpCorner) {
          minEdgeDotTangent = Math.min(minEdgeDotTangent, dotL, dotR);
          minEdgeUnitDotTangent = Math.min(minEdgeUnitDotTangent, uDotL, uDotR);
        }
      }

      const leftChain = [];
      const rightChain = [];
      for (let i = 0; i < numPts; i++) {
        leftChain.push({ x: pts[i].lx, y: pts[i].ly });
        rightChain.push({ x: pts[i].rx, y: pts[i].ry });
      }
      const smoothL = chaikinSmoothOpenChain(leftChain, 2);
      const smoothR = chaikinSmoothOpenChain(rightChain, 2);
      const selfIntersections = countSelfIntersections(smoothL) + countSelfIntersections(smoothR);

      // -----------------------------------------------------------------------
      // Metric 2: High-Frequency Boundary Sawtooth / Jitter
      // Measures normal-offset second difference (in px) and sign-flip rate
      // across both left and right edges, independent of centerline straightness.
      // -----------------------------------------------------------------------
      const features = compiled.features || [];
      const eligibleIndices = [];

      for (let i = 1; i < stopIdx; i++) {
        const p = pts[i];
        if (p.u < 0.15 || p.u > 0.75) continue;
        let nearFeature = false;
        for (const f of features) {
          if (Math.abs(p.s - f.s) <= 6.0) {
            nearFeature = true;
            break;
          }
        }
        if (!nearFeature) {
          eligibleIndices.push(i);
        }
      }

      const offL = new Float32Array(numPts);
      const offR = new Float32Array(numPts);
      for (let i = 0; i < numPts; i++) {
        const p = pts[i];
        offL[i] = (p.lx - p.x) * p.nx + (p.ly - p.y) * p.ny;
        offR[i] = -((p.rx - p.x) * p.nx + (p.ry - p.y) * p.ny);
      }

      let sumD2Offset = 0;
      let countD2 = 0;
      let flips = 0;
      let flipOpportunities = 0;
      let prevSignL = null;
      let prevSignR = null;

      for (let idx = 0; idx < eligibleIndices.length; idx++) {
        const i = eligibleIndices[idx];
        if (idx > 0 && i !== eligibleIndices[idx - 1] + 1) {
          prevSignL = null;
          prevSignR = null;
        }
        const d2L = Math.abs(offL[i+1] - 2 * offL[i] + offL[i-1]);
        const d2R = Math.abs(offR[i+1] - 2 * offR[i] + offR[i-1]);
        sumD2Offset += (d2L + d2R) * 0.5;
        countD2++;

        const diffL = offL[i] - offL[i-1];
        if (Math.abs(diffL) > 1e-4) {
          const sL = diffL > 0 ? 1 : -1;
          if (prevSignL !== null) {
            flipOpportunities++;
            if (sL !== prevSignL) flips++;
          }
          prevSignL = sL;
        }

        const diffR = offR[i] - offR[i-1];
        if (Math.abs(diffR) > 1e-4) {
          const sR = diffR > 0 ? 1 : -1;
          if (prevSignR !== null) {
            flipOpportunities++;
            if (sR !== prevSignR) flips++;
          }
          prevSignR = sR;
        }
      }

      const edgeD2Px = countD2 > 0 ? (sumD2Offset / countD2) : 0.0;
      const normalSignFlipRate = flipOpportunities > 0 ? (flips / flipOpportunities) : 0;

      // -----------------------------------------------------------------------
      // Metric 4: Raster Medial-Axis / Cross-Section Width Profile
      // Measures single-arm outer cross-sectional span along local normal from
      // centerline s=0 (bridging interior kasure slits <= 3.5px without jumping
      // across exterior air gaps into a folded arm).
      // -----------------------------------------------------------------------
      const rasterW = new Float32Array(numPts);
      const maxSearch = Math.max(24, Math.ceil(compiled.shaftRadius * 2.2));

      for (let i = 0; i < numPts; i++) {
        const p = pts[i];
        const cx = p.x;
        const cy = p.y;
        const nx = p.nx;
        const ny = p.ny;

        let lastPos = -Infinity;
        let gapPos = 0;
        for (let s = 0; s <= maxSearch; s += 0.5) {
          const qx = Math.round(cx + nx * s);
          const qy = Math.round(cy + ny * s);
          if (qx < 0 || qx >= 792 || qy < 0 || qy >= 792) break;
          const a = imgRaw[(qy * 792 + qx) * 4 + 3];
          if (a >= 32) {
            lastPos = s;
            gapPos = 0;
          } else {
            gapPos += 0.5;
            if (gapPos > 3.5) break;
          }
        }

        let lastNeg = Infinity;
        let gapNeg = 0;
        for (let s = 0; s >= -maxSearch; s -= 0.5) {
          const qx = Math.round(cx + nx * s);
          const qy = Math.round(cy + ny * s);
          if (qx < 0 || qx >= 792 || qy < 0 || qy >= 792) break;
          const a = imgRaw[(qy * 792 + qx) * 4 + 3];
          if (a >= 32) {
            lastNeg = s;
            gapNeg = 0;
          } else {
            gapNeg += 0.5;
            if (gapNeg > 3.5) break;
          }
        }

        if (lastPos >= 0 && lastNeg <= 0) {
          rasterW[i] = lastPos - lastNeg;
        } else if (lastPos >= 0) {
          rasterW[i] = lastPos;
        } else if (lastNeg <= 0) {
          rasterW[i] = -lastNeg;
        } else {
          rasterW[i] = 0;
        }
      }

      let maxWidthStepPx = 0;
      for (let i = 1; i < stopIdx; i++) {
        let nearCorner = false;
        for (const cf of genuineCorners) {
          if (Math.abs(pts[i].s - cf.s) <= 6.0 || Math.abs(pts[i+1].s - cf.s) <= 6.0) {
            nearCorner = true;
            break;
          }
        }
        if (hf && (Math.abs(pts[i].s - hf.s) <= 6.0 || Math.abs(pts[i+1].s - hf.s) <= 6.0)) {
          nearCorner = true;
        }
        if (nearCorner) continue;
        const stepDiff = Math.abs(rasterW[i+1] - rasterW[i]);
        if (stepDiff > maxWidthStepPx) maxWidthStepPx = stepDiff;
      }
      const tipWidthPx = rasterW[numPts - 1];

      // KVG Endpoint Unreached Distance
      const endPt = pts[numPts - 1];
      const epX = Math.round(endPt.x);
      const epY = Math.round(endPt.y);
      let kvgEndpointUnreachedPx = 0;

      const epInBounds = (epX >= 0 && epX < 792 && epY >= 0 && epY < 792);
      if (!epInBounds || imgRaw[(epY * 792 + epX) * 4 + 3] < 32) {
        let minD = Infinity;
        const win = 50;
        for (let dy = -win; dy <= win; dy++) {
          const qy = epY + dy;
          if (qy < 0 || qy >= 792) continue;
          for (let dx = -win; dx <= win; dx++) {
            const qx = epX + dx;
            if (qx < 0 || qx >= 792) continue;
            if (imgRaw[(qy * 792 + qx) * 4 + 3] >= 32) {
              const d = Math.hypot(qx - endPt.x, qy - endPt.y);
              if (d < minD) minD = d;
            }
          }
        }
        kvgEndpointUnreachedPx = (minD === Infinity ? win : minD);
      }

      // -----------------------------------------------------------------------
      // Metric 3: Hook Trajectory & Splice Discontinuity (Measured from Canvas Pixels)
      // Finds the actual rendered distal hook tip pixel in imgRaw (alpha >= 32)
      // in the hook flick hemisphere from heel H, and compares its position and
      // angle against the actual KanjiVG terminal vector (endPt - H).
      // -----------------------------------------------------------------------
      let hookTipErrorPx = 0;
      let hookAngleErrorDeg = 0;
      let hookSpliceJumpPx = 0;

      if (hf) {
        const H = pts[heelIdx];
        const vKvgX = endPt.x - H.x;
        const vKvgY = endPt.y - H.y;
        const magKvg = Math.hypot(vKvgX, vKvgY) || 1e-6;
        const uKvgX = vKvgX / magKvg;
        const uKvgY = vKvgY / magKvg;

        // Pre-hook shaft incoming direction
        const preIdx = Math.max(0, heelIdx - 8);
        const shaftDx = H.x - pts[preIdx].x;
        const shaftDy = H.y - pts[preIdx].y;
        const shaftMag = Math.hypot(shaftDx, shaftDy) || 1e-6;
        const uShaftX = shaftDx / shaftMag;
        const uShaftY = shaftDy / shaftMag;
        // Lateral normal pointing toward the flick side
        const sideSign = (uShaftX * uKvgY - uShaftY * uKvgX) >= 0 ? 1 : -1;
        const latX = -uShaftY * sideSign;
        const latY = uShaftX * sideSign;

        let bestScore = -Infinity;
        let tipX = H.x;
        let tipY = H.y;
        const searchR = Math.ceil(Math.max(magKvg * 1.8, compiled.shaftRadius * 4.5, 65));
        const hx0 = Math.max(0, Math.floor(H.x - searchR));
        const hx1 = Math.min(791, Math.ceil(H.x + searchR));
        const hy0 = Math.max(0, Math.floor(H.y - searchR));
        const hy1 = Math.min(791, Math.ceil(H.y + searchR));

        for (let py = hy0; py <= hy1; py++) {
          for (let px = hx0; px <= hx1; px++) {
            if (imgRaw[(py * 792 + px) * 4 + 3] < 32) continue;
            // Exclude pixels belonging to the incoming shaft (up to hf.index - 8)
            let insideIncomingShaft = false;
            const shaftCheckLimit = Math.max(0, hf.index - 8);
            for (let m = 0; m <= shaftCheckLimit; m += 2) {
              const sm = pts[m];
              const radM = Math.max(compiled.shaftRadius * 1.15, (sm.radius || compiled.shaftRadius) + 2.5);
              if (Math.hypot(px - sm.x, py - sm.y) <= radM) {
                insideIncomingShaft = true;
                break;
              }
            }
            if (insideIncomingShaft) continue;

            const dx = px - H.x;
            const dy = py - H.y;
            const latProj = dx * latX + dy * latY;
            const kvgProj = dx * uKvgX + dy * uKvgY;
            if (latProj < 2.0 && kvgProj < 4.0) continue;
            const distH = Math.hypot(dx, dy);
            if (distH > searchR) continue;
            const score = kvgProj * 0.65 + latProj * 0.35 + distH * 0.25;
            if (score > bestScore) {
              bestScore = score;
              tipX = px;
              tipY = py;
            }
          }
        }

        hookTipErrorPx = Math.hypot(tipX - endPt.x, tipY - endPt.y);

        const vWedgeX = tipX - H.x;
        const vWedgeY = tipY - H.y;
        const magWedge = Math.hypot(vWedgeX, vWedgeY) || 1e-6;

        const cosTheta = Math.max(-1, Math.min(1, (vWedgeX * vKvgX + vWedgeY * vKvgY) / (magWedge * magKvg)));
        hookAngleErrorDeg = Math.acos(cosTheta) * (180 / Math.PI);

        for (let k = 1; k < stopIdx; k++) {
          const dS = Math.abs(pts[k].s - hf.s);
          const dSNext = Math.abs(pts[k + 1].s - hf.s);
          if (dS > 6.0 && dSNext > 6.0 && dS <= 12.0) {
            const jump = Math.abs(rasterW[k + 1] - rasterW[k]);
            if (jump > hookSpliceJumpPx) hookSpliceJumpPx = jump;
          }
        }
      }

      // -----------------------------------------------------------------------
      // Metric 5: Mechanical Barcode Kasure Detection
      // Restricted to non-hook shaft/tail (i <= stopIdx) within local stroke width.
      // -----------------------------------------------------------------------
      let maxCrossSectionGaps = 0;
      let kasureSlitSamples = 0;

      for (let i = 0; i <= stopIdx; i++) {
        const p = pts[i];
        if (p.u <= 0.65) continue;

        const localHalfW = Math.max(4.0, 0.65 * Math.hypot(p.rx - p.lx, p.ry - p.ly));
        let insideFirstInk = false;
        let inGap = false;
        let gapsInCrossSection = 0;

        for (let s = -localHalfW; s <= localHalfW; s += 0.5) {
          const qx = Math.round(p.x + p.nx * s);
          const qy = Math.round(p.y + p.ny * s);
          if (qx < 0 || qx >= 792 || qy < 0 || qy >= 792) continue;
          const a = imgRaw[(qy * 792 + qx) * 4 + 3];

          if (a >= 48) {
            if (inGap) {
              gapsInCrossSection++;
              inGap = false;
            }
            insideFirstInk = true;
          } else if (a <= 16 && insideFirstInk) {
            inGap = true;
          }
        }

        if (gapsInCrossSection > maxCrossSectionGaps) {
          maxCrossSectionGaps = gapsInCrossSection;
        }
        if (gapsInCrossSection >= 3) {
          kasureSlitSamples++;
        }
      }
      const regularKasureStripes = (maxCrossSectionGaps >= 3);

      // -----------------------------------------------------------------------
      // Metric 6: Longitudinal Spine Tone Oscillation / Polka-Dot Pooling
      // Uses a 5x5 local spatial average + 5-sample longitudinal box filter to
      // isolate macroscopic radial wash stamping (stepWash) from 1px paper grain.
      // -----------------------------------------------------------------------
      const rawDarkness = [];
      for (let i = 0; i <= stopIdx; i++) {
        const p = pts[i];
        if (p.u < 0.12 || p.u > 0.82) continue;
        const px = Math.round(p.x);
        const py = Math.round(p.y);
        let sumDark = 0;
        let countDark = 0;
        for (let dy = -2; dy <= 2; dy++) {
          const qy = py + dy;
          if (qy < 0 || qy >= 792) continue;
          for (let dx = -2; dx <= 2; dx++) {
            const qx = px + dx;
            if (qx < 0 || qx >= 792) continue;
            const idx = (qy * 792 + qx) * 4;
            const aVal = imgRaw[idx + 3];
            if (aVal < 64) continue;
            const lum = 0.299 * imgRaw[idx] + 0.587 * imgRaw[idx + 1] + 0.114 * imgRaw[idx + 2];
            sumDark += (aVal * (255 - lum)) / 255;
            countDark++;
          }
        }
        if (countDark >= 9) {
          rawDarkness.push(sumDark / countDark);
        }
      }

      const smoothDark = [];
      for (let k = 2; k < rawDarkness.length - 2; k++) {
        smoothDark.push(
          (rawDarkness[k - 2] + rawDarkness[k - 1] + rawDarkness[k] + rawDarkness[k + 1] + rawDarkness[k + 2]) / 5
        );
      }

      let prominentPeaks = 0;
      let maxProminence = 0;
      const winProm = 6;
      for (let k = winProm; k < smoothDark.length - winProm; k++) {
        const v = smoothDark[k];
        if (v >= smoothDark[k - 1] && v > smoothDark[k + 1]) {
          let minLeft = v, minRight = v;
          for (let j = Math.max(0, k - winProm * 2); j < k; j++) {
            if (smoothDark[j] < minLeft) minLeft = smoothDark[j];
          }
          for (let j = k + 1; j <= Math.min(smoothDark.length - 1, k + winProm * 2); j++) {
            if (smoothDark[j] < minRight) minRight = smoothDark[j];
          }
          const prom = v - Math.max(minLeft, minRight);
          if (prom >= 0.8) {
            prominentPeaks++;
          }
          if (prom > maxProminence) maxProminence = prom;
        }
      }
      const spineToneOscillation = prominentPeaks;
      const spineToneRipple = maxProminence;

      // -----------------------------------------------------------------------
      // Metric 7: Topological Integrity
      // -----------------------------------------------------------------------
      const disconnectedComponents = countConnectedComponents(imgData, 792, 792);

      // -----------------------------------------------------------------------
      // Metric 8: Pointed Calligraphic Taper Without Wispy Needle OR Blunt Club
      // (wispy_ends.png vs acceptable_taper.png)
      // - Must end in a true calligraphic point (m8_tip_ratio <= 0.16 at u=1.0,
      //   except connecting isZiHengPie).
      // - Must not collapse early into a 0.3mm pencil needle (u=0.80 >= 0.35,
      //   u=0.90 >= 0.20 of shaftW on sweeps/ti).
      // - Must maintain a steady linear/gently-convex slope attack over the
      //   taper zone (|m8_slope_dev| <= 0.08, preventing both concave needle
      //   plunge and parabolic sausage bulge).
      // -----------------------------------------------------------------------
      const beh = compiled.behavior || {};
      const contourW = new Float32Array(numPts);
      for (let i = 0; i < numPts; i++) {
        contourW[i] = Math.hypot(pts[i].rx - pts[i].lx, pts[i].ry - pts[i].ly);
      }
      const shaftDiam = compiled.shaftRadius * 2.0;

      const isTapered = !!(
        (beh.isSweepEnd && !beh.isZiHengPie) || beh.isRightNa || beh.isRisingTi || beh.isVerticalTi || beh.isRoofHook || hf
      );
      let m8TipRatio = 0.0;
      let m8U80Ratio = 1.0;
      let m8U90Ratio = 1.0;
      let m8SlopeDev = 0.0;

      if (isTapered) {
        let sumShaft = 0, cntShaft = 0;
        for (let i = 0; i < numPts; i++) {
          if (pts[i].u >= 0.20 && pts[i].u <= 0.40) {
            sumShaft += contourW[i];
            cntShaft++;
          }
        }
        const shaftW = cntShaft > 0 ? (sumShaft / cntShaft) : shaftDiam;
        m8TipRatio = contourW[numPts - 1] / Math.max(1.0, shaftW);

        // Determine where the final taper begins
        let taperStartU = 0.40;
        const lastCf = genuineCorners.length > 0 ? genuineCorners[genuineCorners.length - 1] : null;
        if (hf) {
          taperStartU = hf.u;
        } else if (beh.isRightNa) {
          taperStartU = 0.72;
        } else if (beh.isRoofHook || beh.isVerticalTi || (lastCf && lastCf.u > 0.42)) {
          taperStartU = Math.min(0.90, (lastCf ? lastCf.u : 0.72) + 0.03);
        } else if (beh.isRisingTi) {
          taperStartU = Math.min(0.32, 4.5 / Math.max(10.0, compiled.origLen || 25.0));
        } else {
          taperStartU = (pts[0].tx < -0.42) ? 0.30 : 0.34;
        }

        const startIdx = Math.min(numPts - 3, Math.max(1, Math.floor((numPts - 1) * taperStartU)));
        const startW = Math.max(1.0, contourW[startIdx]);
        const endIdx = numPts - 1;
        const midIdx = Math.floor((startIdx + endIdx) * 0.5);
        if (endIdx - startIdx >= 4) {
          const chordMidW = 0.5 * (contourW[startIdx] + contourW[endIdx]);
          m8SlopeDev = (contourW[midIdx] - chordMidW) / startW;
        }

        // For long/free-air sweeps & rising ti (where taper starts before u=0.50), check u=0.80 and u=0.90 ratios
        if (taperStartU <= 0.48) {
          const idx80 = Math.min(numPts - 1, Math.floor((numPts - 1) * 0.80));
          const idx90 = Math.min(numPts - 1, Math.floor((numPts - 1) * 0.90));
          m8U80Ratio = contourW[idx80] / Math.max(1.0, shaftW);
          m8U90Ratio = contourW[idx90] / Math.max(1.0, shaftW);
        } else {
          // For post-corner / post-foot / hook tapers, check at 55% and 78% of the taper zone
          const idx55 = Math.min(numPts - 1, Math.floor(startIdx + (endIdx - startIdx) * 0.55));
          const idx78 = Math.min(numPts - 1, Math.floor(startIdx + (endIdx - startIdx) * 0.78));
          m8U80Ratio = contourW[idx55] / startW;
          m8U90Ratio = contourW[idx78] / startW;
        }
      }

      // -----------------------------------------------------------------------
      // Metric 9: Anti-Bulbous Middle Control (bulbous_middle.png on 涙)
      // - Ensures non-dot strokes do not balloon in the middle (u in [0.28, 0.65]
      //   away from corners must have contourW / shaftDiam <= 1.05).
      // - Ensures post-entry body (u in [0.22, 0.85] away from corners/hooks)
      //   does not balloon past 1.14 * shaftDiam (catching pregnant 1.28x Na).
      // - Ensures mid-stroke width profile [u=0.18 .. u=0.68] does not arch
      //   outward convexly (m9_mid_arch_excess_px <= 1.0px).
      // -----------------------------------------------------------------------
      let m9MidBulgeRatio = 0.0;
      let m9MaxBodyRatio = 0.0;
      let m9MidArchExcessPx = 0.0;

      if (!beh.isDot) {
        let maxMidW = 0.0;
        let maxBodyW = 0.0;
        for (let i = 0; i < numPts; i++) {
          const p = pts[i];
          if (p.u < 0.22 || p.u > 0.85) continue;
          let nearFeature = false;
          for (const cf of genuineCorners) {
            if (Math.abs(p.s - cf.s) <= 5.5) {
              nearFeature = true;
              break;
            }
          }
          if (hf && Math.abs(p.s - hf.s) <= 7.5) {
            nearFeature = true;
          }
          if (nearFeature) continue;

          if (contourW[i] > maxBodyW) maxBodyW = contourW[i];
          if (p.u >= 0.28 && p.u <= 0.65 && contourW[i] > maxMidW) {
            maxMidW = contourW[i];
          }
        }
        m9MidBulgeRatio = maxMidW / Math.max(1.0, shaftDiam);
        m9MaxBodyRatio = maxBodyW / Math.max(1.0, shaftDiam);

        // Check mid-stroke outward convexity when no corner lies in [0.15, 0.72]
        const hasMidCorner = genuineCorners.some(cf => cf.u >= 0.15 && cf.u <= 0.72) || (hf && hf.u <= 0.72);
        if (!hasMidCorner) {
          const idx18 = Math.floor((numPts - 1) * 0.18);
          const idx43 = Math.floor((numPts - 1) * 0.43);
          const idx68 = Math.floor((numPts - 1) * 0.68);
          if (contourW[idx43] > contourW[idx18]) {
            const chordMid = 0.5 * (contourW[idx18] + contourW[idx68]);
            m9MidArchExcessPx = Math.max(0.0, contourW[idx43] - chordMid);
          }
        }
      }

      // Package stroke evaluation
      strokeEvals.push({
        strokeIndex: sIdx + 1,
        id: stroke.id || `s-${sIdx + 1}`,
        type: stroke.type || "",
        component: stroke.component || "",
        numSamples: numPts,
        hasHook: !!hf,
        isTapered,
        isDot: !!beh.isDot,
        m1_retrograde_steps: retrogradeSteps,
        m1_min_edge_dot_tangent: Number(minEdgeDotTangent.toFixed(3)),
        m1_min_edge_unit_dot_tangent: Number(minEdgeUnitDotTangent.toFixed(3)),
        m1_self_intersections: selfIntersections,
        m2_edge_d2_px: Number(edgeD2Px.toFixed(3)),
        m2_normal_sign_flip_rate: Number(normalSignFlipRate.toFixed(3)),
        m3_hook_tip_error_px: Number(hookTipErrorPx.toFixed(2)),
        m3_hook_angle_error_deg: Number(hookAngleErrorDeg.toFixed(2)),
        m3_hook_splice_jump_px: Number(hookSpliceJumpPx.toFixed(2)),
        m4_max_width_step_px: Number(maxWidthStepPx.toFixed(2)),
        m4_tip_width_px: Number(tipWidthPx.toFixed(2)),
        m4_kvg_endpoint_unreached_px: Number(kvgEndpointUnreachedPx.toFixed(2)),
        m5_max_cross_section_gaps: maxCrossSectionGaps,
        m5_regular_kasure_stripes: regularKasureStripes,
        m6_spine_tone_oscillation: spineToneOscillation,
        m6_spine_tone_ripple: Number(spineToneRipple.toFixed(2)),
        m7_disconnected_components: disconnectedComponents,
        m8_tip_ratio: Number(m8TipRatio.toFixed(2)),
        m8_u80_ratio: Number(m8U80Ratio.toFixed(2)),
        m8_u90_ratio: Number(m8U90Ratio.toFixed(2)),
        m8_slope_dev: Number(m8SlopeDev.toFixed(2)),
        m9_mid_bulge_ratio: Number(m9MidBulgeRatio.toFixed(2)),
        m9_max_body_ratio: Number(m9MaxBodyRatio.toFixed(2)),
        m9_mid_arch_excess_px: Number(m9MidArchExcessPx.toFixed(2))
      });
    }

    results[char] = {
      char,
      strokeCount: totalStrokes,
      fullRenderSuccess,
      fullInkPixels,
      strokes: strokeEvals
    };
  }

  const outEl = document.createElement("script");
  outEl.id = "eval-output";
  outEl.type = "application/json";
  outEl.textContent = JSON.stringify(results);
  document.body.appendChild(outEl);
})();
"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Brushwork Canvas Evaluator</title>
</head>
<body>
<div id="canvas-container"></div>
<script>
{app_js_content}
</script>
<script>
{eval_script}
</script>
</body>
</html>"""


def extract_strokes_for_characters(chars: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Decomposes and extracts KanjiVG strokes for benchmark characters."""
    char_map: dict[str, list[dict[str, Any]]] = {}
    for ch in chars:
        try:
            tree = ids_parser.decompose_character(ch, max_depth=6, compute_bbox=True)
            layer_info = glyph_service.extract_kanjivg_stroke_layers(ch, tree)
            all_strokes = layer_info.get("all_strokes", [])
            char_map[ch] = all_strokes
        except Exception as e:
            print(f"[WARN] Failed to extract strokes for '{ch}': {e}", file=sys.stderr)
            char_map[ch] = []
    return char_map


def run_headless_evaluator(html_content: str) -> dict[str, Any]:
    """Executes evaluation HTML in headless Chrome and parses the eval-output JSON payload."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        tmp_path = f.name

    try:
        cmd = [
            "google-chrome",
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--dump-dom",
            f"file://{tmp_path}",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        stdout = proc.stdout

        match = re.search(r'<script id="eval-output" type="application/json">(.*?)</script>', stdout, re.DOTALL)
        if not match:
            err_msg = f"Failed to extract eval-output from Chrome dump-dom.\nSTDERR: {proc.stderr[:1000]}"
            raise RuntimeError(err_msg)

        json_data = json.loads(match.group(1))
        return json_data
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def evaluate_defects(stroke: dict[str, Any]) -> dict[str, bool]:
    """Checks whether a stroke violates thresholds across metrics M1-M9."""
    defects = {
        "M1_folds": (
            stroke["m1_retrograde_steps"] >= THRESHOLDS["m1_retrograde_steps"]
            or stroke["m1_self_intersections"] >= THRESHOLDS["m1_self_intersections"]
        ),
        "M2_jitter": (
            stroke["m2_edge_d2_px"] >= THRESHOLDS["m2_edge_d2_px"]
            or stroke["m2_normal_sign_flip_rate"] >= THRESHOLDS["m2_normal_sign_flip_rate"]
        ),
        "M3_hook": (
            stroke["hasHook"]
            and (
                stroke["m3_hook_tip_error_px"] >= THRESHOLDS["m3_hook_tip_error_px"]
                or stroke["m3_hook_angle_error_deg"] >= THRESHOLDS["m3_hook_angle_error_deg"]
                or stroke["m3_hook_splice_jump_px"] >= THRESHOLDS["m3_hook_splice_jump_px"]
            )
        ),
        "M4_raster_step": (
            stroke["m4_max_width_step_px"] >= THRESHOLDS["m4_max_width_step_px"]
            or stroke["m4_kvg_endpoint_unreached_px"] >= THRESHOLDS["m4_kvg_endpoint_unreached_px"]
        ),
        "M5_kasure_barcode": stroke["m5_regular_kasure_stripes"],
        "M6_spine_oscillation": (
            stroke["m6_spine_tone_oscillation"] >= THRESHOLDS["m6_spine_tone_oscillation"]
            or stroke["m6_spine_tone_ripple"] >= THRESHOLDS["m6_spine_tone_ripple"]
        ),
        "M7_topology": (stroke["m7_disconnected_components"] >= THRESHOLDS["m7_disconnected_components"]),
        "M8_taper": (
            stroke.get("isTapered", False)
            and (
                stroke["m8_tip_ratio"] > THRESHOLDS["m8_max_tip_ratio"]
                or stroke["m8_u80_ratio"] < THRESHOLDS["m8_min_u80_ratio"]
                or stroke["m8_u90_ratio"] < THRESHOLDS["m8_min_u90_ratio"]
                or abs(stroke["m8_slope_dev"]) > THRESHOLDS["m8_max_slope_dev"]
            )
        ),
        "M9_bulbous": (
            not stroke.get("isDot", False)
            and (
                stroke["m9_mid_bulge_ratio"] > THRESHOLDS["m9_max_mid_bulge_ratio"]
                or stroke["m9_max_body_ratio"] > THRESHOLDS["m9_max_body_ratio"]
                or stroke["m9_mid_arch_excess_px"] > THRESHOLDS["m9_max_mid_arch_excess_px"]
            )
        ),
    }
    return defects


def print_evaluation_summary(results: dict[str, Any]) -> None:
    """Formats and prints clean human-readable tables per character and aggregate summaries."""
    print("=" * 130)
    print(" PROGRAMMATIC CANVAS BRUSHWORK EVALUATOR — SLENDER GOLD ENGINE AUDIT (HEADLESS CHROME)")
    print("=" * 130)

    total_strokes_all = 0
    defect_counts = {
        "M1_folds": 0,
        "M2_jitter": 0,
        "M3_hook": 0,
        "M4_raster_step": 0,
        "M5_kasure_barcode": 0,
        "M6_spine_oscillation": 0,
        "M7_topology": 0,
        "M8_taper": 0,
        "M9_bulbous": 0,
    }
    hook_strokes_total = 0
    tapered_strokes_total = 0
    non_dot_strokes_total = 0

    for char, cdata in results.items():
        strokes = cdata.get("strokes", [])
        total_strokes_all += len(strokes)
        print(f"\nKanji: 【{char}】 ({len(strokes)} strokes) | Full Canvas Render: {'PASS' if cdata.get('fullRenderSuccess') else 'FAIL'} ({cdata.get('fullInkPixels', 0):,} ink px)")
        print("-" * 130)
        headers = [
            "#", "Type", "M1 Folds", "M2 d2/Flip", "M3 Hook Err",
            "M4 Step/End", "M5 Kasure", "M6 Spine", "M7 Isl", "M8 Tip/u90/Slp", "M9 Mid/Body/Arch", "Defects"
        ]
        row_fmt = "{:<3} {:<5} {:<11} {:<12} {:<12} {:<14} {:<9} {:<11} {:<7} {:<16} {:<16} {:<8}"
        print(row_fmt.format(*headers))
        print("-" * 130)

        for s in strokes:
            defects = evaluate_defects(s)
            for k, is_defect in defects.items():
                if is_defect:
                    defect_counts[k] += 1
            if s["hasHook"]:
                hook_strokes_total += 1
            if s.get("isTapered"):
                tapered_strokes_total += 1
            if not s.get("isDot"):
                non_dot_strokes_total += 1

            active_defects = [k.split("_")[0] for k, v in defects.items() if v]
            defect_str = ",".join(active_defects) if active_defects else "NONE"

            m1_val = f"f:{s['m1_retrograde_steps']}/{s['m1_min_edge_dot_tangent']:.1f}"
            m2_val = f"{s['m2_edge_d2_px']:.2f}/{s['m2_normal_sign_flip_rate']:.2f}"
            m3_val = f"{s['m3_hook_tip_error_px']:.1f}p {s['m3_hook_angle_error_deg']:.0f}°" if s["hasHook"] else "N/A"
            m4_val = f"dw:{s['m4_max_width_step_px']:.1f} e:{s['m4_kvg_endpoint_unreached_px']:.1f}"
            m5_val = f"gaps:{s['m5_max_cross_section_gaps']}"
            m6_val = f"p:{s['m6_spine_tone_oscillation']} r:{s['m6_spine_tone_ripple']:.1f}"
            m7_val = f"c:{s['m7_disconnected_components']}"
            m8_val = f"{s['m8_tip_ratio']:.2f}/{s['m8_u90_ratio']:.2f}/{s['m8_slope_dev']:+.2f}" if s.get("isTapered") else "N/A"
            m9_val = f"{s['m9_mid_bulge_ratio']:.2f}/{s['m9_max_body_ratio']:.2f}/{s['m9_mid_arch_excess_px']:.1f}" if not s.get("isDot") else "N/A"

            print(row_fmt.format(
                s["strokeIndex"],
                s["type"][:5],
                m1_val,
                m2_val,
                m3_val,
                m4_val,
                m5_val,
                m6_val,
                m7_val,
                m8_val,
                m9_val,
                defect_str
            ))

    print("\n" + "=" * 130)
    print(" AGGREGATE BRUSHWORK DEFECT AUDIT REPORT")
    print("=" * 130)
    print(f"Total Evaluated Characters : {len(results)}")
    print(f"Total Evaluated Strokes    : {total_strokes_all}")
    print(f"Total Strokes with Hooks   : {hook_strokes_total}")
    print(f"Total Tapered Strokes      : {tapered_strokes_total}")
    print(f"Total Non-Dot Strokes      : {non_dot_strokes_total}")
    print("-" * 130)
    print("Defect Breakdown by Metric:")
    metric_names = [
        ("M1: Retrograde Boundary Folds & Self-Intersections", defect_counts["M1_folds"], total_strokes_all),
        ("M2: High-Frequency Boundary Sawtooth / Jitter", defect_counts["M2_jitter"], total_strokes_all),
        ("M3: Hook Trajectory & Splice Discontinuity", defect_counts["M3_hook"], hook_strokes_total if hook_strokes_total else 1),
        ("M4: Raster Cross-Section Width Jumps & Unreached Endpoints", defect_counts["M4_raster_step"], total_strokes_all),
        ("M5: Mechanical Barcode Kasure (>= 3 parallel slits)", defect_counts["M5_kasure_barcode"], total_strokes_all),
        ("M6: Longitudinal Spine Tone Oscillation / Polka-Dot", defect_counts["M6_spine_oscillation"], total_strokes_all),
        ("M7: Topological Severance (Disconnected Islands)", defect_counts["M7_topology"], total_strokes_all),
        ("M8: Taper Quality (Pointed Tip, Anti-Wispy, Linear Slope)", defect_counts["M8_taper"], tapered_strokes_total if tapered_strokes_total else 1),
        ("M9: Bulbous Middle / Belly Bloating (e.g. 涙 ㇏)", defect_counts["M9_bulbous"], non_dot_strokes_total if non_dot_strokes_total else 1),
    ]

    for label, count, denom in metric_names:
        pct = (count / denom * 100) if denom > 0 else 0.0
        bar = "█" * int(round(pct / 5)) + "░" * (20 - int(round(pct / 5)))
        print(f"  {label:<60} : {count:>3} / {denom:>3} ({pct:>5.1f}%) [{bar}]")

    print("=" * 130)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Programmatic HTML Canvas Brushwork Evaluator for Slender Gold Calligraphy"
    )
    parser.add_argument(
        "--chars",
        type=str,
        default="",
        help="Comma or space-separated list of characters to evaluate (default: 永,水,嵐,成,九,子,心,道)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Optional path to export raw evaluation JSON",
    )
    args = parser.parse_args()

    if args.chars.strip():
        # Handle comma or space separation
        chars = [c.strip() for c in re.split(r"[\s,]+", args.chars.strip()) if c.strip()]
    else:
        chars = DEFAULT_BENCHMARK_CHARS

    if not APP_JS_PATH.exists():
        print(f"Error: {APP_JS_PATH} does not exist.", file=sys.stderr)
        sys.exit(1)

    app_js_content = APP_JS_PATH.read_text(encoding="utf-8")

    char_strokes = extract_strokes_for_characters(chars)
    html_content = build_evaluation_html(char_strokes, app_js_content)

    results = run_headless_evaluator(html_content)
    print_evaluation_summary(results)

    if args.json_out:
        out_path = Path(args.json_out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[INFO] Raw JSON evaluation data saved to: {out_path}")


if __name__ == "__main__":
    main()
