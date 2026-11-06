#!/usr/bin/env python3
"""
scripts/audit/evaluate_brushwork_canvas.py

Programmatic HTML Canvas Brushwork Evaluator for Slender Gold Calligraphy.
Executes rendering in headless Chrome (google-chrome --headless --no-sandbox --disable-gpu --dump-dom)
and inspects both compileStrokePhysics vector state and ctx.getImageData(0, 0, 792, 792)
pixel arrays without saving or reading PNG files.

Metrics:
  M1:  Retrograde Boundary Folds (retrograde_steps, min_edge_dot_tangent, self_intersections)
  M2:  High-Frequency Boundary Sawtooth / Jitter (edge_jitter_ratio, normal_sign_flip_rate)
  M3:  Hook Trajectory & Splice Discontinuity (hook_tip_error_px, hook_angle_error_deg, hook_splice_jump_px)
  M4:  Raster Medial-Axis / Cross-Section Width Profile (max_width_step_px, tip_width_px, kvg_endpoint_unreached_px)
  M5:  Mechanical Barcode Kasure Detection (max_cross_section_gaps, regular_kasure_stripes)
  M6:  Longitudinal Spine Tone Oscillation / Polka-Dot Pooling (spine_tone_oscillation, spine_tone_std_diff)
  M7:  Topological Integrity (disconnected_components)
  M8:  Pointed Calligraphic Taper (tip_ratio, u80_ratio, u90_ratio, slope_dev)
  M9:  Anti-Bulbous Middle Control (mid_bulge_ratio, max_body_ratio, mid_arch_excess_px)
  M10: Short-Stroke & Dot Elongation / Anti-Roundness (length_to_width_ratio, raster_aspect_ratio, dot_end_bloat_ratio)
  M11: Width Consistency Across Crossing & Character Strokes (crossing_width_ratio, crossing_mean_ratio, char_width_ratio)
  M12: Terminal Tome Clubbing & Acute Corner Webbing (tome_ratio, corner_bloat_ratio)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import ids_parser
import glyph_service

DEFAULT_BENCHMARK_CHARS = [
    "永", "水", "嵐", "成", "九", "子", "心", "道", "鬱", "涙",
    "京", "高", "葱", "匆", "交", "父", "文", "立", "家", "守",
    "広", "殺", "凶", "気", "井", "開", "月", "用", "周", "糸",
    "弱", "幾", "鳥", "米", "門", "同",
]
APP_JS_PATH = BASE_DIR / "static" / "app.js"
DB_PATH = BASE_DIR / "data" / "kanji_explorer.db"

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
    "m10_min_length_to_width_ratio": 2.35,
    "m10_min_raster_aspect_ratio": 1.95,
    "m10_max_dot_end_bloat_ratio": 0.68,
    "m11_max_crossing_width_ratio": 1.32,
    "m11_max_crossing_mean_ratio": 1.30,
    "m11_max_char_width_ratio": 1.30,
    "m11_min_char_width_ratio": 0.72,
    "m12_max_tome_ratio": 1.30,
    "m12_max_corner_bloat_ratio": 1.28,
    "i1_min_interior_darkness_std": 5.5,
    "i1_min_interior_alpha_std": 4.5,
    "i2_min_valley_ridge_contrast": 7.0,
    "i3_min_coffee_ring_rim_delta": 4.5,
    "i4_min_nijimi_fringe_ratio": 0.25,
    "i4_min_nijimi_valley_anisotropy": 0.35,
    "i5_min_glue_warmth_shift": 1.8,
    "i6_min_bristle_striation_rms": 1.1,
    "i7_min_dwell_pool_enrichment": 3.5,
    "i8_min_crossing_layer_darkening": 10.0,
}


def _collect_path_components(xml_input: ET.Element | str) -> list[dict[str, Any]]:
    """Fast extraction of stroke dictionaries from KanjiVG XML."""
    if isinstance(xml_input, str):
        if "xmlns:kvg=" not in xml_input:
            if "<kanji " in xml_input:
                xml_text = xml_input.replace("<kanji ", f'<kanji xmlns:kvg="{glyph_service.KVG_NS}" ', 1)
            else:
                xml_text = f'<kanjivg xmlns:kvg="{glyph_service.KVG_NS}">{xml_input}</kanjivg>'
        else:
            xml_text = xml_input
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
    else:
        root = xml_input

    path_comp_map: dict[int, str] = {}

    def _traverse(el: ET.Element, ancestor_elems: tuple[str, ...] = ()) -> None:
        cur_elems = ancestor_elems
        if el.tag.endswith("g"):
            raw_elem = (
                el.attrib.get(f"{{{glyph_service.KVG_NS}}}element")
                or el.attrib.get("kvg:element")
                or ""
            )
            norm_elem, _ = glyph_service.normalize_element_symbol(raw_elem)
            elem_val = norm_elem or raw_elem
            if elem_val:
                cur_elems = (*ancestor_elems, elem_val)
        elif el.tag.endswith("path"):
            comp_val = ""
            for anc in reversed(cur_elems):
                if anc in ("子", "了", "孑"):
                    comp_val = anc
                    break
            if not comp_val and cur_elems:
                comp_val = cur_elems[-1]
            path_comp_map[id(el)] = comp_val
        for ch_el in el:
            _traverse(ch_el, cur_elems)

    _traverse(root)

    raw_paths = [
        p for p in root.iter()
        if p.tag.endswith("path") and p.attrib.get("d")
    ]
    strokes = []
    for i, p in enumerate(raw_paths, 1):
        sid = p.attrib.get("id", f"s-{i}")
        sd = p.attrib.get("d", "")
        ptype = (
            p.attrib.get(f"{{{glyph_service.KVG_NS}}}type")
            or p.attrib.get("kvg:type")
            or ""
        )
        comp = path_comp_map.get(id(p), "")
        strokes.append({
            "id": sid,
            "d": sd,
            "type": ptype,
            "element": comp,
            "component": comp,
        })
    return strokes


if not hasattr(glyph_service, "_collect_path_components"):
    glyph_service._collect_path_components = _collect_path_components


def load_characters_from_db(
    joyo: bool = False,
    grades_str: str = "",
    db_path: Path = DB_PATH,
) -> list[str]:
    """Loads characters from SQLite database based on joyo or grade criteria."""
    if not db_path.exists():
        print(f"[WARN] Database not found at {db_path}. Falling back to default benchmark.", file=sys.stderr)
        return list(DEFAULT_BENCHMARK_CHARS)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        if joyo:
            cur.execute(
                "SELECT char FROM characters WHERE grade IN (1, 2, 3, 4, 5, 6, 8) "
                "ORDER BY grade, stroke_count, char"
            )
        elif grades_str:
            grades = [int(g.strip()) for g in grades_str.split(",") if g.strip().isdigit()]
            if not grades:
                return []
            placeholders = ",".join("?" for _ in grades)
            cur.execute(
                f"SELECT char FROM characters WHERE grade IN ({placeholders}) "
                f"ORDER BY grade, stroke_count, char",
                grades,
            )
        else:
            return []
        rows = cur.fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def extract_strokes_for_characters(chars: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Fast extraction of KanjiVG strokes for benchmark characters."""
    kvg_service = glyph_service._get_default_kanjivg_service()
    char_map: dict[str, list[dict[str, Any]]] = {}

    for ch in chars:
        try:
            xml_root = kvg_service.get_kanji_xml(ch) if kvg_service else None
            if xml_root is not None:
                raw_strokes = glyph_service._collect_path_components(xml_root)
                if raw_strokes:
                    char_map[ch] = [
                        {
                            "id": s.get("id", f"s-{idx+1}"),
                            "d": s.get("d", ""),
                            "type": s.get("type", ""),
                            "component": s.get("element", s.get("component", "")),
                        }
                        for idx, s in enumerate(raw_strokes)
                    ]
                else:
                    tree = ids_parser.decompose_character(ch, max_depth=6, compute_bbox=True)
                    layer_info = glyph_service.extract_kanjivg_stroke_layers(ch, tree)
                    char_map[ch] = layer_info.get("all_strokes", [])
            else:
                tree = ids_parser.decompose_character(ch, max_depth=6, compute_bbox=True)
                layer_info = glyph_service.extract_kanjivg_stroke_layers(ch, tree)
                char_map[ch] = layer_info.get("all_strokes", [])
        except Exception as e:
            print(f"[WARN] Failed to extract strokes for '{ch}': {e}", file=sys.stderr)
            char_map[ch] = []
    return char_map


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
  function countConnectedComponents(imgData, W, H, bbox) {
    const data = imgData.data;
    const bMinX = bbox ? Math.max(0, Math.floor(bbox.minX)) : 0;
    const bMaxX = bbox ? Math.min(W - 1, Math.ceil(bbox.maxX)) : W - 1;
    const bMinY = bbox ? Math.max(0, Math.floor(bbox.minY)) : 0;
    const bMaxY = bbox ? Math.min(H - 1, Math.ceil(bbox.maxY)) : H - 1;

    let minX = W, maxX = -1, minY = H, maxY = -1;
    for (let y = bMinY; y <= bMaxY; y++) {
      for (let x = bMinX; x <= bMaxX; x++) {
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

  // Pre-allocate one reusable 792x792 canvas for isolated stroke rendering
  const strokeCanvas = document.createElement("canvas");
  strokeCanvas.width = 792;
  strokeCanvas.height = 792;
  const strokeCtx = strokeCanvas.getContext("2d");
  const paperSub = getXuanPaperSubstrate(792, 792);

  try {
    // Master execution for each character
    for (const [char, strokes] of Object.entries(charStrokeMap)) {
    const totalStrokes = strokes.length;
    const strokeEvals = [];
    const compiledStrokesInfo = [];

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
    let fullImgDataArr = null;
    try {
      setupCalligraphySumiCanvas(targetElement, svgElem, strokeEntries);
      const fullCanvas = targetElement.querySelector("canvas.calligraphy-sumi-canvas");
      if (fullCanvas) {
        const fullCtx = fullCanvas.getContext("2d");
        const fullImg = fullCtx.getImageData(0, 0, 792, 792);
        fullImgDataArr = fullImg.data;
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
      const beh = compiled.behavior || {};

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

      // Render isolated stroke onto reusable 792x792 canvas
      strokeCtx.clearRect(0, 0, 792, 792);
      renderFullCompiledStroke(strokeCtx, compiled, { toneMode: "sumi", opacity: 1.0 });
      const imgData = strokeCtx.getImageData(0, 0, 792, 792);
      const imgRaw = imgData.data;

      // Compute bounding box around stroke sample points and outlines padded by 36px
      let bMinX = Infinity, bMaxX = -Infinity, bMinY = Infinity, bMaxY = -Infinity;
      for (let i = 0; i < numPts; i++) {
        const p = pts[i];
        if (p.x < bMinX) bMinX = p.x;
        if (p.x > bMaxX) bMaxX = p.x;
        if (p.y < bMinY) bMinY = p.y;
        if (p.y > bMaxY) bMaxY = p.y;
        if (p.lx < bMinX) bMinX = p.lx;
        if (p.lx > bMaxX) bMaxX = p.lx;
        if (p.ly < bMinY) bMinY = p.ly;
        if (p.ly > bMaxY) bMaxY = p.ly;
        if (p.rx < bMinX) bMinX = p.rx;
        if (p.rx > bMaxX) bMaxX = p.rx;
        if (p.ry < bMinY) bMinY = p.ry;
        if (p.ry > bMaxY) bMaxY = p.ry;
      }
      const strokeBbox = {
        minX: Math.max(0, Math.floor(bMinX - 36)),
        maxX: Math.min(791, Math.ceil(bMaxX + 36)),
        minY: Math.max(0, Math.floor(bMinY - 36)),
        maxY: Math.min(791, Math.ceil(bMaxY + 36))
      };

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
      // -----------------------------------------------------------------------
      const hasKasure = !!(beh.isSweepEnd && !beh.isZiHengPie && !beh.isRoofHook && !beh.isRisingTi && !beh.isVerticalTi && (compiled.origLen || 0) > 45 && !beh.isRightNa && !compiled.hookFeature && (compiled.cornerFeatures ? compiled.cornerFeatures.length : 0) <= 1);

      const rasterW = new Float32Array(numPts);
      const maxSearch = Math.max(24, Math.ceil(compiled.shaftRadius * 2.2));

      for (let i = 0; i < numPts; i++) {
        const p = pts[i];
        const cx = p.x;
        const cy = p.y;
        const nx = p.nx;
        const ny = p.ny;
        const maxGap = (hasKasure && p.u >= 0.74) ? 3.5 : 0.5;

        let lastPos = -Infinity;
        let gapPos = 0;
        for (let s = 0; s <= maxSearch; s += 0.5) {
          const qx = Math.round(cx + nx * s);
          const qy = Math.round(cy + ny * s);
          if (qx < 0 || qx >= 792 || qy < 0 || qy >= 792) break;

          if (Math.abs(s) > 4.0) {
            let inOtherLeg = false;
            const distSqI = s * s;
            for (let m = 0; m < numPts; m += 3) {
              if (Math.abs(m - i) <= 14) continue;
              const dmx = qx - pts[m].x;
              const dmy = qy - pts[m].y;
              if (dmx * dmx + dmy * dmy < distSqI * 0.72) {
                inOtherLeg = true;
                break;
              }
            }
            if (inOtherLeg) break;
          }

          const a = imgRaw[(qy * 792 + qx) * 4 + 3];
          if (a >= 32) {
            lastPos = s;
            gapPos = 0;
          } else {
            gapPos += 0.5;
            if (gapPos > maxGap) break;
          }
        }

        let lastNeg = Infinity;
        let gapNeg = 0;
        for (let s = 0; s >= -maxSearch; s -= 0.5) {
          const qx = Math.round(cx + nx * s);
          const qy = Math.round(cy + ny * s);
          if (qx < 0 || qx >= 792 || qy < 0 || qy >= 792) break;

          if (Math.abs(s) > 4.0) {
            let inOtherLeg = false;
            const distSqI = s * s;
            for (let m = 0; m < numPts; m += 3) {
              if (Math.abs(m - i) <= 14) continue;
              const dmx = qx - pts[m].x;
              const dmy = qy - pts[m].y;
              if (dmx * dmx + dmy * dmy < distSqI * 0.72) {
                inOtherLeg = true;
                break;
              }
            }
            if (inOtherLeg) break;
          }

          const a = imgRaw[(qy * 792 + qx) * 4 + 3];
          if (a >= 32) {
            lastNeg = s;
            gapNeg = 0;
          } else {
            gapNeg += 0.5;
            if (gapNeg > maxGap) break;
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
      for (let i = 3; i < stopIdx - 2; i++) {
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

        const preIdx = Math.max(0, heelIdx - 8);
        const shaftDx = H.x - pts[preIdx].x;
        const shaftDy = H.y - pts[preIdx].y;
        const shaftMag = Math.hypot(shaftDx, shaftDy) || 1e-6;
        const uShaftX = shaftDx / shaftMag;
        const uShaftY = shaftDy / shaftMag;
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
      // -----------------------------------------------------------------------
      let maxCrossSectionGaps = 0;
      let kasureSlitSamples = 0;

      if (!beh.isDot && !beh.isCrownDot) {
        for (let i = 0; i < stopIdx - 2; i++) {
          const p = pts[i];
          if (p.u <= 0.65) continue;

          let nearFeature = false;
          for (const cf of genuineCorners) {
            if (Math.abs(p.s - cf.s) <= 6.0) {
              nearFeature = true;
              break;
            }
          }
          if (hf && Math.abs(p.s - hf.s) <= 6.0) {
            nearFeature = true;
          }
          if (nearFeature) continue;

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
      }
      const regularKasureStripes = (maxCrossSectionGaps >= 3);

      // -----------------------------------------------------------------------
      // Metric 6: Longitudinal Spine Tone Oscillation / Polka-Dot Pooling
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
      const disconnectedComponents = countConnectedComponents(imgData, 792, 792, strokeBbox);

      // -----------------------------------------------------------------------
      // Metric 8: Pointed Calligraphic Taper Without Wispy Needle OR Blunt Club
      // -----------------------------------------------------------------------
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
        } else if (beh.isRoofHook || beh.isVerticalTi || (lastCf && lastCf.u > 0.44)) {
          taperStartU = lastCf ? lastCf.u : 0.75;
        } else if (beh.isRisingTi) {
          taperStartU = Math.min(0.30, 4.8 / Math.max(10.0, compiled.origLen || 25.0));
        } else {
          taperStartU = compiled.sweepStartU || 0.40;
        }

        const startIdx = Math.min(numPts - 3, Math.max(1, Math.floor((numPts - 1) * taperStartU)));
        const startW = Math.max(1.0, contourW[startIdx]);
        const endIdx = numPts - 1;
        const midIdx = Math.floor((startIdx + endIdx) * 0.5);
        if (endIdx - startIdx >= 8) {
          const chordMidW = 0.5 * (contourW[startIdx] + contourW[endIdx]);
          m8SlopeDev = (contourW[midIdx] - chordMidW) / startW;
        } else {
          m8SlopeDev = 0.0;
        }

        if (taperStartU <= 0.48) {
          const idx80 = Math.min(numPts - 1, Math.floor((numPts - 1) * 0.80));
          const idx90 = Math.min(numPts - 1, Math.floor((numPts - 1) * 0.90));
          m8U80Ratio = contourW[idx80] / Math.max(1.0, shaftW);
          m8U90Ratio = contourW[idx90] / Math.max(1.0, shaftW);
        } else {
          const idx55 = Math.min(numPts - 1, Math.floor(startIdx + (endIdx - startIdx) * 0.55));
          const idx78 = Math.min(numPts - 1, Math.floor(startIdx + (endIdx - startIdx) * 0.78));
          m8U80Ratio = contourW[idx55] / startW;
          m8U90Ratio = contourW[idx78] / startW;
        }
      }

      // -----------------------------------------------------------------------
      // Metric 9: Anti-Bulbous Middle Control
      // -----------------------------------------------------------------------
      let m9MidBulgeRatio = 0.0;
      let m9MaxBodyRatio = 0.0;
      let m9MidArchExcessPx = 0.0;

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

      // Check mid-stroke outward convexity for non-dot strokes
      if (!beh.isDot && !beh.isCrownDot) {
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
      } else {
        m9MidArchExcessPx = 0.0;
      }

      // -----------------------------------------------------------------------
      // Metric 10: Short-Stroke & Dot Elongation / Anti-Roundness
      // -----------------------------------------------------------------------
      const strokeLenPx = (compiled.totalLen || compiled.origLen || 1.0) * (792.0 / 109.0);
      let maxContourW = 1.0;
      for (let i = 0; i < numPts; i++) {
        if (contourW[i] > maxContourW) maxContourW = contourW[i];
      }
      const m10LengthToWidthRatio = strokeLenPx / maxContourW;

      let m10RasterAspectRatio = 3.0;
      const isFoldedOrHooked = !!(beh.isFold || genuineCorners.length > 0 || hf);
      if (isFoldedOrHooked) {
        m10RasterAspectRatio = m10LengthToWidthRatio;
      } else {
        let sumW = 0, sumX = 0, sumY = 0;
        for (let y = strokeBbox.minY; y <= strokeBbox.maxY; y++) {
          for (let x = strokeBbox.minX; x <= strokeBbox.maxX; x++) {
            const a = imgRaw[(y * 792 + x) * 4 + 3];
            if (a >= 32) {
              sumW += 1;
              sumX += x;
              sumY += y;
            }
          }
        }
        if (sumW >= 10) {
          const meanX = sumX / sumW;
          const meanY = sumY / sumW;
          let mu20 = 0, mu02 = 0, mu11 = 0;
          for (let y = strokeBbox.minY; y <= strokeBbox.maxY; y++) {
            const dy = y - meanY;
            for (let x = strokeBbox.minX; x <= strokeBbox.maxX; x++) {
              if (imgRaw[(y * 792 + x) * 4 + 3] >= 32) {
                const dx = x - meanX;
                mu20 += dx * dx;
                mu02 += dy * dy;
                mu11 += dx * dy;
              }
            }
          }
          mu20 /= sumW; mu02 /= sumW; mu11 /= sumW;
          const diff = mu20 - mu02;
          const disc = Math.sqrt(diff * diff + 4 * mu11 * mu11);
          const lambda1 = Math.max(0.1, 0.5 * (mu20 + mu02 + disc));
          const lambda2 = Math.max(0.1, 0.5 * (mu20 + mu02 - disc));
          const chordPx = Math.max(1.0, Math.hypot(pts[numPts - 1].x - pts[0].x, pts[numPts - 1].y - pts[0].y));
          const arcToChord = Math.max(1.0, strokeLenPx / chordPx);
          m10RasterAspectRatio = Math.sqrt(lambda1 / lambda2) * arcToChord;
        } else {
          m10RasterAspectRatio = m10LengthToWidthRatio;
        }
      }

      let m10DotEndBloatRatio = 0.0;
      if (beh.isDot || beh.isCrownDot) {
        m10DotEndBloatRatio = contourW[numPts - 1] / maxContourW;
      }

      // Characteristic body width for Metric 11
      let sumContourW = 0, cntContourW = 0;
      const uMinBody = beh.isRisingTi ? 0.08 : 0.12;
      const uMaxBody = beh.isRisingTi ? 0.35 : (isTapered ? 0.55 : (beh.isDot ? 0.62 : 0.82));
      for (let i = 0; i < numPts; i++) {
        const p = pts[i];
        if (p.u >= uMinBody && p.u <= uMaxBody) {
          let nearFeat = false;
          for (const cf of genuineCorners) {
            if (Math.abs(p.s - cf.s) <= 5.5) {
              nearFeat = true;
              break;
            }
          }
          if (hf && Math.abs(p.s - hf.s) <= 5.5) {
            nearFeat = true;
          }
          if (!nearFeat) {
            sumContourW += contourW[i];
            cntContourW++;
          }
        }
      }
      const meanW = cntContourW > 0 ? (sumContourW / cntContourW) : shaftDiam;

      // -----------------------------------------------------------------------
      // Metric 12: Terminal Tome Clubbing & Acute Corner Webbing
      // -----------------------------------------------------------------------
      let m12TomeRatio = 1.0;
      if (!isTapered && !beh.isDot && !beh.isCrownDot) {
        let sumMid = 0, cntMid = 0;
        let maxEndW = 0.0;
        for (let i = 0; i < numPts; i++) {
          const p = pts[i];
          let nearCorner = false;
          for (const cf of genuineCorners) {
            if (Math.abs(p.s - cf.s) <= 5.5) {
              nearCorner = true;
              break;
            }
          }
          if (nearCorner) continue;

          if (p.u >= 0.30 && p.u <= 0.55) {
            sumMid += contourW[i];
            cntMid++;
          }
          if (p.u >= 0.75) {
            if (hf && Math.abs(p.s - hf.s) <= 7.5) continue;
            if (contourW[i] > maxEndW) {
              maxEndW = contourW[i];
            }
          }
        }
        const midShaftW = cntMid > 0 ? (sumMid / cntMid) : shaftDiam;
        m12TomeRatio = (midShaftW > 1.0 && maxEndW > 0) ? (maxEndW / midShaftW) : 1.0;
      }

      let m12CornerBloatRatio = 0.0;
      if (genuineCorners.length > 0) {
        let maxCornerW = 0.0;
        for (let i = 0; i < numPts; i++) {
          const p = pts[i];
          let atCorner = false;
          for (const cf of genuineCorners) {
            if (Math.abs(p.s - cf.s) <= 5.5) {
              atCorner = true;
              break;
            }
          }
          if (atCorner && contourW[i] > maxCornerW) {
            maxCornerW = contourW[i];
          }
        }
        m12CornerBloatRatio = maxCornerW / Math.max(1.0, shaftDiam);
      }

      // -----------------------------------------------------------------------
      // Ink & Paper Physics Quality Metrics I1 - I7 (Measured from Canvas Pixels)
      // -----------------------------------------------------------------------
      let intCount = 0;
      let sumA = 0.0, sumA2 = 0.0;
      let sumD = 0.0, sumD2 = 0.0;
      let valleyDarkSum = 0.0, valleyCount = 0;
      let ridgeDarkSum = 0.0, ridgeCount = 0;
      let rimDarkSum = 0.0, rimCount = 0;
      let troughDarkSum = 0.0, troughCount = 0;
      let coreDarkSum = 0.0, coreCount = 0;
      let haloTotalCount = 0, haloBleedCount = 0;
      let haloValleyAlphaSum = 0.0, haloValleyCount = 0;
      let haloRidgeAlphaSum = 0.0, haloRidgeCount = 0;
      let thinWarmSum = 0.0, thinWarmCount = 0;
      let thickWarmSum = 0.0, thickWarmCount = 0;
      const dwellDarkSamples = [];
      const shaftDarkSamples = [];

      const yStart = Math.max(5, strokeBbox.minY);
      const yEnd = Math.min(786, strokeBbox.maxY);
      const xStart = Math.max(5, strokeBbox.minX);
      const xEnd = Math.min(786, strokeBbox.maxX);

      for (let py = yStart; py <= yEnd; py++) {
        const rowOff = py * 792;
        for (let px = xStart; px <= xEnd; px++) {
          const gIdx = rowOff + px;
          const pOff = gIdx * 4;
          const a = imgRaw[pOff + 3];
          const aU1 = imgRaw[((py - 1) * 792 + px) * 4 + 3];
          const aD1 = imgRaw[((py + 1) * 792 + px) * 4 + 3];
          const aL1 = imgRaw[(rowOff + px - 1) * 4 + 3];
          const aR1 = imgRaw[(rowOff + px + 1) * 4 + 3];
          const aU2 = imgRaw[((py - 2) * 792 + px) * 4 + 3];
          const aD2 = imgRaw[((py + 2) * 792 + px) * 4 + 3];
          const aL2 = imgRaw[(rowOff + px - 2) * 4 + 3];
          const aR2 = imgRaw[(rowOff + px + 2) * 4 + 3];
          const minN1 = Math.min(aU1, aD1, aL1, aR1);
          const maxN2 = Math.max(aU1, aD1, aL1, aR1, aU2, aD2, aL2, aR2);

          const hVal = paperSub.height[gIdx];
          const gZero = paperSub.zeroB5Grain[gIdx];

          if (a < 30) {
            if (maxN2 >= 80) {
              haloTotalCount++;
              if (a > 0) haloBleedCount++;
              if (hVal < 0.48) {
                haloValleyAlphaSum += a;
                haloValleyCount++;
              } else if (hVal > 0.52) {
                haloRidgeAlphaSum += a;
                haloRidgeCount++;
              }
            }
            continue;
          }

          if (a >= 115 && minN1 >= 80) {
            const r = imgRaw[pOff];
            const g = imgRaw[pOff + 1];
            const b = imgRaw[pOff + 2];
            const lum = 0.299 * r + 0.587 * g + 0.114 * b;
            const dark = (a / 255.0) * (255.0 - lum);

            intCount++;
            sumA += a;
            sumA2 += a * a;
            sumD += dark;
            sumD2 += dark * dark;

            if (gZero < -0.22) {
              valleyDarkSum += dark;
              valleyCount++;
            } else if (gZero > 0.22) {
              ridgeDarkSum += dark;
              ridgeCount++;
            }

            const aU3 = imgRaw[((py - 3) * 792 + px) * 4 + 3];
            const aD3 = imgRaw[((py + 3) * 792 + px) * 4 + 3];
            const aL3 = imgRaw[(rowOff + px - 3) * 4 + 3];
            const aR3 = imgRaw[(rowOff + px + 3) * 4 + 3];
            const minN23 = Math.min(aU2, aD2, aL2, aR2, aU3, aD3, aL3, aR3);
            const aU5 = imgRaw[((py - 5) * 792 + px) * 4 + 3];
            const aD5 = imgRaw[((py + 5) * 792 + px) * 4 + 3];
            const aL5 = imgRaw[(rowOff + px - 5) * 4 + 3];
            const aR5 = imgRaw[(rowOff + px + 5) * 4 + 3];
            const minN5 = Math.min(aU5, aD5, aL5, aR5);

            if (minN23 < 60) {
              rimDarkSum += dark;
              rimCount++;
            } else {
              coreDarkSum += dark;
              coreCount++;
              if (minN23 >= 100 && minN5 < 80) {
                troughDarkSum += dark;
                troughCount++;
              }
            }

            const wRgb = r - b;
            if (a <= 188) {
              thinWarmSum += wRgb;
              thinWarmCount++;
            } else if (a >= 202) {
              thickWarmSum += wRgb;
              thickWarmCount++;
            }

            if (intCount % 3 === 0) {
              // Associate pixel with nearest sample u for dwell vs. mid-shaft comparison
              let bestDistSq = Infinity;
              let bestIdx = 0;
              for (let k = 0; k < numPts; k += 2) {
                const dx = px - pts[k].x;
                const dy = py - pts[k].y;
                const d2 = dx * dx + dy * dy;
                if (d2 < bestDistSq) {
                  bestDistSq = d2;
                  bestIdx = k;
                }
              }
              const sp = pts[bestIdx];
              let inDwell = (sp.u <= 0.16) || (!isTapered && sp.u >= 0.82) || (beh.isRightNa && sp.u >= 0.60 && sp.u <= 0.86);
              if (!inDwell && hf && Math.abs(sp.s - hf.s) <= 8.0) inDwell = true;
              if (!inDwell) {
                for (const cf of genuineCorners) {
                  if (Math.abs(sp.s - cf.s) <= 6.5) {
                    inDwell = true;
                    break;
                  }
                }
              }
              if (inDwell) {
                dwellDarkSamples.push(dark);
              } else if (sp.u >= 0.24 && sp.u <= 0.64) {
                shaftDarkSamples.push(dark);
              }
            }
          }
        }
      }

      const meanIntA = intCount > 0 ? (sumA / intCount) : 0.0;
      const i1InteriorAlphaStd = intCount > 1 ? Math.sqrt(Math.max(0.0, sumA2 / intCount - meanIntA * meanIntA)) : 0.0;
      const meanIntD = intCount > 0 ? (sumD / intCount) : 0.0;
      const i1InteriorDarknessStd = intCount > 1 ? Math.sqrt(Math.max(0.0, sumD2 / intCount - meanIntD * meanIntD)) : 0.0;

      const i2ValleyRidgeContrast = (valleyCount > 0 && ridgeCount > 0)
        ? ((valleyDarkSum / valleyCount) - (ridgeDarkSum / ridgeCount))
        : 0.0;

      const refTroughMean = troughCount >= 8 ? (troughDarkSum / troughCount) : (coreDarkSum / Math.max(1, coreCount));
      const i3CoffeeRingRimDelta = rimCount > 0 ? ((rimDarkSum / rimCount) - refTroughMean) : 0.0;

      const i4NijimiFringeRatio = haloTotalCount > 0 ? (haloBleedCount / haloTotalCount) : 0.0;
      const i4NijimiValleyAnisotropy = (haloValleyCount > 0 && haloRidgeCount > 0)
        ? ((haloValleyAlphaSum / haloValleyCount) - (haloRidgeAlphaSum / haloRidgeCount))
        : 0.0;

      const i5GlueWarmthShift = (thinWarmCount > 0 && thickWarmCount > 0)
        ? ((thinWarmSum / thinWarmCount) - (thickWarmSum / thickWarmCount))
        : 0.0;

      // I6: Skeletal Bristle-Track Transverse Striation RMS
      let sumTransDiffSq = 0.0;
      let countTransDiff = 0;
      for (let i = 2; i < stopIdx - 1; i += 2) {
        const p = pts[i];
        const halfW = Math.max(3.5, 0.46 * contourW[i] - 1.2);
        for (let s = -halfW; s <= halfW - 1.0; s += 1.0) {
          if (Math.abs(s) < 2.6 && Math.abs(s + 1.0) < 2.6) continue;
          const qx1 = Math.round(p.x + p.nx * s);
          const qy1 = Math.round(p.y + p.ny * s);
          const qx2 = Math.round(p.x + p.nx * (s + 1.0));
          const qy2 = Math.round(p.y + p.ny * (s + 1.0));
          if (qx1 < 0 || qx1 >= 792 || qy1 < 0 || qy1 >= 792 || qx2 < 0 || qx2 >= 792 || qy2 < 0 || qy2 >= 792) continue;
          const idx1 = (qy1 * 792 + qx1) * 4;
          const idx2 = (qy2 * 792 + qx2) * 4;
          const a1 = imgRaw[idx1 + 3], a2 = imgRaw[idx2 + 3];
          if (a1 >= 120 && a2 >= 120) {
            const lum1 = 0.299 * imgRaw[idx1] + 0.587 * imgRaw[idx1 + 1] + 0.114 * imgRaw[idx1 + 2];
            const lum2 = 0.299 * imgRaw[idx2] + 0.587 * imgRaw[idx2 + 1] + 0.114 * imgRaw[idx2 + 2];
            const d1 = (a1 / 255.0) * (255.0 - lum1);
            const d2 = (a2 / 255.0) * (255.0 - lum2);
            const diff = d2 - d1;
            sumTransDiffSq += diff * diff;
            countTransDiff++;
          }
        }
      }
      const i6BristleStriationRms = countTransDiff > 0 ? Math.sqrt(sumTransDiffSq / countTransDiff) : 0.0;

      // I7: Calligraphic Dwell & Pause Pooling Enrichment (80th percentile dwell vs. median mid-shaft)
      dwellDarkSamples.sort((a, b) => a - b);
      shaftDarkSamples.sort((a, b) => a - b);
      const dwellP80 = dwellDarkSamples.length > 0
        ? dwellDarkSamples[Math.min(dwellDarkSamples.length - 1, Math.floor(dwellDarkSamples.length * 0.80))]
        : meanIntD;
      const shaftP50 = shaftDarkSamples.length > 0
        ? shaftDarkSamples[Math.floor(shaftDarkSamples.length * 0.50)]
        : refTroughMean;
      const i7DwellPoolEnrichment = dwellP80 - shaftP50;

      // Package stroke evaluation
      const strokeEvalObj = {
        strokeIndex: sIdx + 1,
        id: stroke.id || `s-${sIdx + 1}`,
        type: stroke.type || "",
        component: stroke.component || "",
        numSamples: numPts,
        hasHook: !!hf,
        isTapered,
        isDot: !!beh.isDot,
        isCrownDot: !!beh.isCrownDot,
        hasCrossing: false,
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
        m9_mid_arch_excess_px: Number(m9MidArchExcessPx.toFixed(2)),
        m10_length_to_width_ratio: Number(m10LengthToWidthRatio.toFixed(2)),
        m10_raster_aspect_ratio: Number(m10RasterAspectRatio.toFixed(2)),
        m10_dot_end_bloat_ratio: Number(m10DotEndBloatRatio.toFixed(2)),
        m11_crossing_width_ratio: 1.0,
        m11_crossing_mean_ratio: 1.0,
        m11_char_width_ratio: 1.0,
        m12_tome_ratio: Number(m12TomeRatio.toFixed(2)),
        m12_corner_bloat_ratio: Number(m12CornerBloatRatio.toFixed(2)),
        i1_interior_darkness_std: Number(i1InteriorDarknessStd.toFixed(2)),
        i1_interior_alpha_std: Number(i1InteriorAlphaStd.toFixed(2)),
        i2_valley_ridge_contrast: Number(i2ValleyRidgeContrast.toFixed(2)),
        i3_coffee_ring_rim_delta: Number(i3CoffeeRingRimDelta.toFixed(2)),
        i4_nijimi_fringe_ratio: Number(i4NijimiFringeRatio.toFixed(3)),
        i4_nijimi_valley_anisotropy: Number(i4NijimiValleyAnisotropy.toFixed(2)),
        i5_glue_warmth_shift: Number(i5GlueWarmthShift.toFixed(2)),
        i6_bristle_striation_rms: Number(i6BristleStriationRms.toFixed(2)),
        i7_dwell_pool_enrichment: Number(i7DwellPoolEnrichment.toFixed(2)),
        i8_crossing_layer_darkening: 0.0,
      };

      strokeEvals.push(strokeEvalObj);
      compiledStrokesInfo.push({
        sIdx,
        pts,
        contourW,
        origLen: compiled.origLen || 0,
        meanW,
        meanIntD,
        isRisingTi: !!beh.isRisingTi,
        isDot: !!beh.isDot,
        isTapered,
        evalObj: strokeEvalObj
      });
    }

    // -------------------------------------------------------------------------
    // Metric 11 & I8: Crossing Width Consistency & Multi-Stroke KM Layering
    // -------------------------------------------------------------------------
    for (let a = 0; a < compiledStrokesInfo.length; a++) {
      const sA = compiledStrokesInfo[a];
      const maxFlatU_A = sA.isRisingTi ? 0.32 : (sA.isTapered ? 0.52 : (sA.isDot ? 0.60 : 0.75));
      for (let b = a + 1; b < compiledStrokesInfo.length; b++) {
        const sB = compiledStrokesInfo[b];
        const maxFlatU_B = sB.isRisingTi ? 0.32 : (sB.isTapered ? 0.52 : (sB.isDot ? 0.60 : 0.75));

        for (let iA = 0; iA < sA.pts.length - 1; iA += 2) {
          const pA1 = sA.pts[iA];
          const pA2 = sA.pts[Math.min(iA + 2, sA.pts.length - 1)];
          const uMidA = 0.5 * (pA1.u + pA2.u);
          if (uMidA < 0.18 || uMidA > 0.82) continue;

          for (let iB = 0; iB < sB.pts.length - 1; iB += 2) {
            const pB1 = sB.pts[iB];
            const pB2 = sB.pts[Math.min(iB + 2, sB.pts.length - 1)];
            const uMidB = 0.5 * (pB1.u + pB2.u);
            if (uMidB < 0.18 || uMidB > 0.82) continue;

            if (checkSegmentsIntersect(pA1, pA2, pB1, pB2)) {
              // ALWAYS compare crossing_mean_ratio for interior crossings
              const crossMeanRatio = Math.max(sA.meanW, sB.meanW) / Math.max(1.0, Math.min(sA.meanW, sB.meanW));
              sA.evalObj.m11_crossing_mean_ratio = Math.max(sA.evalObj.m11_crossing_mean_ratio, crossMeanRatio);
              sB.evalObj.m11_crossing_mean_ratio = Math.max(sB.evalObj.m11_crossing_mean_ratio, crossMeanRatio);

              // Only compare local point width wA vs wB when both strokes are in their mid-body
              if (uMidA >= 0.20 && uMidA <= maxFlatU_A && uMidB >= 0.20 && uMidB <= maxFlatU_B) {
                const wA = sA.contourW[iA];
                const wB = sB.contourW[iB];
                const crossWRatio = Math.max(wA, wB) / Math.max(1.0, Math.min(wA, wB));
                sA.evalObj.m11_crossing_width_ratio = Math.max(sA.evalObj.m11_crossing_width_ratio, crossWRatio);
                sB.evalObj.m11_crossing_width_ratio = Math.max(sB.evalObj.m11_crossing_width_ratio, crossWRatio);
              }

              // I8: Multi-stroke Kubelka-Munk optical glazing darkening at crossing
              if (fullImgDataArr) {
                const cx = Math.round(0.25 * (pA1.x + pA2.x + pB1.x + pB2.x));
                const cy = Math.round(0.25 * (pA1.y + pA2.y + pB1.y + pB2.y));
                let crossDarkSum = 0.0, crossCnt = 0;
                for (let dy = -2; dy <= 2; dy++) {
                  const qy = cy + dy;
                  if (qy < 0 || qy >= 792) continue;
                  for (let dx = -2; dx <= 2; dx++) {
                    const qx = cx + dx;
                    if (qx < 0 || qx >= 792) continue;
                    const cOff = (qy * 792 + qx) * 4;
                    const ca = fullImgDataArr[cOff + 3];
                    if (ca >= 200) {
                      const clum = 0.299 * fullImgDataArr[cOff] + 0.587 * fullImgDataArr[cOff + 1] + 0.114 * fullImgDataArr[cOff + 2];
                      crossDarkSum += (ca / 255.0) * (255.0 - clum);
                      crossCnt++;
                    }
                  }
                }
                if (crossCnt >= 4) {
                  const crossDarkMean = crossDarkSum / crossCnt;
                  const singleAvg = 0.5 * (sA.meanIntD + sB.meanIntD);
                  const deltaCross = crossDarkMean - singleAvg;
                  sA.evalObj.hasCrossing = true;
                  sB.evalObj.hasCrossing = true;
                  sA.evalObj.i8_crossing_layer_darkening = Math.max(sA.evalObj.i8_crossing_layer_darkening, Number(deltaCross.toFixed(2)));
                  sB.evalObj.i8_crossing_layer_darkening = Math.max(sB.evalObj.i8_crossing_layer_darkening, Number(deltaCross.toFixed(2)));
                }
              }
            }
          }
        }
      }
    }

    const longStrokes = compiledStrokesInfo.filter(d => (d.origLen || 0) >= 16.0);
    if (longStrokes.length >= 2) {
      const sortedW = longStrokes.map(d => d.meanW).sort((x, y) => x - y);
      const mid = Math.floor(sortedW.length / 2);
      const charMedianW = (sortedW.length % 2 !== 0) ? sortedW[mid] : 0.5 * (sortedW[mid - 1] + sortedW[mid]);
      for (const d of longStrokes) {
        d.evalObj.m11_char_width_ratio = d.meanW / Math.max(1.0, charMedianW);
      }
    }

    for (const info of compiledStrokesInfo) {
      info.evalObj.m11_crossing_width_ratio = Number(info.evalObj.m11_crossing_width_ratio.toFixed(2));
      info.evalObj.m11_crossing_mean_ratio = Number(info.evalObj.m11_crossing_mean_ratio.toFixed(2));
      info.evalObj.m11_char_width_ratio = Number(info.evalObj.m11_char_width_ratio.toFixed(2));
    }

    // Clean up DOM elements for this character to prevent memory accumulation
    targetElement.remove();

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
} catch (err) {
    const errEl = document.createElement("script");
    errEl.id = "eval-error";
    errEl.type = "application/json";
    errEl.textContent = JSON.stringify({ message: err ? err.message : "Unknown", stack: err ? err.stack : "" });
    document.body.appendChild(errEl);
  }
})();
"""

    return f"""<!DOCTYPE html>
<html data-theme="light">
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


def find_chrome_binary() -> str:
    """Returns the first available headless-capable Chrome/Chromium executable."""
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return "google-chrome"


def run_headless_evaluator(html_content: str) -> dict[str, Any]:
    """Executes evaluation HTML in headless Chrome and parses the eval-output JSON payload."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        tmp_path = f.name

    try:
        cmd = [
            find_chrome_binary(),
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--dump-dom",
            f"file://{tmp_path}",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        stdout = proc.stdout

        err_match = re.search(r'<script id="eval-error" type="application/json">(.*?)</script>', stdout, re.DOTALL)
        if err_match:
            err_data = json.loads(err_match.group(1))
            raise RuntimeError(f"Browser JS Exception: {err_data.get('message')}\nStack: {err_data.get('stack')}")

        match = re.search(r'<script id="eval-output" type="application/json">(.*?)</script>', stdout, re.DOTALL)
        if not match:
            err_msg = f"Failed to extract eval-output from Chrome dump-dom (stdout len={len(stdout)}).\nSTDOUT TAIL: {stdout[-500:]}\nSTDERR: {proc.stderr[:1000]}"
            raise RuntimeError(err_msg)

        json_data = json.loads(match.group(1))
        return json_data
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _evaluate_batch_worker(payload: tuple[dict[str, list[dict[str, Any]]], str]) -> dict[str, Any]:
    """Worker function for parallel headless Chrome batch execution."""
    batch_char_strokes, app_js_content = payload
    batch_html = build_evaluation_html(batch_char_strokes, app_js_content)
    return run_headless_evaluator(batch_html)


def evaluate_ink_physics_defects(stroke: dict[str, Any]) -> dict[str, bool]:
    """Checks whether a stroke violates physical ink & Xuan paper quality thresholds I1-I8."""
    return {
        "I1_km_transmittance": (
            stroke.get("i1_interior_darkness_std", 0.0) < THRESHOLDS["i1_min_interior_darkness_std"]
            or stroke.get("i1_interior_alpha_std", 0.0) < THRESHOLDS["i1_min_interior_alpha_std"]
        ),
        "I2_xuan_valley_granulation": (
            stroke.get("i2_valley_ridge_contrast", 0.0) < THRESHOLDS["i2_min_valley_ridge_contrast"]
        ),
        "I3_coffee_ring_rim": (
            stroke.get("i3_coffee_ring_rim_delta", 0.0) < THRESHOLDS["i3_min_coffee_ring_rim_delta"]
        ),
        "I4_lbm_nijimi_dispersion": (
            stroke.get("i4_nijimi_fringe_ratio", 0.0) < THRESHOLDS["i4_min_nijimi_fringe_ratio"]
            or stroke.get("i4_nijimi_valley_anisotropy", 0.0) < THRESHOLDS["i4_min_nijimi_valley_anisotropy"]
        ),
        "I5_colloidal_glue_warmth": (
            stroke.get("i5_glue_warmth_shift", 0.0) < THRESHOLDS["i5_min_glue_warmth_shift"]
        ),
        "I6_bristle_striations": (
            stroke.get("i6_bristle_striation_rms", 0.0) < THRESHOLDS["i6_min_bristle_striation_rms"]
        ),
        "I7_dwell_pooling": (
            stroke.get("i7_dwell_pool_enrichment", 0.0) < THRESHOLDS["i7_min_dwell_pool_enrichment"]
        ),
        "I8_multi_stroke_km_glaze": (
            stroke.get("hasCrossing", False)
            and stroke.get("i8_crossing_layer_darkening", 0.0) < THRESHOLDS["i8_min_crossing_layer_darkening"]
        ),
    }


def evaluate_defects(stroke: dict[str, Any]) -> dict[str, bool]:
    """Checks whether a stroke violates thresholds across brushwork metrics M1-M12 and ink physics metrics I1-I8."""
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
            stroke["m9_mid_bulge_ratio"] > THRESHOLDS["m9_max_mid_bulge_ratio"]
            or stroke["m9_max_body_ratio"] > THRESHOLDS["m9_max_body_ratio"]
            or stroke["m9_mid_arch_excess_px"] > THRESHOLDS["m9_max_mid_arch_excess_px"]
        ),
        "M10_short_round": (
            stroke["m10_length_to_width_ratio"] < THRESHOLDS["m10_min_length_to_width_ratio"]
            or stroke["m10_raster_aspect_ratio"] < THRESHOLDS["m10_min_raster_aspect_ratio"]
            or (
                (stroke.get("isDot") or stroke.get("isCrownDot"))
                and stroke["m10_dot_end_bloat_ratio"] > THRESHOLDS["m10_max_dot_end_bloat_ratio"]
            )
        ),
        "M11_width_mismatch": (
            stroke["m11_crossing_width_ratio"] > THRESHOLDS["m11_max_crossing_width_ratio"]
            or stroke["m11_crossing_mean_ratio"] > THRESHOLDS["m11_max_crossing_mean_ratio"]
            or stroke["m11_char_width_ratio"] > THRESHOLDS["m11_max_char_width_ratio"]
            or stroke["m11_char_width_ratio"] < THRESHOLDS["m11_min_char_width_ratio"]
        ),
        "M12_terminal_or_corner_bloat": (
            stroke["m12_tome_ratio"] > THRESHOLDS["m12_max_tome_ratio"]
            or stroke["m12_corner_bloat_ratio"] > THRESHOLDS["m12_max_corner_bloat_ratio"]
        ),
    }
    if "i1_interior_darkness_std" in stroke:
        defects.update(evaluate_ink_physics_defects(stroke))
    return defects


def print_evaluation_summary(
    results: dict[str, Any],
    only_defects: bool = False,
    summary_only: bool = False,
) -> None:
    """Formats and prints clean human-readable tables per character and aggregate summaries."""
    print("=" * 165)
    print(" PROGRAMMATIC CANVAS BRUSHWORK EVALUATOR — SLENDER GOLD ENGINE AUDIT (HEADLESS CHROME)")
    print("=" * 165)

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
        "M10_short_round": 0,
        "M11_width_mismatch": 0,
        "M12_terminal_or_corner_bloat": 0,
        "I1_km_transmittance": 0,
        "I2_xuan_valley_granulation": 0,
        "I3_coffee_ring_rim": 0,
        "I4_lbm_nijimi_dispersion": 0,
        "I5_colloidal_glue_warmth": 0,
        "I6_bristle_striations": 0,
        "I7_dwell_pooling": 0,
        "I8_multi_stroke_km_glaze": 0,
    }
    hook_strokes_total = 0
    tapered_strokes_total = 0
    crossing_strokes_total = 0
    defective_strokes: list[dict[str, Any]] = []

    filter_defects_only = only_defects or (len(results) > 50)

    for char, cdata in results.items():
        strokes = cdata.get("strokes", [])
        total_strokes_all += len(strokes)

        char_has_defects = False
        rows_to_print = []

        for s in strokes:
            defects = evaluate_defects(s)
            is_defective = any(defects.values())
            if is_defective:
                char_has_defects = True
                details = []
                if defects["M1_folds"]:
                    details.append(f"M1(folds={s['m1_retrograde_steps']}, self_intersect={s['m1_self_intersections']})")
                if defects["M2_jitter"]:
                    details.append(f"M2(d2={s['m2_edge_d2_px']:.2f}, flip={s['m2_normal_sign_flip_rate']:.2f})")
                if defects["M3_hook"]:
                    details.append(f"M3(tip_err={s['m3_hook_tip_error_px']:.1f}px, ang_err={s['m3_hook_angle_error_deg']:.0f}°, jump={s['m3_hook_splice_jump_px']:.1f}px)")
                if defects["M4_raster_step"]:
                    details.append(f"M4(step={s['m4_max_width_step_px']:.1f}px, unreached={s['m4_kvg_endpoint_unreached_px']:.1f}px)")
                if defects["M5_kasure_barcode"]:
                    details.append(f"M5(gaps={s['m5_max_cross_section_gaps']})")
                if defects["M6_spine_oscillation"]:
                    details.append(f"M6(osc={s['m6_spine_tone_oscillation']}, ripple={s['m6_spine_tone_ripple']:.1f})")
                if defects["M7_topology"]:
                    details.append(f"M7(components={s['m7_disconnected_components']})")
                if defects["M8_taper"]:
                    details.append(f"M8(tip={s['m8_tip_ratio']:.2f}, u80={s['m8_u80_ratio']:.2f}, u90={s['m8_u90_ratio']:.2f}, slp={s['m8_slope_dev']:+.2f})")
                if defects["M9_bulbous"]:
                    details.append(f"M9(mid={s['m9_mid_bulge_ratio']:.2f}, body={s['m9_max_body_ratio']:.2f}, arch={s['m9_mid_arch_excess_px']:.1f}px)")
                if defects["M10_short_round"]:
                    details.append(f"M10(L/W={s['m10_length_to_width_ratio']:.2f}, asp={s['m10_raster_aspect_ratio']:.2f}, dot_end={s['m10_dot_end_bloat_ratio']:.2f})")
                if defects["M11_width_mismatch"]:
                    details.append(f"M11(cross_w={s['m11_crossing_width_ratio']:.2f}, cross_mean={s['m11_crossing_mean_ratio']:.2f}, char_w={s['m11_char_width_ratio']:.2f})")
                if defects["M12_terminal_or_corner_bloat"]:
                    details.append(f"M12(tome={s['m12_tome_ratio']:.2f}, corner={s['m12_corner_bloat_ratio']:.2f})")
                if defects.get("I1_km_transmittance"):
                    details.append(f"I1(dark_std={s.get('i1_interior_darkness_std', 0):.2f}, alpha_std={s.get('i1_interior_alpha_std', 0):.2f})")
                if defects.get("I2_xuan_valley_granulation"):
                    details.append(f"I2(valley_ridge={s.get('i2_valley_ridge_contrast', 0):.2f})")
                if defects.get("I3_coffee_ring_rim"):
                    details.append(f"I3(rim_delta={s.get('i3_coffee_ring_rim_delta', 0):.2f})")
                if defects.get("I4_lbm_nijimi_dispersion"):
                    details.append(f"I4(fringe={s.get('i4_nijimi_fringe_ratio', 0):.2f}, aniso={s.get('i4_nijimi_valley_anisotropy', 0):.2f})")
                if defects.get("I5_colloidal_glue_warmth"):
                    details.append(f"I5(warmth={s.get('i5_glue_warmth_shift', 0):.2f})")
                if defects.get("I6_bristle_striations"):
                    details.append(f"I6(striation_rms={s.get('i6_bristle_striation_rms', 0):.2f})")
                if defects.get("I7_dwell_pooling"):
                    details.append(f"I7(dwell_pool={s.get('i7_dwell_pool_enrichment', 0):.2f})")
                if defects.get("I8_multi_stroke_km_glaze"):
                    details.append(f"I8(cross_dark={s.get('i8_crossing_layer_darkening', 0):.2f})")
                defective_strokes.append({
                    "char": char,
                    "strokeIndex": s["strokeIndex"],
                    "type": s["type"],
                    "component": s.get("component", ""),
                    "details": details,
                })

            for k, is_def in defects.items():
                if is_def and k in defect_counts:
                    defect_counts[k] += 1
            if s["hasHook"]:
                hook_strokes_total += 1
            if s.get("isTapered"):
                tapered_strokes_total += 1
            if s.get("hasCrossing"):
                crossing_strokes_total += 1

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
            m9_val = f"{s['m9_mid_bulge_ratio']:.2f}/{s['m9_max_body_ratio']:.2f}/{s['m9_mid_arch_excess_px']:.1f}"
            if s.get("isDot") or s.get("isCrownDot"):
                m10_val = f"{s['m10_length_to_width_ratio']:.1f}/{s['m10_raster_aspect_ratio']:.1f}/{s['m10_dot_end_bloat_ratio']:.2f}"
            else:
                m10_val = f"{s['m10_length_to_width_ratio']:.1f}/{s['m10_raster_aspect_ratio']:.1f}"
            m11_val = f"{s['m11_crossing_width_ratio']:.2f}/{s['m11_char_width_ratio']:.2f}"
            m12_val = f"{s['m12_tome_ratio']:.2f}/{s['m12_corner_bloat_ratio']:.2f}"

            rows_to_print.append((
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
                m10_val,
                m11_val,
                m12_val,
                defect_str,
            ))

        if not summary_only and (not filter_defects_only or char_has_defects):
            print(f"\nKanji: 【{char}】 ({len(strokes)} strokes) | Full Canvas Render: {'PASS' if cdata.get('fullRenderSuccess') else 'FAIL'} ({cdata.get('fullInkPixels', 0):,} ink px)")
            print("-" * 165)
            headers = [
                "#", "Type", "M1 Folds", "M2 d2/Flip", "M3 Hook Err",
                "M4 Step/End", "M5 Kasure", "M6 Spine", "M7 Isl", "M8 Tip/u90/Slp", "M9 Mid/Body/Arch",
                "M10 L/W/Asp", "M11 Cross/Ch", "M12 Tome/Crn", "Defects"
            ]
            row_fmt = "{:<3} {:<5} {:<11} {:<12} {:<13} {:<14} {:<9} {:<11} {:<7} {:<16} {:<16} {:<14} {:<13} {:<13} {:<18}"
            print(row_fmt.format(*headers))
            print("-" * 165)
            for row in rows_to_print:
                print(row_fmt.format(*row))

    print("\n" + "=" * 165)
    print(" AGGREGATE BRUSHWORK DEFECT AUDIT REPORT")
    print("=" * 165)
    print(f"Total Evaluated Characters : {len(results)}")
    print(f"Total Evaluated Strokes    : {total_strokes_all}")
    print(f"Total Strokes with Hooks   : {hook_strokes_total}")
    print(f"Total Tapered Strokes      : {tapered_strokes_total}")
    print("-" * 165)
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
        ("M9: Bulbous Middle / Belly Bloating", defect_counts["M9_bulbous"], total_strokes_all),
        ("M10: Short-Stroke & Dot Elongation / Anti-Roundness", defect_counts["M10_short_round"], total_strokes_all),
        ("M11: Width Consistency Across Crossing & Character Strokes", defect_counts["M11_width_mismatch"], total_strokes_all),
        ("M12: Terminal Tome Clubbing & Corner Webbing", defect_counts["M12_terminal_or_corner_bloat"], total_strokes_all),
        ("I1: Kubelka-Munk Optical Transmittance & Tonal Dynamic Range", defect_counts["I1_km_transmittance"], total_strokes_all),
        ("I2: Xuan Paper Fiber & Valley Granulation Coupling", defect_counts["I2_xuan_valley_granulation"], total_strokes_all),
        ("I3: Contact-Line Capillary Replenishment / Coffee-Ring Rim", defect_counts["I3_coffee_ring_rim"], total_strokes_all),
        ("I4: Anisotropic D2Q9 LBM Nijimi Dispersion & Pinning", defect_counts["I4_lbm_nijimi_dispersion"], total_strokes_all),
        ("I5: Colloidal Soot / Animal Glue Chromatic Warmth Separation", defect_counts["I5_colloidal_glue_warmth"], total_strokes_all),
        ("I6: Skeletal Bristle-Track Striations & Feibai Coupling", defect_counts["I6_bristle_striations"], total_strokes_all),
        ("I7: Calligraphic Dwell & Pause Pooling Enrichment", defect_counts["I7_dwell_pooling"], total_strokes_all),
        ("I8: Multi-Stroke Kubelka-Munk Optical Layering at Crossings", defect_counts["I8_multi_stroke_km_glaze"], crossing_strokes_total if crossing_strokes_total else 1),
    ]

    for label, count, denom in metric_names:
        pct = (count / denom * 100) if denom > 0 else 0.0
        bar = "█" * int(round(pct / 5)) + "░" * (20 - int(round(pct / 5)))
        print(f"  {label:<64} : {count:>4} / {denom:>4} ({pct:>5.1f}%) [{bar}]")

    print("=" * 165)

    if defective_strokes:
        print(f"\n DEFECTIVE STROKES DETAIL (Showing {min(len(defective_strokes), 50)} of {len(defective_strokes)} defective strokes across {len(results)} characters)")
        print("=" * 165)
        for ds in defective_strokes[:50]:
            comp_info = f" ({ds['component']})" if ds["component"] else ""
            print(f"  - 【{ds['char']}】 Stroke #{ds['strokeIndex']} [{ds['type']}{comp_info}]: " + "; ".join(ds["details"]))
        if len(defective_strokes) > 50:
            print(f"  ... and {len(defective_strokes) - 50} more defective strokes (use --json-out to inspect full list)")
        print("=" * 165)
    else:
        print(f"\n ALL STROKES PASSED EVALUATION WITH ZERO DEFECTS ACROSS {len(results)} CHARACTERS ({total_strokes_all} STROKES)!")
        print("=" * 165)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Programmatic HTML Canvas Brushwork Evaluator for Slender Gold Calligraphy"
    )
    parser.add_argument(
        "--chars",
        type=str,
        default="",
        help="Comma or space-separated list of characters to evaluate",
    )
    parser.add_argument(
        "--joyo",
        action="store_true",
        help="Evaluate all 2,136 Jōyō kanji from data/kanji_explorer.db",
    )
    parser.add_argument(
        "--grade",
        type=str,
        default="",
        help="Optional comma-separated list of grades (e.g. 1,2,3) to evaluate from data/kanji_explorer.db",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional integer limit on number of characters evaluated",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 4),
        help=f"Number of parallel headless Chrome worker processes when evaluating > 40 characters (default: {min(8, os.cpu_count() or 4)})",
    )
    parser.add_argument(
        "--only-defects",
        action="store_true",
        help="Only print individual character tables for characters that have at least 1 defect",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Skip per-character tables and only print aggregate report and defective strokes",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Optional path to export raw evaluation JSON",
    )
    args = parser.parse_args()

    if args.chars.strip():
        chars = [c.strip() for c in re.split(r"[\s,]+", args.chars.strip()) if c.strip()]
    elif args.joyo:
        chars = load_characters_from_db(joyo=True)
    elif args.grade.strip():
        chars = load_characters_from_db(grades_str=args.grade.strip())
    else:
        chars = list(DEFAULT_BENCHMARK_CHARS)

    if args.limit is not None and args.limit > 0:
        chars = chars[: args.limit]

    if not APP_JS_PATH.exists():
        print(f"Error: {APP_JS_PATH} does not exist.", file=sys.stderr)
        sys.exit(1)

    app_js_content = APP_JS_PATH.read_text(encoding="utf-8")

    t_extract_start = time.time()
    char_strokes = extract_strokes_for_characters(chars)
    t_extract_elapsed = time.time() - t_extract_start

    if len(chars) > 40:
        print(f"[INFO] Extracted KanjiVG strokes for {len(chars)} characters in {t_extract_elapsed:.2f}s")
        batch_size = 120
        batches = []
        for i in range(0, len(chars), batch_size):
            batch_chars = chars[i : i + batch_size]
            batch_strokes = {ch: char_strokes.get(ch, []) for ch in batch_chars}
            batches.append((batch_strokes, app_js_content))

        results: dict[str, Any] = {}
        workers = max(1, args.workers)
        print(f"[INFO] Evaluating {len(chars)} characters in {len(batches)} batches across {workers} headless Chrome workers...")
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            future_to_batch = {executor.submit(_evaluate_batch_worker, b): b[0] for b in batches}
            for fut in concurrent.futures.as_completed(future_to_batch):
                batch_res = fut.result()
                results.update(batch_res)

        # Restore original character order
        ordered_results = {ch: results[ch] for ch in chars if ch in results}
        results = ordered_results
    else:
        html_content = build_evaluation_html(char_strokes, app_js_content)
        results = run_headless_evaluator(html_content)

    print_evaluation_summary(
        results,
        only_defects=args.only_defects,
        summary_only=args.summary_only,
    )

    if args.json_out:
        out_path = Path(args.json_out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[INFO] Raw JSON evaluation data saved to: {out_path}")


if __name__ == "__main__":
    main()
