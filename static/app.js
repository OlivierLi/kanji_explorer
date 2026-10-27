/**
 * 漢字構造・部首ドリルダウン探索器 フロントエンド制御スクリプト
 * 100% 日本語UI、CHISE IDS・KanjiVG・Unicodeブロック統合、双方向連動ホバー、
 * マウスホイール階層切替、多要素逆引き（ids-find）対応
 */

// =============================================================================
// 1. 定数およびフォールバック用組込データ
// =============================================================================

// IDC 演算子日本語メタデータ
const IDC_OPERATORS = {
  "⿰": { name: "左右構造", short: "左右", parts: ["左", "右"] },
  "⿱": { name: "上下構造", short: "上下", parts: ["上", "下"] },
  "⿲": { name: "左中右構造", short: "左中右", parts: ["左", "中", "右"] },
  "⿳": { name: "上中下構造", short: "上中下", parts: ["上", "中", "下"] },
  "⿴": { name: "全包囲構造(国構え等)", short: "全包囲", parts: ["外囲", "内側"] },
  "⿵": { name: "上三方包囲(同構え等)", short: "上包囲", parts: ["上囲", "内側"] },
  "⿶": { name: "下三方包囲(凶構え等)", short: "下包囲", parts: ["下囲", "内側"] },
  "⿷": { name: "左三方包囲(区構え等)", short: "左包囲", parts: ["左囲", "内側"] },
  "⿸": { name: "左上包囲(垂れ)", short: "左上包囲", parts: ["垂れ", "内側"] },
  "⿹": { name: "右上包囲(包み構え)", short: "右上包囲", parts: ["包み", "内側"] },
  "⿺": { name: "左下包囲(繞・にょう)", short: "左下包囲", parts: ["繞", "内側"] },
  "⿻": { name: "重ね・交差構造", short: "重ね", parts: ["要素1", "要素2"] },
  "⿼": { name: "右三方包囲", short: "右包囲", parts: ["右囲", "内側"] },
  "⿽": { name: "右下包囲", short: "右下包囲", parts: ["右下囲", "内側"] },
  "⿾": { name: "反転(鏡像)", short: "反転", parts: ["反転対象"] },
  "⿿": { name: "回転", short: "回転", parts: ["回転対象"] }
};

// プリセット用高精度フォールバックデータ（サーバー未起動・オフライン検証対応）
const DEMO_PRESETS_DATA = {
  "蛍": {
    meta: {
      literal: "蛍",
      codepoint: "U+86CD",
      block_name: "CJK統合漢字（基本多言語面）",
      tier: "基本漢字",
      stroke_count: 11,
      radical: "虫(むし・むしへん) [142]",
      on_readings: ["ケイ"],
      kun_readings: ["ほたる"],
      nanori: [],
      grade: 4,
      jlpt: 2,
      freq: 1200,
      badges: ["教育漢字(小学4年)", "常用漢字", "新聞頻度 #1200", "旧JLPT 2級"],
      daikanwa: "33140",
      four_corner: "9013.6",
      skip: "2-2-9",
      cangjie: "FBLMI",
      mojijoho: "MJ022987",
      equivalents: [{ char: "螢", codepoint: "U+87A2", label: "旧字体" }]
    },
    alternatives: [
      { source: "CHISE標準構造", ids: "⿱𰃮虫" },
      { source: "CJKVI構造", ids: "⿳𭕄冖虫" }
    ],
    tree: {
      type: "op",
      op: "⿱",
      char: "蛍",
      path: "0",
      role_label: "全体",
      bbox: [0.0, 0.0, 1.0, 1.0],
      children: [
        {
          type: "op",
          op: "⿱",
          char: "𰃮",
          codepoint: "U+300EE",
          tier: "拡張G",
          path: "0.0",
          role_label: "上",
          bbox: [0.0, 0.0, 1.0, 0.45],
          children: [
            {
              type: "op",
              op: "⿲",
              char: "𭕄",
              raw_char: "⺍",
              codepoint: "U+2D544",
              tier: "拡張F",
              path: "0.0.0",
              role_label: "上",
              bbox: [0.15, 0.0, 0.7, 0.22],
              children: [
                { type: "char", char: "丶", codepoint: "U+4E36", tier: "部首・筆画", path: "0.0.0.0", role_label: "左", bbox: [0.15, 0.0, 0.23, 0.22] },
                { type: "char", char: "丶", codepoint: "U+4E36", tier: "部首・筆画", path: "0.0.0.1", role_label: "中", bbox: [0.38, 0.0, 0.24, 0.22] },
                { type: "char", char: "丿", codepoint: "U+4E3F", tier: "部首・筆画", path: "0.0.0.2", role_label: "右", bbox: [0.62, 0.0, 0.23, 0.22] }
              ]
            },
            {
              type: "char",
              char: "冖",
              codepoint: "U+5196",
              tier: "基本漢字",
              path: "0.0.1",
              role_label: "下",
              bbox: [0.05, 0.22, 0.9, 0.23]
            }
          ]
        },
        {
          type: "op",
          op: "⿱",
          char: "虫",
          codepoint: "U+866B",
          tier: "基本漢字",
          path: "0.1",
          role_label: "下",
          bbox: [0.1, 0.45, 0.8, 0.55],
          children: [
            { type: "char", char: "中", codepoint: "U+4E2D", tier: "基本漢字", path: "0.1.0", role_label: "上", bbox: [0.15, 0.45, 0.7, 0.35] },
            { type: "char", char: "一", codepoint: "U+4E00", tier: "基本漢字", path: "0.1.1", role_label: "下", bbox: [0.1, 0.8, 0.8, 0.2] }
          ]
        }
      ]
    },
    visual: {
      has_kanjivg: true,
      interactive_svg: {
        base_path: "M841 4 826 31 811 56 803 68 755 56 689 41 622 28 553 16 482 5 411 -5 338 -15 264 -23 188 -31 132 -35 122 -53 110 -37 96 26 107 27 183 31 259 35 333 39 406 45 477 51H480V257H263V192L199 160V510L263 477H480V596L544 585L560 575L544 565V477H760L793 504L852 456L825 434V257L760 225V257H544V56H547L617 63L685 70L751 76L795 80L793 82L773 107L752 131L729 155L704 179L677 203L682 211L715 196L746 177L775 158L802 135L828 112L851 87L872 60L891 32L908 3L924 -28L923 -53L906 -70L881 -69L864 -52L853 -24ZM263 456V278H480V456ZM544 456V278H760V456ZM47 477 42 501 55 522 66 529 77 539 87 551 96 567 105 587 113 609 120 634 127 663 132 695 136 730H146L151 695L153 670H653L667 690L686 717L702 741L718 764L733 785L746 805L758 824L767 840L776 856L780 865L785 874L838 836L846 819H824L814 807L800 791L785 775L767 757L749 738L728 719L706 698L681 677L672 670H899L902 672V674H903L931 697L990 648L964 632L945 624L940 619L930 605L918 591L906 576L892 561L878 545L862 528L845 512L828 494L820 499L832 521L842 542L852 563L861 582L871 600L879 617L886 633L892 647L893 648H154V630L152 601L148 574L142 549L134 526L122 505L109 486L92 469L68 464ZM286 739 280 752 274 764 265 777 256 791 245 804 232 818 218 833 202 846 207 854 227 845 245 837 263 827 280 817 295 806 309 794 322 781 334 767 344 752 353 737 352 712 335 695 310 696 293 714 290 726ZM497 755 493 770 487 784 479 798 471 812 461 827 450 842 437 857 422 871 428 878 446 869 465 860 481 849 497 837 512 824 525 810 537 795 548 779 558 762 565 745 562 720 543 705 518 708 503 727 501 741Z",
        component_layers: [
          { path: "0.0", char: "𰃮", depth: 1, role_label: "上", bbox: [0.0, 0.0, 1.0, 0.5] },
          { path: "0.0.0", char: "𭕄", depth: 2, role_label: "上", bbox: [0.0, 0.0, 1.0, 0.25] },
          { path: "0.0.1", char: "冖", depth: 2, role_label: "下", bbox: [0.0, 0.25, 1.0, 0.25] },
          { path: "0.1", char: "虫", depth: 1, role_label: "下", bbox: [0.0, 0.5, 1.0, 0.5] },
          { path: "0.1.0", char: "中", depth: 2, role_label: "上", bbox: [0.0, 0.5, 1.0, 0.25] },
          { path: "0.1.0.0", char: "口", depth: 3, role_label: "外囲", bbox: [0.0, 0.5, 1.0, 0.25] },
          { path: "0.1.0.1", char: "丨", depth: 3, role_label: "内側", bbox: [0.12, 0.53, 0.76, 0.19] },
          { path: "0.1.1", char: "𠃌", depth: 2, role_label: "下", bbox: [0.0, 0.75, 1.0, 0.25] }
        ]
      },
      kanjivg_svg: `
        <svg viewBox="0 0 109 109" class="kvg-root">
          <g id="kvg:086cd" kvg:element="蛍">
            <g id="kvg:086cd-g1" kvg:element="𰃮" kvg:position="top" data-path="0.0">
              <g id="kvg:086cd-g2" kvg:element="𭕄" kvg:original="⺍" data-path="0.0.0">
                <path id="kvg:086cd-s1" class="kvg-stroke" kvg:type="㇔" d="M31.25,12.75c3.27,2.35,6.77,6.48,7.94,9.69"/>
                <path id="kvg:086cd-s2" class="kvg-stroke" kvg:type="㇔" d="M52.75,9.75c2.47,1.88,6.88,6.38,7.72,9.69"/>
                <path id="kvg:086cd-s3" class="kvg-stroke" kvg:type="㇒" d="M78.49,11.23c0.41,0.85,0.22,1.96-0.34,2.95c-1.4,2.44-4.65,6.57-7.9,9.57"/>
              </g>
              <g id="kvg:086cd-g3" kvg:element="冖" data-path="0.0.1">
                <path id="kvg:086cd-s4" class="kvg-stroke" kvg:type="㇔" d="M19.75,27.5c0,3.43-3.21,12.87-4.67,15.16"/>
                <path id="kvg:086cd-s5" class="kvg-stroke" kvg:type="㇖b" d="M21.24,30.34c11.76-1.59,57.19-5.71,66.36-6.15c9.65-0.45,1.94,6.78-0.34,8.56"/>
              </g>
            </g>
            <g id="kvg:086cd-g4" kvg:element="虫" kvg:position="bottom" data-path="0.1">
              <g id="kvg:086cd-g5" kvg:element="中" data-path="0.1.0">
                <g id="kvg:086cd-g6" kvg:element="口" data-path="0.1.0.0">
                  <path id="kvg:086cd-s6" class="kvg-stroke" kvg:type="㇑" d="M30.75,44.42c0.59,0.5,1.33,1.38,1.48,2.03c1.27,5.55,2.42,12.01,3.48,19.26"/>
                  <path id="kvg:086cd-s7" class="kvg-stroke" kvg:type="㇕b" d="M33.22,46.17c9.53-1.04,36.56-4.57,43.43-4.96c2.68-0.15,3.85,1.54,3.22,3.87c-1.62,6-2.62,9.67-4.58,16.48"/>
                  <path id="kvg:086cd-s8" class="kvg-stroke" kvg:type="㇐b" d="M36.17,63.95c9.21-0.82,29.96-2.82,41.45-3.66"/>
                </g>
                <g id="kvg:086cd-g7" kvg:element="丨" data-path="0.1.0.1">
                  <path id="kvg:086cd-s9" class="kvg-stroke" kvg:type="㇑a" d="M52.92,34.25c1.08,1.08,1.46,2.38,1.46,3.94c0,5.06-0.13,38.56-0.13,50.31"/>
                </g>
              </g>
              <path id="kvg:086cd-s10" class="kvg-stroke" kvg:type="㇀" d="M25.75,82.58c1.38,1.17,3.15,1.43,4.64,0.73c7.86-3.69,38.86-18.06,47.86-22.31" data-path="0.1.1"/>
              <path id="kvg:086cd-s11" class="kvg-stroke" kvg:type="㇔" d="M72.25,69.75c5.38,3.95,13.9,16.24,15.25,22.38" data-path="0.1.2"/>
            </g>
          </g>
        </svg>
      `
    }
  },
  "𰃮": {
    meta: {
      literal: "𰃮",
      codepoint: "U+300EE",
      block_name: "CJK統合漢字拡張G",
      tier: "拡張G",
      stroke_count: 5,
      radical: "冖(わかんむり) [14]",
      on_readings: [],
      kun_readings: [],
      nanori: [],
      grade: null,
      jlpt: null,
      freq: null,
      badges: ["拡張G", "構成部品"],
      daikanwa: "-",
      four_corner: "-",
      skip: "2-3-2",
      cangjie: "FB",
      mojijoho: "-",
      equivalents: [{ char: "⺍", codepoint: "U+2E8D", label: "冠部首" }]
    },
    alternatives: [
      { source: "CHISE標準構造", ids: "⿱𭕄冖" }
    ],
    tree: {
      type: "op",
      op: "⿱",
      char: "𰃮",
      path: "0",
      role_label: "全体",
      bbox: [0.0, 0.0, 1.0, 1.0],
      children: [
        {
          type: "op",
          op: "⿲",
          char: "𭕄",
          raw_char: "⺍",
          codepoint: "U+2D544",
          tier: "拡張F",
          path: "0.0",
          role_label: "上",
          bbox: [0.15, 0.05, 0.7, 0.45],
          children: [
            { type: "char", char: "丶", codepoint: "U+4E36", tier: "部首・筆画", path: "0.0.0", role_label: "左", bbox: [0.15, 0.05, 0.23, 0.45] },
            { type: "char", char: "丶", codepoint: "U+4E36", tier: "部首・筆画", path: "0.0.1", role_label: "中", bbox: [0.38, 0.05, 0.24, 0.45] },
            { type: "char", char: "丿", codepoint: "U+4E3F", tier: "部首・筆画", path: "0.0.2", role_label: "右", bbox: [0.62, 0.05, 0.23, 0.45] }
          ]
        },
        {
          type: "char",
          char: "冖",
          codepoint: "U+5196",
          tier: "基本漢字",
          path: "0.1",
          role_label: "下",
          bbox: [0.05, 0.55, 0.9, 0.4]
        }
      ]
    },
    visual: {
      has_kanjivg: false,
      interactive_svg: {
        base_path: "M42 225 36 248 47 270 58 279 69 291 80 306 90 326 99 349 107 375 114 405 120 439 125 476 131 517H141L146 476L148 445H647L661 469L679 499L696 527L712 553L727 577L739 599L751 620L770 657L774 668L779 678L833 643L843 626L821 625L810 609L796 591L781 571L764 551L745 528L724 505L702 481L677 456L665 445H894L896 447V448H897L926 472L985 424L958 408L942 401L936 391L925 376L914 359L901 341L888 324L873 305L857 285L840 265L822 244L814 249L825 274L836 298L846 321L855 342L864 363L872 382L879 401L886 417L888 424H149V402L147 368L143 338L137 309L129 283L118 260L104 239L88 220L64 213ZM280 528 274 544 267 559 259 574 249 589 238 604 225 619 212 635 196 650 202 658 222 648 241 638 259 626 276 614 291 600 306 585 318 570 330 554 341 537 349 518 347 494 329 477 304 480 288 498 285 513ZM492 547 487 564 480 581 473 597 464 613 454 630 443 646 431 663 416 679 422 687 441 675 460 664 477 650 493 636 508 621 521 604 533 587 544 568 553 548 561 528 557 504 537 489 513 493 498 513 495 530Z",
        component_layers: [
          {
            path: "0.0",
            char: "𭕄",
            depth: 1,
            role_label: "上",
            bbox: [0.15, 0.05, 0.7, 0.45],
            svg_path: "M250,200 Q280,260 300,340 M500,160 Q520,240 530,340 M780,180 Q730,260 670,340",
            svg_transform: ""
          },
          {
            path: "0.1",
            char: "冖",
            depth: 1,
            role_label: "下",
            bbox: [0.05, 0.55, 0.9, 0.4],
            svg_path: "M150,550 L120,750 M140,580 L880,580 L850,750",
            svg_transform: ""
          }
        ]
      }
    }
  },
  "𭕄": {
    meta: {
      literal: "𭕄",
      codepoint: "U+2D544",
      block_name: "CJK統合漢字拡張F",
      tier: "拡張F",
      stroke_count: 3,
      radical: "小(しょう・しょうがしら) [42]",
      on_readings: [],
      kun_readings: [],
      nanori: [],
      grade: null,
      jlpt: null,
      freq: null,
      badges: ["拡張F", "末端基礎部品", "つかんむり原字"],
      daikanwa: "-",
      four_corner: "-",
      skip: "1-1-1",
      cangjie: "FF",
      mojijoho: "-",
      equivalents: [{ char: "⺍", codepoint: "U+2E8D", label: "CJK部首補助" }]
    },
    alternatives: [
      { source: "CHISE標準構造", ids: "⿲丶丶丿" }
    ],
    tree: {
      type: "op",
      op: "⿲",
      char: "𭕄",
      path: "0",
      role_label: "全体",
      bbox: [0.0, 0.0, 1.0, 1.0],
      children: [
        { type: "char", char: "丶", codepoint: "U+4E36", tier: "部首・筆画", path: "0.0", role_label: "左", bbox: [0.1, 0.2, 0.25, 0.6] },
        { type: "char", char: "丶", codepoint: "U+4E36", tier: "部首・筆画", path: "0.1", role_label: "中", bbox: [0.38, 0.15, 0.24, 0.7] },
        { type: "char", char: "丿", codepoint: "U+4E3F", tier: "部首・筆画", path: "0.2", role_label: "右", bbox: [0.65, 0.2, 0.25, 0.6] }
      ]
    },
    visual: {
      has_kanjivg: false,
      interactive_svg: {
        base_path: "M855 538 865 520 844 519 839 510 822 481 804 452 787 422 768 391 749 359 729 327 707 294 685 261 661 227 653 232 667 270 682 308 697 344 713 378 728 412 742 445 757 477 771 508 785 538 796 562H795L801 573ZM237 333 229 361 220 387 210 413 200 437 189 461 177 483 165 506 152 528 159 535 180 519 200 501 218 480 235 457 251 433 266 408 279 381 292 352 303 322 313 290 309 266 290 251 266 255 251 275 244 305ZM478 361 471 385 464 409 455 433 435 483 423 508 411 534 398 561 406 567 428 546 447 524 465 501 481 477 496 453 509 428 522 404 532 378 542 353 550 327 546 303 526 289 502 293 487 313 483 337Z",
        component_layers: [
          { path: "0.0", char: "丶", depth: 1, role_label: "左", bbox: [0.1, 0.2, 0.25, 0.6], svg_path: "M250,280 Q290,420 330,600", svg_transform: "" },
          { path: "0.1", char: "丶", depth: 1, role_label: "中", bbox: [0.38, 0.15, 0.24, 0.7], svg_path: "M500,200 Q520,400 540,650", svg_transform: "" },
          { path: "0.2", char: "丿", depth: 1, role_label: "右", bbox: [0.65, 0.2, 0.25, 0.6], svg_path: "M800,260 Q720,450 630,650", svg_transform: "" }
        ]
      }
    }
  }
};

// 逆引き検索用の組込データ（蛍・𰃮・𭕄に関連する包含漢字）
const DEMO_FIND_DATABASE = [
  { literal: "学", codepoint: "U+5B66", tier: "小学校1年", grade: 1, freq: 63, stroke_count: 8, ids: "⿱𰃮子", is_direct: 1, path: "0.0", via: "", readings: "ガク / まなぶ", components: ["𰃮", "子", "𭕄", "冖", "丶", "丿", "了", "一"] },
  { literal: "挙", codepoint: "U+6319", tier: "小学校4年", grade: 4, freq: 257, stroke_count: 10, ids: "⿱𰃮手", is_direct: 1, path: "0.0", via: "", readings: "キョ / あげる", components: ["𰃮", "手", "𭕄", "冖"] },
  { literal: "労", codepoint: "U+52B4", tier: "小学校4年", grade: 4, freq: 398, stroke_count: 7, ids: "⿱𰃮力", is_direct: 1, path: "0.0", via: "", readings: "ロウ", components: ["𰃮", "力", "𭕄", "冖"] },
  { literal: "脳", codepoint: "U+8133", tier: "小学校6年", grade: 6, freq: 459, stroke_count: 11, ids: "⿰月⿱𰃮凶", is_direct: 0, path: "0.1.0", via: "𰃮", readings: "ノウ", components: ["月", "𰃮", "凶", "𭕄", "冖"] },
  { literal: "単", codepoint: "U+5358", tier: "小学校4年", grade: 4, freq: 586, stroke_count: 9, ids: "⿱𰃮甲", is_direct: 1, path: "0.0", via: "", readings: "タン / ひとえ", components: ["𰃮", "甲", "𭕄", "冖", "田", "丨"] },
  { literal: "厳", codepoint: "U+53B3", tier: "小学校6年", grade: 6, freq: 638, stroke_count: 17, ids: "⿱𰃮敢", is_direct: 1, path: "0.0", via: "", readings: "ゲン・ゴン / きびしい", components: ["𰃮", "敢", "𭕄", "冖"] },
  { literal: "覚", codepoint: "U+899A", tier: "小学校4年", grade: 4, freq: 710, stroke_count: 12, ids: "⿱𰃮見", is_direct: 1, path: "0.0", via: "", readings: "カク / おぼえる・さめる", components: ["𰃮", "見", "𭕄", "冖", "目", "儿"] },
  { literal: "栄", codepoint: "U+6804", tier: "小学校4年", grade: 4, freq: 920, stroke_count: 9, ids: "⿱𰃮木", is_direct: 1, path: "0.0", via: "", readings: "エイ / さかえる", components: ["𰃮", "木", "𭕄", "冖", "丶", "丿", "十", "八"] },
  { literal: "誉", codepoint: "U+8A89", tier: "中学校", grade: 8, freq: 1064, stroke_count: 13, ids: "⿱𰃮言", is_direct: 1, path: "0.0", via: "", readings: "ヨ / ほまれ", components: ["𰃮", "言", "𭕄", "冖", "口"] },
  { literal: "巣", codepoint: "U+5DE3", tier: "小学校4年", grade: 4, freq: 1588, stroke_count: 11, ids: "⿱𰃮果", is_direct: 1, path: "0.0", via: "", readings: "ソウ / す", components: ["𰃮", "果", "𭕄", "冖", "日", "木"] },
  { literal: "獣", codepoint: "U+7363", tier: "中学校", grade: 8, freq: 1714, stroke_count: 16, ids: "⿰⿱𰃮田犬", is_direct: 0, path: "0.0.0", via: "𰃮", readings: "ジュウ / けもの", components: ["𰃮", "田", "犬", "𭕄", "冖"] },
  { literal: "蛍", codepoint: "U+86CD", tier: "常用漢字", grade: 8, freq: 2031, stroke_count: 11, ids: "⿱𰃮虫", is_direct: 1, path: "0.0", via: "", readings: "ケイ / ほたる", components: ["𰃮", "虫", "𭕄", "冖", "丶", "丿", "中", "口", "丨", "一"] },
  { literal: "螢", codepoint: "U+87A2", tier: "旧字体・人名", grade: null, freq: 9999, stroke_count: 16, ids: "⿱⿳𤇾冖虫", is_direct: 0, path: "0.0.1", via: "虫", readings: "ケイ / ほたる", components: ["虫", "冖", "火"] }
];

// =============================================================================
// 2. アプリケーション状態管理
// =============================================================================

const state = {
  currentChar: "蛍",
  history: ["蛍"],
  historyIndex: 0,
  activeDisplayMode: "kvg", // 'kvg' (KanjiVG筆画表示 - デフォルト), 'mincho' (明朝体印刷書体)
  lockedPath: null,         // 段階的ロック階層パス (例: null, "0.0", "0.0.0")
  activeStructureIndex: 0,
  charData: null,
  hoveredPath: null,
  hoveredAncestors: [],
  wheelIndex: 0,
  findChips: new Set(["𭕄"]),
  wordsData: null,
  wordsFilter: {
    position: "all",
    tier: "all",
    keyword: ""
  },
  theme: (typeof localStorage !== "undefined" && localStorage.getItem("kanji_theme")) || "light"
};

/**
 * HTML/SVG属性値のエスケープ
 */
function escapeAttr(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// =============================================================================
// 3. ユーティリティ関数群
// =============================================================================

/**
 * CHISE外字実体参照やUnicode文字を適切なHTML要素として描画
 */
function renderGlyphHTML(token, cssClass = "") {
  if (!token) return "";
  const isEntity = token.startsWith("&") && token.endsWith(";");
  const safeCls = escapeAttr(cssClass);
  const safeTok = escapeAttr(token);
  if (isEntity) {
    const safeSrc = `/api/glyph?c=${encodeURIComponent(token)}`;
    return `<img src="${safeSrc}" class="entity-glyph-img ${safeCls}" alt="${safeTok}" onerror="this.outerHTML='<span class=\\'kanji-text\\'>${safeTok}</span>'">`;
  }
  return `<span class="kanji-text ${safeCls}">${safeTok}</span>`;
}

/**
 * コードポイントを16進表記文字列に変換
 */
function getCodepointHex(char) {
  if (!char || char.startsWith("&")) return char || "";
  try {
    const cp = char.codePointAt(0);
    return `U+${cp.toString(16).toUpperCase()}`;
  } catch (e) {
    return char;
  }
}

// =============================================================================
// 4. データ取得 & 検査ロジック
// =============================================================================

/**
 * 指定文字の構文解析およびメタデータをロード
 * @param {string} charOrToken - 調査対象の漢字または文字トークン
 * @param {boolean} recordHistory - 探索履歴に記録するかどうか
 * @param {string} altIds - 構造切替時のカスタムIDS指定（省略時は標準構造）
 */
async function inspectCharacter(charOrToken, recordHistory = true, altIds = "") {
  if (!charOrToken) return;
  const token = charOrToken.trim();
  if (!token) return;

  const idcRegex = /^[⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻⿼⿽⿾⿿]/;
  const isCodepoint = /^(?:[Uu][\+\s]|0[xX])?[0-9a-fA-F]{4,6}$/.test(token);
  const isEntity = /^&[0-9A-Za-z_-]+;?$/.test(token) || /^(?:CDP|GT|MJ|M|C[1-7]|J90|CB|HZK|SW-JIGUGE)-/i.test(token);
  const isIdc = idcRegex.test(token);

  let effectiveToken = token;
  if (!isCodepoint && !isEntity && !isIdc) {
    const chars = Array.from(token.replace(/\s+/g, ""));
    if (chars.length > 1) {
      if (recordHistory && !altIds) {
        if (state.historyIndex < state.history.length - 1) {
          state.history = state.history.slice(0, state.historyIndex + 1);
        }
        chars.forEach(ch => {
          if (state.history[state.history.length - 1] !== ch) {
            state.history.push(ch);
          }
        });
        state.historyIndex = state.history.indexOf(chars[0]);
        if (state.historyIndex === -1) state.historyIndex = 0;
        updateBreadcrumbsUI();
      }
      effectiveToken = chars[0];
    }
  }

  // 履歴更新（構造切替時は新規文字扱いとしない）
  if (recordHistory && !altIds && effectiveToken === token) {
    if (state.historyIndex < state.history.length - 1) {
      state.history = state.history.slice(0, state.historyIndex + 1);
    }
    if (state.history[state.history.length - 1] !== effectiveToken) {
      state.history.push(effectiveToken);
      state.historyIndex = state.history.length - 1;
    }
    updateBreadcrumbsUI();
  }

  // APIリクエスト（/api/char?q=...&alt_ids=...）
  let data = null;
  try {
    const queryUrl = `/api/char?q=${encodeURIComponent(effectiveToken)}${altIds ? '&alt_ids=' + encodeURIComponent(altIds) : ''}`;
    const response = await fetch(queryUrl);
    if (response.ok) {
      data = await response.json();
    }
  } catch (err) {
    console.warn("バックエンドAPI接続待機中(フォールバックデータを表示します):", err);
  }

  // フォールバックデータ設定（サーバー未接続時）
  if (!data) {
    if (DEMO_PRESETS_DATA[effectiveToken]) {
      data = JSON.parse(JSON.stringify(DEMO_PRESETS_DATA[effectiveToken]));
    } else {
      const cp = getCodepointHex(effectiveToken);
      data = {
        meta: {
          literal: effectiveToken,
          char: effectiveToken,
          codepoint: cp,
          block_name: "CJK統合漢字",
          tier: "通常漢字",
          stroke_count: 10,
          radical: "部首情報取得中...",
          ja_on: ["—"],
          ja_kun: ["—"],
          badges: ["基本文字"],
          daikanwa: "—",
          four_corner: "—",
          skip_code: "—",
          cangjie: "—",
          moji_joho: "—",
          equivalents: []
        },
        alternatives: [{ id: "std", label: "標準構造", ids: effectiveToken }],
        tree: {
          type: "char",
          char: effectiveToken,
          path: "0",
          role_label: "全体",
          bbox: [0.0, 0.0, 1.0, 1.0],
          children: []
        },
        visual: {
          has_kanjivg: false,
          interactive_svg: {
            base_path: null,
            component_layers: [
              { path: "0", char: effectiveToken, depth: 0, role_label: "全体", bbox: [0.0, 0.0, 1.0, 1.0], svg_path: null, svg_transform: "" }
            ]
          }
        }
      };
    }
  }

  state.charData = data;
  state.lockedPath = null;

  if (!altIds) {
    state.currentChar = data.meta?.char || data.meta?.literal || effectiveToken;
    state.findChips = new Set([state.currentChar]);
    renderFindChips();
    state.activeStructureIndex = 0;
  } else {
    state.currentChar = data.meta?.char || data.meta?.literal || state.currentChar || effectiveToken;
    const alts = data.alternatives || [];
    const matchIdx = alts.findIndex(a => a.ids === altIds);
    if (matchIdx >= 0) {
      state.activeStructureIndex = matchIdx;
    }
  }

  updateLockControllerUI();
  resetHud();

  // 表示モード制御: KanjiVG筆画データの有無に応じてトグルボタンの状態を同期
  const hasKvg = !!(data.visual && data.visual.has_kanjivg);
  const btnKvg = document.getElementById("btnModeKvg");
  const btnMincho = document.getElementById("btnModeMincho");

  if (!hasKvg) {
    state.activeDisplayMode = "mincho";
    if (btnKvg) {
      btnKvg.disabled = true;
      btnKvg.classList.remove("active");
      btnKvg.title = "この文字のKanjiVG筆画データは未収録です(明朝体印刷書体で表示)";
    }
    if (btnMincho) {
      btnMincho.classList.add("active");
      btnMincho.title = "印刷書体表示(明朝体)";
    }
  } else {
    if (btnKvg) {
      btnKvg.disabled = false;
      btnKvg.title = "筆画表示(KanjiVGベクター・筆画単位ハイライト - デフォルト)";
      if (state.activeDisplayMode === "kvg") {
        btnKvg.classList.add("active");
        if (btnMincho) btnMincho.classList.remove("active");
      }
    }
    if (btnMincho && state.activeDisplayMode === "mincho") {
      btnMincho.classList.add("active");
      if (btnKvg) btnKvg.classList.remove("active");
    }
  }

  // 画面レンダリング更新
  renderCanvas();
  renderAttributeCard();
  renderStructureSelector();
  renderIdsTokens();
  renderRecursiveTree();

  // 逆引き検索を連動更新
  executeFindSearch();

  // 収録熟語・語彙検索を連動更新
  loadWordsForCurrentKanji();
}

/**
 * 構文解析木から特定パスのノードを検索
 */
function findNodeByPath(node, targetPath) {
  if (!node || !targetPath) return null;
  if (node.path === targetPath) return node;
  if (node.children && node.children.length > 0) {
    for (const child of node.children) {
      const found = findNodeByPath(child, targetPath);
      if (found) return found;
    }
  }
  return null;
}

/**
 * KanjiVG グループ要素（漢字・部首）に対応する構文木パスをスマート探索
 */
function findTreePathForElement(treeNode, elementChar, searchPathPrefix = "") {
  if (!treeNode || !elementChar) return null;

  // 1. 接頭辞スコープ内の優先探索
  if (searchPathPrefix && searchPathPrefix !== "0") {
    const subRoot = findNodeByPath(treeNode, searchPathPrefix);
    if (subRoot) {
      const found = searchSubtree(subRoot);
      if (found) return found;
    }
    // 接頭辞スコープが指定されている場合、他コンポーネントの同名要素への誤マッチ（スコープ逸脱）を防ぐためnullを返す
    return null;
  }

  // 2. 木全体からの探索（スコープ未指定時のみ）
  return searchSubtree(treeNode);

  function searchSubtree(node) {
    if (!node) return null;
    if (node.char === elementChar || node.raw_char === elementChar) {
      return node.path;
    }
    if (node.children && node.children.length > 0) {
      for (const child of node.children) {
        const p = searchSubtree(child);
        if (p) return p;
      }
    }
    return null;
  }
}

// =============================================================================
// 5. 左カラム: キャンバス描画 & インタラクティブホバー
// =============================================================================

/**
 * キャンバスおよびツリー要素のロック中表示クラスを同期更新
 */
function updateCanvasLockClasses() {
  const container = document.getElementById("canvasSvgContainer");
  const lockedPath = state.lockedPath;

  if (container) {
    const roots = container.querySelectorAll(".kvg-root");
    roots.forEach(root => {
      root.classList.toggle("has-locked-scope", !!lockedPath);
    });

    container.querySelectorAll(".component-vector-layer").forEach(layer => {
      const lPath = layer.getAttribute("data-path");
      layer.classList.toggle("locked-scope", !!(lockedPath && lPath === lockedPath));
    });

    container.querySelectorAll(".kvg-group:not(.component-vector-layer)[data-path]").forEach(g => {
      const gPath = g.getAttribute("data-path") || "";
      const inScope = !!(lockedPath && (gPath === lockedPath || gPath.startsWith(lockedPath + ".")));
      g.classList.toggle("locked-scope", inScope);
      g.classList.toggle("locked-target", !!(lockedPath && gPath === lockedPath));
    });
  }

  document.querySelectorAll(".tree-node-card").forEach(card => {
    const cPath = card.getAttribute("data-path");
    card.classList.toggle("locked-node", !!(lockedPath && cPath === lockedPath));
  });
}

/**
 * 段階的ロック階層探索コントローラーUIの更新
 */
function updateLockControllerUI() {
  const badge = document.getElementById("depthStatusBadge");
  const btnStepUp = document.getElementById("btnLockStepUp");
  const btnReset = document.getElementById("btnResetLock");
  const trail = document.getElementById("depthLockTrail");

  if (!badge || !trail) return;

  if (!state.lockedPath) {
    badge.textContent = "第1階層(直接構成)";
    badge.className = "depth-status-badge level-1";
    if (btnStepUp) btnStepUp.disabled = true;
    if (btnReset) btnReset.disabled = true;
    trail.innerHTML = '<span class="depth-lock-hint">※ 第1階層の構成部品をクリックで固定・逆引き検索、「選択解除」で解除</span>';
    return;
  }

  const lockedNode = findNodeByPath(state.charData?.tree, state.lockedPath);
  const lockedDepth = state.lockedPath.split(".").length - 1;
  const hasChildren = lockedNode && Array.isArray(lockedNode.children) && lockedNode.children.length > 0;

  if (btnStepUp) btnStepUp.disabled = false;
  if (btnReset) btnReset.disabled = false;

  badge.className = "depth-status-badge is-locked";
  if (hasChildren) {
    const charName = lockedNode.char || lockedNode.raw_char || "部品";
    badge.textContent = `第${lockedDepth + 1}階層(${charName}の内部)`;
  } else {
    const charName = lockedNode?.char || lockedNode?.raw_char || "";
    badge.textContent = `第${lockedDepth}階層(末端部品: ${charName})`;
  }

  // 祖先パンくずリスト描画
  trail.innerHTML = "";
  const parts = state.lockedPath.split(".");
  const ancestorPaths = [];
  for (let i = 2; i <= parts.length; i++) {
    ancestorPaths.push(parts.slice(0, i).join("."));
  }

  ancestorPaths.forEach((p, idx) => {
    if (idx > 0) {
      const sep = document.createElement("span");
      sep.className = "depth-trail-sep";
      sep.textContent = "→";
      trail.appendChild(sep);
    }

    const n = findNodeByPath(state.charData?.tree, p);
    const d = p.split(".").length - 1;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "depth-trail-chip" + (p === state.lockedPath ? " active" : "");
    const chipChar = n?.char || n?.raw_char || n?.role_label || "部品";
    chip.textContent = `第${d}階層: ${chipChar}`;
    chip.title = `第${d}階層「${chipChar}」にスコープを切り替えます`;
    chip.addEventListener("click", () => {
      lockComponentScope(p);
    });
    trail.appendChild(chip);
  });

  // 単体調査ボタン
  if (lockedNode && lockedNode.char && lockedNode.char !== state.currentChar) {
    const btnOpenMain = document.createElement("button");
    btnOpenMain.type = "button";
    btnOpenMain.className = "btn-open-locked-main";
    btnOpenMain.id = "btnOpenLockedMain";
    btnOpenMain.textContent = `「${lockedNode.char}」を単体調査 →`;
    btnOpenMain.title = `「${lockedNode.char}」を主文字として詳細分解します`;
    btnOpenMain.addEventListener("click", () => {
      inspectCharacter(lockedNode.char);
    });
    trail.appendChild(btnOpenMain);
  }
}

/**
 * 指定パスの部品を探索スコープとして固定（ロック）
 */
function lockComponentScope(path) {
  if (!path || path === "0") {
    resetLockedScope();
    return;
  }

  state.lockedPath = path;
  const node = findNodeByPath(state.charData?.tree, path);

  // 右カラム逆引き検索をロック部品に連動
  const targetChar = node ? (node.char || node.raw_char) : null;
  if (targetChar) {
    state.findChips = new Set([targetChar]);
    renderFindChips();
    executeFindSearch();
  }

  applyHitTestDepth();
  updateLockControllerUI();
  clearComponentHover();
}

/**
 * 選択固定を解除して第1階層探索へリセット
 */
function resetLockedScope() {
  state.lockedPath = null;
  state.findChips = new Set([state.currentChar]);
  renderFindChips();
  executeFindSearch();
  applyHitTestDepth();
  updateLockControllerUI();
  clearComponentHover();
}

/**
 * 1つ上の祖先階層へ戻る
 */
function stepLockScopeUp() {
  if (!state.lockedPath) return;
  const parts = state.lockedPath.split(".");
  if (parts.length > 2) {
    parts.pop();
    const parentPath = parts.join(".");
    lockComponentScope(parentPath);
  } else {
    resetLockedScope();
  }
}

/**
 * 段階的ロック階層に基づくヒットテスト適用
 */
function applyHitTestDepth() {
  const container = document.getElementById("canvasSvgContainer");
  if (!container) return;

  const lockedPath = state.lockedPath;
  const lockedNode = lockedPath ? findNodeByPath(state.charData?.tree, lockedPath) : null;
  const hasChildren = lockedNode && Array.isArray(lockedNode.children) && lockedNode.children.length > 0;

  // 1. 明朝体ベクターレイヤー (.component-vector-layer)
  const layers = container.querySelectorAll(".component-vector-layer");
  layers.forEach(layer => {
    const layerPath = layer.getAttribute("data-path") || "";
    const hitboxes = layer.querySelectorAll(".component-layer-hitbox");
    if (hitboxes.length === 0) return;

    let targetPointerEvents = "none";
    if (!lockedPath) {
      // 第1階層部品のみ (root "0" の直接の子: "0.0", "0.1" -> split(".").length === 2)
      const isLevel1 = (layerPath.split(".").length === 2);
      targetPointerEvents = isLevel1 ? "all" : "none";
    } else {
      if (hasChildren) {
        // lockedPath の直接の子要素のみ有効化
        const isDirectChild = layerPath.startsWith(lockedPath + ".") &&
          layerPath.split(".").length === lockedPath.split(".").length + 1;
        targetPointerEvents = isDirectChild ? "all" : "none";
      } else {
        // 末端部品自身のみ有効化（再クリックで単体調査への遷移を可能にする）
        targetPointerEvents = (layerPath === lockedPath) ? "all" : "none";
      }
    }

    hitboxes.forEach(hb => {
      hb.style.pointerEvents = targetPointerEvents;
    });
  });

  // 2. フォールバック用 KanjiVG グループ (.kvg-group[data-path])
  if (layers.length === 0) {
    const kvgGroups = container.querySelectorAll(".kvg-group[data-path]");
    kvgGroups.forEach(g => {
      const gPath = g.getAttribute("data-path") || "";
      if (!lockedPath) {
        let isLevel1 = (gPath.split(".").length === 2);
        if (!isLevel1 && gPath.split(".").length > 2) {
          const l1Path = gPath.split(".").slice(0, 2).join(".");
          const hasL1Ancestor = !!container.querySelector(`.kvg-group[data-path="${l1Path}"]`);
          if (!hasL1Ancestor) {
            isLevel1 = true;
          }
        }
        g.style.pointerEvents = isLevel1 ? "all" : "none";
      } else {
        if (hasChildren) {
          const isDirectChild = gPath.startsWith(lockedPath + ".") &&
            gPath.split(".").length === lockedPath.split(".").length + 1;
          g.style.pointerEvents = isDirectChild ? "all" : "none";
        } else {
          g.style.pointerEvents = (gPath === lockedPath) ? "all" : "none";
        }
      }
    });
  }

  updateCanvasLockClasses();
}

/**
 * キャンバス描画（常に明朝体ベクターSVGをフルサイズ描画）
 */
function renderCanvas() {
  const container = document.getElementById("canvasSvgContainer");
  if (!container || !state.charData) return;
  container.innerHTML = "";

  const visual = state.charData.visual || {};
  const tree = state.charData.tree || {};

  renderSvgInto(container, visual, tree);
  applyHitTestDepth();
}

/**
 * SVG要素の構築（KanjiVG筆画表示を最優先、明朝体・印刷書体を第2モードとして描画）
 */
function renderSvgInto(targetElement, visual, tree) {
  // 1. バックエンドからの構造化 KanjiVG JSON データ処理（筆画単位ベクター表示 - デフォルト）
  if (state.activeDisplayMode !== "mincho" && visual.has_kanjivg && visual.kanjivg && typeof visual.kanjivg === "object") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 109 109");
    svg.classList.add("kvg-root");

    function renderKvgGroup(group, parentTreePath = "") {
      const elem = group.element || group.raw_element || "";
      let treePath = group.path || "";
      if (!treePath) {
        if (!parentTreePath) {
          treePath = "0";
        } else {
          const foundPath = elem ? findTreePathForElement(tree, elem, parentTreePath) : null;
          if (foundPath) {
            treePath = foundPath;
          } else {
            treePath = (parentTreePath !== "0") ? parentTreePath : "";
          }
        }
      }

      // 安全ガード: 子グループのパスが親の木構造スコープ (parentTreePath) を逸脱しないことを保証
      if (
        parentTreePath &&
        parentTreePath !== "0" &&
        treePath &&
        treePath !== parentTreePath &&
        !treePath.startsWith(parentTreePath + ".")
      ) {
        treePath = parentTreePath;
      }

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      if (group.id) g.setAttribute("id", group.id);
      g.setAttribute("class", "kvg-group");
      if (treePath) g.setAttribute("data-path", treePath);
      if (elem) g.setAttribute("data-char", elem);
      if (group.position) g.setAttribute("data-role", group.position);
      if (group.raw_element) g.setAttribute("data-raw", group.raw_element);

      const strokes = group.strokes || [];
      const children = group.children || [];
      const effectivePathForChildren = treePath || parentTreePath;

      // 直下の筆画（strokes）を描画：表示用パスと透明太幅ヒット領域パス
      if (strokes.length > 0) {
        strokes.forEach(stroke => {
          const visiblePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
          if (stroke.id) visiblePath.setAttribute("id", stroke.id);
          visiblePath.setAttribute("class", "kvg-stroke");
          visiblePath.setAttribute("d", stroke.d);
          if (stroke.type) visiblePath.setAttribute("kvg:type", stroke.type);
          g.appendChild(visiblePath);

          const hitPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
          hitPath.setAttribute("class", "kvg-stroke-hit");
          hitPath.setAttribute("d", stroke.d);
          g.appendChild(hitPath);
        });
      }

      // 子グループの再帰描画
      children.forEach(childGroup => {
        g.appendChild(renderKvgGroup(childGroup, effectivePathForChildren));
      });

      if (treePath && (treePath !== "0" || children.length === 0)) {
        attachInteractiveEventsToNode(g, treePath, elem, group.position || "", group.raw_element || "");
      }
      return g;
    }

    svg.appendChild(renderKvgGroup(visual.kanjivg, ""));
    targetElement.appendChild(svg);
    applyHitTestDepth();
    return;
  }

  // 2. 明朝体（印刷書体）インタラクティブベクターSVG
  if (visual.interactive_svg && (visual.interactive_svg.base_path || (visual.interactive_svg.component_layers && visual.interactive_svg.component_layers.length > 0))) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 1024 1024");
    svg.setAttribute("class", "kvg-svg print-style-svg");

    const uid = (targetElement.id ? targetElement.id + "_" : "") + Math.random().toString(36).slice(2, 7);
    const rawLayers = visual.interactive_svg.component_layers || [];
    const layers = rawLayers.filter(l => l && l.path && l.path !== "0");

    // <defs> クリップパス定義
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    layers.forEach(layer => {
      const safePath = String(layer.path).replace(/[^a-zA-Z0-9_-]/g, "_");
      const clipPath = document.createElementNS("http://www.w3.org/2000/svg", "clipPath");
      clipPath.setAttribute("id", `clip-${uid}-${safePath}`);

      const clipRects = (Array.isArray(layer.clip_rects) && layer.clip_rects.length > 0)
        ? layer.clip_rects
        : [layer.bbox || [0, 0, 1, 1]];
      clipRects.forEach(cr => {
        const rx = Math.round(cr[0] * 1024);
        const ry = Math.round(cr[1] * 1024);
        const rw = Math.round(cr[2] * 1024);
        const rh = Math.round(cr[3] * 1024);

        const clipRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        clipRect.setAttribute("x", String(rx));
        clipRect.setAttribute("y", String(ry));
        clipRect.setAttribute("width", String(rw));
        clipRect.setAttribute("height", String(rh));
        clipPath.appendChild(clipRect);
      });

      defs.appendChild(clipPath);
    });
    svg.appendChild(defs);

    const rootG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    rootG.setAttribute("class", "kvg-root");
    rootG.setAttribute("data-path", "0");

    const basePath = visual.interactive_svg.base_path || "";
    // ベース文字全体の明朝体アウトライン（鮮明な単一実線・不透明度1）
    if (basePath) {
      const baseGlyph = document.createElementNS("http://www.w3.org/2000/svg", "path");
      baseGlyph.setAttribute("d", basePath);
      baseGlyph.setAttribute("transform", "translate(0, 880) scale(1, -1)");
      baseGlyph.setAttribute("class", "print-base-glyph");
      rootG.appendChild(baseGlyph);
    }

    // 階層深度昇順ソート（浅い階層ほど先、深い子部品ほどDOM後ろ＝前面に配置されX線ホバーが正確にヒット）
    layers.sort((a, b) => a.path.split(".").length - b.path.split(".").length);

    // 最上位の svg_path 保持層を判定（祖先がすでに svg_path を保持している層を除外）
    const topSvgLayerPaths = new Set();
    layers.forEach(layer => {
      if (!layer.svg_path) return;
      const lPath = layer.path;
      let hasAncestor = false;
      for (const anc of topSvgLayerPaths) {
        if (lPath.startsWith(anc + ".")) {
          hasAncestor = true;
          break;
        }
      }
      if (!hasAncestor) {
        topSvgLayerPaths.add(lPath);
      }
    });

    layers.forEach(layer => {
      const depth = layer.path.split(".").length - 1;
      const safePath = String(layer.path).replace(/[^a-zA-Z0-9_-]/g, "_");
      const bbox = layer.bbox || [0, 0, 1, 1];
      const rx = Math.round(bbox[0] * 1024);
      const ry = Math.round(bbox[1] * 1024);
      const rw = Math.round(bbox[2] * 1024);
      const rh = Math.round(bbox[3] * 1024);

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "component-vector-layer kvg-group");
      g.setAttribute("data-path", layer.path);
      g.setAttribute("data-char", escapeAttr(layer.char || ""));
      g.setAttribute("data-depth", String(depth));
      if (layer.role_label) g.setAttribute("data-role", escapeAttr(layer.role_label));
      if (layer.raw_char) g.setAttribute("data-raw", escapeAttr(layer.raw_char));

      if (basePath) {
        // base_path あり：クリップされた明朝体スライスのみ描画（ホバー時に朱色で発色）
        // 重要: clip-pathをtransformを持つ要素自体にかけるとフォントローカル座標系（上下反転）で評価されてしまうため、
        // 画面座標系 (0..1024) を維持する親 <g> に clip-path を指定し、さらにその外側のラッパーに drop-shadow を適用して光彩の直線切断を防ぐ
        const glowWrapper = document.createElementNS("http://www.w3.org/2000/svg", "g");
        glowWrapper.setAttribute("class", "print-component-glow-wrapper");

        const sliceGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
        const shouldClip = (layer.needs_clip !== false) || !layer.slice_path || (layer.slice_path === basePath);
        if (shouldClip) {
          sliceGroup.setAttribute("clip-path", `url(#clip-${uid}-${safePath})`);
        }
        sliceGroup.setAttribute("class", "print-component-slice-group");

        const slice = document.createElementNS("http://www.w3.org/2000/svg", "path");
        const slicePath = layer.slice_path || basePath;
        slice.setAttribute("d", slicePath);
        slice.setAttribute("transform", "translate(0, 880) scale(1, -1)");
        slice.setAttribute("class", "print-component-slice");

        sliceGroup.appendChild(slice);
        glowWrapper.appendChild(sliceGroup);
        g.appendChild(glowWrapper);
      } else if (layer.svg_path) {
        // base_path なし：最上位のベクター保持層は常時表示、深層はホバー時のみ朱色発色
        const isTop = topSvgLayerPaths.has(layer.path);
        const fallback = document.createElementNS("http://www.w3.org/2000/svg", "path");
        fallback.setAttribute("d", layer.svg_path);
        if (layer.svg_transform) {
          fallback.setAttribute("transform", layer.svg_transform);
        }
        if (isTop) {
          fallback.setAttribute("class", "print-component-fallback");
        } else {
          fallback.setAttribute("class", "print-component-slice-fallback");
        }
        g.appendChild(fallback);
      }

      // インタラクティブヒットボックス & ホバー枠（分割ヒット領域 hit_rects 対応）
      const hitRects = (layer.hit_rects && Array.isArray(layer.hit_rects) && layer.hit_rects.length > 0)
        ? layer.hit_rects
        : [bbox];

      hitRects.forEach(hr => {
        const hrx = Math.round(hr[0] * 1024);
        const hry = Math.round(hr[1] * 1024);
        const hrw = Math.round(hr[2] * 1024);
        const hrh = Math.round(hr[3] * 1024);

        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", String(hrx));
        rect.setAttribute("y", String(hry));
        rect.setAttribute("width", String(hrw));
        rect.setAttribute("height", String(hrh));
        rect.setAttribute("rx", "10");
        rect.setAttribute("ry", "10");
        rect.setAttribute("class", "component-layer-hitbox");
        g.appendChild(rect);
      });

      attachInteractiveEventsToNode(g, layer.path, layer.char || "", layer.role_label || "", layer.raw_char || "");
      rootG.appendChild(g);
    });

    if (!basePath && topSvgLayerPaths.size === 0) {
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      const isMulti = Array.from(state.currentChar || "").length > 1;
      text.setAttribute("x", "512");
      text.setAttribute("y", isMulti ? "512" : "720");
      text.setAttribute("font-size", isMulti ? "110" : "700");
      if (isMulti) {
        text.setAttribute("dominant-baseline", "central");
      }
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("fill", "currentColor");
      text.style.fontFamily = "var(--font-kanji)";
      text.textContent = state.currentChar;
      rootG.appendChild(text);
    }

    svg.appendChild(rootG);
    targetElement.appendChild(svg);
    applyHitTestDepth();
    return;
  }

  // 3. 静的SVG文字列フォールバック（デモプリセット等）
  if (visual.has_kanjivg && visual.kanjivg_svg && typeof visual.kanjivg_svg === "string") {
    const parser = new DOMParser();
    const doc = parser.parseFromString(visual.kanjivg_svg, "image/svg+xml");
    const svgElem = doc.querySelector("svg");
    if (svgElem) {
      svgElem.removeAttribute("width");
      svgElem.removeAttribute("height");
      attachSvgInteractiveEvents(svgElem);
      targetElement.appendChild(svgElem);
      return;
    }
  }

  // 4. フォールバック（文字テキスト描画）
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 1024 1024");
  svg.classList.add("kvg-root");
  const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
  const isMulti = Array.from(state.currentChar || "").length > 1;
  text.setAttribute("x", "512");
  text.setAttribute("y", isMulti ? "512" : "720");
  text.setAttribute("font-size", isMulti ? "110" : "700");
  if (isMulti) {
    text.setAttribute("dominant-baseline", "central");
  }
  text.setAttribute("text-anchor", "middle");
  text.setAttribute("fill", "currentColor");
  text.style.fontFamily = "var(--font-kanji)";
  text.textContent = state.currentChar;
  svg.appendChild(text);
  targetElement.appendChild(svg);
}

/**
 * KanjiVG SVG 内の要素へイベントリスナーを付与
 */
function attachSvgInteractiveEvents(svgElem) {
  const groups = svgElem.querySelectorAll("g[id^='kvg:']");
  groups.forEach(g => {
    g.classList.add("kvg-group");
    const path = g.getAttribute("data-path") || "0";
    const element = g.getAttribute("kvg:element") || "";
    const original = g.getAttribute("kvg:original") || "";
    if (path && (path !== "0" || g.querySelectorAll("g[id^='kvg:']").length === 0)) {
      attachInteractiveEventsToNode(g, path, element, "", original);
    }
  });
}

/**
 * キャンバス部品クリック時の段階的ロック制御
 */
function handleComponentClick(path, char, role = "", raw_char = "") {
  if (!path || path === "0") return;

  const node = findNodeByPath(state.charData?.tree, path);

  // すでにロック済みの末端部品を再度クリックした場合: 単体調査へドリルダウン
  if (state.lockedPath === path) {
    const targetChar = char || node?.char || "";
    if (targetChar && targetChar !== state.currentChar) {
      inspectCharacter(targetChar);
    }
    return;
  }

  // 部品を固定（ロック）
  lockComponentScope(path);
}

/**
 * ノードへのホバーおよびクリックイベントの紐付け（mouseover による入れ子要素の確実な捕捉）
 */
function attachInteractiveEventsToNode(domNode, path, char, role = "", raw_char = "") {
  domNode.addEventListener("mouseover", (e) => {
    e.stopPropagation();
    let effectivePath = path;
    let effectiveChar = char;
    let effectiveRole = role;
    let effectiveRaw = raw_char;
    if (!state.lockedPath) {
      const parts = path.split(".");
      if (parts.length > 2) {
        const l1Path = parts.slice(0, 2).join(".");
        const hasL1Ancestor = !!domNode.closest ? !!domNode.closest(`.kvg-group[data-path="${l1Path}"]`) : false;
        if (!hasL1Ancestor) {
          effectivePath = l1Path;
          const l1Node = findNodeByPath(state.charData?.tree, l1Path);
          if (l1Node) {
            effectiveChar = l1Node.char || "";
            effectiveRole = l1Node.role_label || "";
            effectiveRaw = l1Node.raw_char || "";
          }
        }
      }
    }
    handleComponentHover(effectivePath, effectiveChar, effectiveRole, effectiveRaw);
  });

  domNode.addEventListener("mouseout", (e) => {
    if (e.relatedTarget && domNode.contains(e.relatedTarget)) {
      return;
    }
    const nextTarget = e.relatedTarget?.closest ? e.relatedTarget.closest("[data-path]") : null;
    const nextPath = nextTarget ? nextTarget.getAttribute("data-path") : null;
    if (!nextPath || nextPath === "0") {
      clearComponentHover();
    }
  });

  domNode.addEventListener("click", (e) => {
    e.stopPropagation();
    let effectivePath = path;
    let effectiveChar = char;
    let effectiveRole = role;
    let effectiveRaw = raw_char;
    if (!state.lockedPath) {
      const parts = path.split(".");
      if (parts.length > 2) {
        const l1Path = parts.slice(0, 2).join(".");
        const hasL1Ancestor = !!domNode.closest ? !!domNode.closest(`.kvg-group[data-path="${l1Path}"]`) : false;
        if (!hasL1Ancestor) {
          effectivePath = l1Path;
          const l1Node = findNodeByPath(state.charData?.tree, l1Path);
          if (l1Node) {
            effectiveChar = l1Node.char || "";
            effectiveRole = l1Node.role_label || "";
            effectiveRaw = l1Node.raw_char || "";
          }
        }
      }
    }
    handleComponentClick(effectivePath, effectiveChar, effectiveRole, effectiveRaw);
  });

  // マウスホイールによる階層深度切り替え
  domNode.addEventListener("wheel", (e) => {
    e.preventDefault();
    e.stopPropagation();
    handleWheelHierarchy(e.deltaY);
  }, { passive: false });
}

/**
 * ホバー時の詳細更新および双方向連動ハイライト
 */
function handleComponentHover(path, charOrEntering = "", role = "", raw_char = "") {
  if (charOrEntering === false) {
    clearComponentHover();
    return;
  }

  let targetPath = path || "0";
  let targetChar = typeof charOrEntering === "string" ? charOrEntering : "";
  let targetRole = role || "";
  let targetRaw = raw_char || "";

  state.hoveredPath = targetPath;

  // 対象ノードの詳細メタデータサマリー取得
  const activeNode = findNodeByPath(state.charData?.tree, targetPath);
  if (activeNode) {
    targetChar = targetChar || activeNode.char || "";
    targetRole = targetRole || activeNode.role_label || "";
    targetRaw = targetRaw || activeNode.raw_char || "";
  }
  const metaSummary = activeNode?.meta_summary || null;

  // 1. キャンバス内要素のハイライト
  document.querySelectorAll("[data-path]").forEach(el => {
    const elPath = el.getAttribute("data-path");
    if (!elPath || !targetPath || targetPath === "0") {
      el.classList.remove("hovered", "dimmed");
      return;
    }

    if (el.classList.contains("spatial-box")) {
      // 親の矩形領域が子要素全域を包含するため、完全一致時のみ hovered
      if (elPath === targetPath) {
        el.classList.add("hovered");
        el.classList.remove("dimmed");
      } else {
        el.classList.remove("hovered");
        el.classList.add("dimmed");
      }
    } else if (el.classList.contains("component-vector-layer")) {
      // 印刷書体スライス・破線枠は完全一致時のみ hovered（重複枠線の防止）
      if (elPath === targetPath) {
        el.classList.add("hovered");
      } else {
        el.classList.remove("hovered");
      }
    } else if (el.classList.contains("kvg-group")) {
      if (elPath === targetPath || elPath.startsWith(targetPath + ".")) {
        el.classList.add("hovered");
      } else {
        el.classList.remove("hovered");
      }
    } else if (el.classList.contains("tree-node") || el.classList.contains("tree-node-card")) {
      // ツリーノードは後述の処理で対応
    } else {
      if (elPath === targetPath) {
        el.classList.add("hovered");
      } else {
        el.classList.remove("hovered");
      }
    }
  });

  document.querySelectorAll(".kvg-root").forEach(svg => {
    if (targetPath && targetPath !== "0") {
      svg.classList.add("has-hovered-child");
    } else {
      svg.classList.remove("has-hovered-child");
    }
  });

  // 1.5 KanjiVG筆画レイヤー（layer_strokes）直接同期
  const layerStrokesMap = state.charData?.visual?.layer_strokes || state.charData?.visual?.kanjivg?.layer_strokes;
  if (layerStrokesMap) {
    const activeStrokes = new Set(layerStrokesMap[targetPath] || []);
    document.querySelectorAll(".kvg-stroke").forEach(strokeEl => {
      const sid = strokeEl.getAttribute("id");
      if (sid && activeStrokes.has(sid)) {
        strokeEl.classList.add("active-stroke");
      } else {
        strokeEl.classList.remove("active-stroke");
      }
    });
  }

  // 2. 中央ツリービューの双方向連動ハイライト & 自動スクロール
  document.querySelectorAll(".tree-node, .tree-node-card").forEach(nodeEl => {
    const nodePath = nodeEl.getAttribute("data-path");
    if (!nodePath || !targetPath || targetPath === "0") {
      nodeEl.classList.remove("hovered", "pulse", "hovered-descendant");
      return;
    }
    if (nodePath === targetPath) {
      nodeEl.classList.add("hovered", "pulse");
      nodeEl.classList.remove("hovered-descendant");

      // 親の .column-content のみスクロール（祖先コンテナやウィンドウの意図しないスクロールを完全防止）
      const scrollParent = nodeEl.closest(".column-content");
      if (scrollParent) {
        const parentRect = scrollParent.getBoundingClientRect();
        const nodeRect = nodeEl.getBoundingClientRect();
        if (nodeRect.top < parentRect.top) {
          scrollParent.scrollTop -= (parentRect.top - nodeRect.top) + 8;
        } else if (nodeRect.bottom > parentRect.bottom) {
          scrollParent.scrollTop += (nodeRect.bottom - parentRect.bottom) + 8;
        }
      }
    } else if (nodePath.startsWith(targetPath + ".")) {
      nodeEl.classList.add("hovered-descendant");
      nodeEl.classList.remove("hovered", "pulse");
    } else {
      nodeEl.classList.remove("hovered", "pulse", "hovered-descendant");
    }
  });

  // 3. HUD更新
  updateHud(targetChar || "—", targetPath, targetRole, targetRaw, metaSummary);
}

function clearComponentHover() {
  state.hoveredPath = null;
  document.querySelectorAll("[data-path]").forEach(el => el.classList.remove("hovered", "dimmed"));
  document.querySelectorAll(".kvg-root").forEach(svg => svg.classList.remove("has-hovered-child"));
  document.querySelectorAll(".kvg-stroke").forEach(el => el.classList.remove("active-stroke"));
  document.querySelectorAll(".tree-node, .tree-node-card").forEach(el => el.classList.remove("hovered", "pulse", "hovered-descendant"));

  updateCanvasLockClasses();
  resetHud();
}

/**
 * マウスホイールによる階層切り替え
 */
function handleWheelHierarchy(deltaY) {
  if (!state.hoveredPath) return;
  const parts = state.hoveredPath.split(".");
  let newPath = state.hoveredPath;

  if (deltaY > 0) {
    // 浅い階層へ
    if (parts.length > 1) {
      parts.pop();
      newPath = parts.join(".");
    }
  } else {
    // 深い階層へ
    const currNode = findNodeByPath(state.charData?.tree, state.hoveredPath);
    if (currNode && currNode.children && currNode.children.length > 0) {
      newPath = currNode.children[0].path;
    }
  }

  if (newPath !== state.hoveredPath) {
    const node = findNodeByPath(state.charData?.tree, newPath);
    if (node) {
      handleComponentHover(newPath, node.char, node.role_label, node.raw_char);
    }
  }
}

/**
 * リアルタイムHUDの表示更新
 */
function updateHud(char, path, role, raw_char, metaSummary = null) {
  const hud = document.getElementById("hoverHud");
  const glyphBox = document.getElementById("hudGlyphBox");
  const charName = document.getElementById("hudCharName");
  const codepoint = document.getElementById("hudCodepoint");
  const rawOrig = document.getElementById("hudRawOrig");
  const trail = document.getElementById("hudTrail");

  if (!hud || !glyphBox) return;

  hud.classList.add("active");
  glyphBox.innerHTML = renderGlyphHTML(char);
  glyphBox.style.opacity = "1";
  charName.textContent = char;
  codepoint.textContent = getCodepointHex(char);
  rawOrig.textContent = raw_char ? `(原表記: ${raw_char})` : "";

  let extra = "";
  if (metaSummary) {
    const parts = [];
    if (metaSummary.stroke_count) parts.push(`${metaSummary.stroke_count}画`);
    if (metaSummary.ja_on && metaSummary.ja_on.length > 0) parts.push(`音: ${metaSummary.ja_on.join("・")}`);
    if (metaSummary.ja_kun && metaSummary.ja_kun.length > 0) parts.push(`訓: ${metaSummary.ja_kun.join("・")}`);
    if (parts.length > 0) extra = ` | ${parts.join(" | ")}`;
  }

  trail.textContent = `階層パス: ${path}${role ? ` [役割: ${role}]` : ""}${extra}`;
}

function resetHud() {
  const hud = document.getElementById("hoverHud");
  const glyphBox = document.getElementById("hudGlyphBox");
  const charName = document.getElementById("hudCharName");
  const codepoint = document.getElementById("hudCodepoint");
  const rawOrig = document.getElementById("hudRawOrig");
  const trail = document.getElementById("hudTrail");
  const hint = document.getElementById("hudHint");

  if (!hud || !glyphBox) return;

  if (state.lockedPath) {
    const lockedNode = findNodeByPath(state.charData?.tree, state.lockedPath);
    if (lockedNode) {
      const lockedDepth = state.lockedPath.split(".").length - 1;
      const hasChildren = Array.isArray(lockedNode.children) && lockedNode.children.length > 0;
      const isComposite = !lockedNode.char && !lockedNode.raw_char;
      const dispChar = lockedNode.char || lockedNode.raw_char || (lockedNode.role_label ? `[${lockedNode.role_label}]` : "複合部品");

      hud.classList.add("active");
      glyphBox.innerHTML = renderGlyphHTML(dispChar);
      glyphBox.style.opacity = "1";
      charName.textContent = `[固定] ${dispChar}`;
      codepoint.textContent = isComposite ? "(複合要素)" : getCodepointHex(dispChar);
      rawOrig.textContent = lockedNode.raw_char ? `(原表記: ${lockedNode.raw_char})` : "";

      if (hasChildren) {
        trail.textContent = `階層パス: ${state.lockedPath} [役割: ${lockedNode.role_label || "固定部品"}] | 内部の第${lockedDepth + 1}階層部品を探索中`;
        if (hint) {
          hint.textContent = `[固定中: ${dispChar}] 内部の第${lockedDepth + 1}階層部品をホバーで確認(クリックでさらに固定 / 「選択解除」で解除)`;
        }
      } else {
        trail.textContent = `階層パス: ${state.lockedPath} [役割: ${lockedNode.role_label || "末端部品"}] | 末端部品固定中`;
        if (hint) {
          hint.textContent = `クリックで「${dispChar}」を単体調査 ／ 選択解除で復帰`;
        }
      }
      return;
    }
  }

  // デフォルト状態（未固定時）
  hud.classList.remove("active");
  const cur = state.currentChar || "蛍";
  glyphBox.innerHTML = renderGlyphHTML(cur);
  glyphBox.style.opacity = "0.75";
  charName.textContent = `${cur}(全体)`;
  codepoint.textContent = getCodepointHex(cur);
  rawOrig.textContent = "";
  trail.textContent = "階層パス: 0 [役割: 全体]";
  if (hint) {
    hint.textContent = "※ 部品ホバーで字形確認 / クリックで選択・逆引き検索";
  }
}

/**
 * 漢字属性・字書情報カードのレンダリング
 */
function renderAttributeCard() {
  const meta = state.charData?.meta;
  if (!meta) return;

  const char = meta.char || meta.literal || state.currentChar;
  const cpHex = meta.codepoint || getCodepointHex(char);

  document.getElementById("attrCharCodepoint").textContent = cpHex;
  document.getElementById("attrCodepoint").textContent = cpHex;

  const tierBadge = document.getElementById("attrTierBadge");
  tierBadge.textContent = meta.tier || "通常漢字";

  // 部首情報の成形（辞書オブジェクトまたは文字列フォールバック）
  let radText = "—";
  if (meta.radical) {
    if (typeof meta.radical === "object") {
      const rName = meta.radical.name || meta.radical.char || "";
      const rNum = meta.radical.num ? ` [第${meta.radical.num}部]` : "";
      const rChar = meta.radical.char ? `${meta.radical.char}(${rName})` : rName;
      radText = rChar ? `${rChar}${rNum}` : (meta.radical.num ? `第${meta.radical.num}部` : "—");
    } else if (typeof meta.radical === "string") {
      radText = meta.radical;
    }
  }

  const strokeCountText = meta.stroke_count ? `${meta.stroke_count}画` : "画数未詳";
  document.getElementById("attrStrokesRadical").textContent = `${strokeCountText} ／ ${radText}`;

  // 読み（音・訓）
  const onReadings = (Array.isArray(meta.ja_on) && meta.ja_on.length > 0)
    ? meta.ja_on
    : (meta.on_readings || []);
  document.getElementById("attrOnReadings").textContent =
    onReadings.length > 0 ? onReadings.join("、") : "—";

  const kunReadings = (Array.isArray(meta.ja_kun) && meta.ja_kun.length > 0)
    ? meta.ja_kun
    : (meta.kun_readings || []);
  document.getElementById("attrKunReadings").textContent =
    kunReadings.length > 0 ? kunReadings.join("、") : "—";

  // バッジ一覧
  const badgesContainer = document.getElementById("attrBadges");
  badgesContainer.innerHTML = "";
  (meta.badges || []).forEach(b => {
    const span = document.createElement("span");
    span.className = "badge badge-grade";
    span.textContent = b;
    badgesContainer.appendChild(span);
  });

  // 辞書コード
  const daikanwa = meta.daikanwa || "—";
  const fourCorner = meta.four_corner || "—";
  const skip = meta.skip_code || meta.skip || "—";
  const cangjie = meta.cangjie || "—";
  const mojijoho = meta.moji_joho || meta.mojijoho || "—";
  document.getElementById("attrDictCodes").textContent =
    `大漢和: ${daikanwa} | 四角号碼: ${fourCorner} | SKIP: ${skip} | 倉頡: ${cangjie} | MJ文字: ${mojijoho}`;

  // 同等部品・異体字（文字列配列およびオブジェクト配列両対応）
  const equivList = document.getElementById("attrEquivalents");
  equivList.innerHTML = "";
  const equivalents = meta.equivalents || [];
  if (equivalents.length > 0) {
    equivalents.forEach(eq => {
      const chip = document.createElement("button");
      chip.className = "equiv-chip";
      let eqChar = "";
      let eqLabel = "";
      if (typeof eq === "string") {
        eqChar = eq;
        eqLabel = getCodepointHex(eq);
      } else if (typeof eq === "object" && eq) {
        eqChar = eq.char || "";
        eqLabel = eq.label || eq.codepoint || getCodepointHex(eqChar);
      }
      if (eqChar) {
        chip.innerHTML = `${renderGlyphHTML(eqChar)} <span style="font-size:0.68rem;opacity:0.75;">(${eqLabel})</span>`;
        chip.addEventListener("click", () => inspectCharacter(eqChar));
        equivList.appendChild(chip);
      }
    });
  }
  if (equivList.children.length === 0) {
    equivList.innerHTML = `<span style="font-size:0.75rem;color:var(--text-muted);">特になし</span>`;
  }
}

// =============================================================================
// 6. 中央カラム: 構造分解ツリー & IDSシーケンス
// =============================================================================

function renderStructureSelector() {
  const container = document.getElementById("structureSelector");
  if (!container || !state.charData) return;
  container.innerHTML = "";

  const alts = state.charData.alternatives || [];
  alts.forEach((alt, idx) => {
    const btn = document.createElement("button");
    btn.className = `struct-btn ${idx === state.activeStructureIndex ? "active" : ""}`;
    const label = alt.label || alt.source || alt.id || "構造";
    btn.textContent = `${label}: ${alt.ids}`;
    btn.addEventListener("click", () => {
      state.activeStructureIndex = idx;
      inspectCharacter(state.currentChar, false, alt.ids);
    });
    container.appendChild(btn);
  });
}

function renderIdsTokens() {
  const container = document.getElementById("idsTokensContainer");
  if (!container || !state.charData) return;
  container.innerHTML = "";

  const alts = state.charData.alternatives || [];
  const alt = alts[state.activeStructureIndex] || alts[0] || { ids: state.currentChar };
  const idsStr = alt.ids || state.currentChar;

  // サロゲートペア（拡張漢字）およびCHISE実体参照を安全にトークン化
  const tokens = idsStr.match(/&[^;\s]+;|[\s\S]/gu) || [];

  tokens.forEach(tok => {
    const chip = document.createElement("span");
    chip.className = "ids-token-chip";
    if (tok in IDC_OPERATORS) {
      chip.classList.add("operator");
      chip.title = IDC_OPERATORS[tok].name;
      chip.textContent = tok;
    } else {
      chip.innerHTML = renderGlyphHTML(tok);
      chip.addEventListener("click", () => {
        inspectCharacter(tok);
      });
    }
    container.appendChild(chip);
  });
}

/**
 * 再帰的分解ツリーの描画
 */
function renderRecursiveTree() {
  const container = document.getElementById("treeContainer");
  if (!container || !state.charData) return;
  container.innerHTML = "";

  const tree = state.charData.tree;
  if (!tree) return;

  function buildNodeDOM(node, depth = 0) {
    const wrapper = document.createElement("div");
    wrapper.className = "tree-node-wrapper";

    const card = document.createElement("div");
    card.className = "tree-node-card";
    card.setAttribute("data-path", node.path || "0");

    // 左側: 役割バッジ、グリフ表示、文字名、コードポイント
    const left = document.createElement("div");
    left.className = "tree-node-left";

    const roleBadge = document.createElement("span");
    roleBadge.className = "tree-role-badge";
    roleBadge.textContent = node.role_label ? `[${node.role_label}]` : `[第${depth}階層]`;
    left.appendChild(roleBadge);

    const glyphBox = document.createElement("div");
    glyphBox.className = "tree-glyph-box";
    glyphBox.innerHTML = renderGlyphHTML(node.char || node.op);
    left.appendChild(glyphBox);

    const meta = document.createElement("div");
    meta.className = "tree-node-meta";

    const nameRow = document.createElement("div");
    nameRow.className = "tree-node-name-row";

    const charName = document.createElement("span");
    charName.className = "tree-node-char";
    charName.textContent = node.char || node.op;
    nameRow.appendChild(charName);

    if (node.op && node.op in IDC_OPERATORS) {
      const opBadge = document.createElement("span");
      opBadge.className = "badge badge-tier-basic";
      opBadge.textContent = `${node.op} ${IDC_OPERATORS[node.op].short}`;
      nameRow.appendChild(opBadge);
    }

    if (node.tier) {
      const tierBadge = document.createElement("span");
      tierBadge.className = "badge badge-tier-ext";
      tierBadge.textContent = node.tier;
      nameRow.appendChild(tierBadge);
    }

    // 画数サマリー（meta_summary 由来）
    if (node.meta_summary?.stroke_count) {
      const strokeBadge = document.createElement("span");
      strokeBadge.className = "badge";
      strokeBadge.style.background = "var(--bg-tertiary)";
      strokeBadge.textContent = `${node.meta_summary.stroke_count}画`;
      nameRow.appendChild(strokeBadge);
    }

    // 読み情報（meta_summary 由来）
    const reads = [...(node.meta_summary?.ja_on || []), ...(node.meta_summary?.ja_kun || [])];
    if (reads.length > 0) {
      const readSpan = document.createElement("span");
      readSpan.className = "tree-node-readings";
      readSpan.style.fontSize = "0.72rem";
      readSpan.style.color = "var(--text-muted)";
      readSpan.textContent = reads.slice(0, 3).join("、");
      nameRow.appendChild(readSpan);
    }

    meta.appendChild(nameRow);

    const sub = document.createElement("span");
    sub.className = "tree-node-sub";
    const rawInfo = node.raw_char ? ` (原表記: ${node.raw_char})` : "";
    const bboxFormatted = (node.bbox || []).map(v => typeof v === "number" ? v.toFixed(2) : v).join(", ");
    sub.textContent = `${getCodepointHex(node.char || "")}${rawInfo} | 領域: [${bboxFormatted}]`;
    meta.appendChild(sub);

    left.appendChild(meta);
    card.appendChild(left);

    // 右側: ドリルダウン & 逆引き追加アクションボタン
    const right = document.createElement("div");
    right.className = "tree-node-right";

    if (node.char && node.char !== state.currentChar) {
      const btnInspect = document.createElement("button");
      btnInspect.className = "btn-tree-action";
      btnInspect.innerHTML = "詳細";
      btnInspect.title = `「${node.char}」を主文字として詳細分解します`;
      btnInspect.addEventListener("click", (e) => {
        e.stopPropagation();
        inspectCharacter(node.char);
      });
      right.appendChild(btnInspect);

      const btnAddFind = document.createElement("button");
      btnAddFind.className = "btn-tree-action add-find";
      btnAddFind.innerHTML = "＋逆引き";
      btnAddFind.title = `「${node.char}」を逆引き検索条件に追加します`;
      btnAddFind.addEventListener("click", (e) => {
        e.stopPropagation();
        addFindChip(node.char);
      });
      right.appendChild(btnAddFind);
    }

    if (state.lockedPath && node.path === state.lockedPath) {
      card.classList.add("locked-node");
    }

    card.appendChild(right);

    // クリックによる段階的ロック連動
    card.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      e.stopPropagation();
      handleComponentClick(node.path, node.char, node.role_label, node.raw_char);
    });

    // 双方向ホバーイベント紐付け
    card.addEventListener("mouseenter", () => {
      handleComponentHover(node.path, node.char, node.role_label, node.raw_char);
    });
    card.addEventListener("mouseleave", () => {
      clearComponentHover();
    });

    wrapper.appendChild(card);

    // 子要素の再帰展開
    if (node.children && node.children.length > 0) {
      const childrenCont = document.createElement("div");
      childrenCont.className = "tree-children";
      node.children.forEach(child => {
        childrenCont.appendChild(buildNodeDOM(child, depth + 1));
      });
      wrapper.appendChild(childrenCont);
    }

    return wrapper;
  }

  container.appendChild(buildNodeDOM(tree, 0));
}

// =============================================================================
// 7. 右カラム: 包含漢字・逆引き探索（ids-find）
// =============================================================================

function addFindChip(char) {
  if (!char) return;
  state.findChips.add(char);
  renderFindChips();
  executeFindSearch();
}

function removeFindChip(char) {
  state.findChips.delete(char);
  renderFindChips();
  executeFindSearch();
}

function clearFindChips() {
  state.findChips.clear();
  renderFindChips();
  executeFindSearch();
}

function renderFindChips() {
  const container = document.getElementById("findChipsContainer");
  const input = document.getElementById("findComponentInput");
  if (!container || !input) return;

  // 既存のチップを削除（input以外）
  const oldChips = container.querySelectorAll(".component-chip");
  oldChips.forEach(c => c.remove());

  state.findChips.forEach(char => {
    const chip = document.createElement("span");
    chip.className = "component-chip";
    chip.innerHTML = `${renderGlyphHTML(char)} <button class="chip-remove-btn" title="条件から削除">×</button>`;
    chip.querySelector(".chip-remove-btn").addEventListener("click", () => removeFindChip(char));
    container.insertBefore(chip, input);
  });
}

/**
 * 逆引き検索の実行（CHISE ids-find）
 */
async function executeFindSearch() {
  const resultsGrid = document.getElementById("resultsGrid");
  if (!resultsGrid) return;

  const chipsArray = Array.from(state.findChips);
  if (chipsArray.length === 0) {
    resultsGrid.innerHTML = `
      <div class="state-message">
        <p>検索したい部品を追加してください。</p>
        <p style="font-size:0.75rem;">例: 「𭕄」や「虫」を追加すると包含する漢字が一覧表示されます。</p>
      </div>
    `;
    updateResultsSummary(0, 0, 0);
    return;
  }

  // フィルタ設定取得
  const hierarchyFilter = document.getElementById("filterHierarchy")?.value || "all";
  const categoryFilter = document.getElementById("filterCategory")?.value || "all";
  const minStroke = parseInt(document.getElementById("filterStrokeMin")?.value, 10) || 0;
  const maxStroke = parseInt(document.getElementById("filterStrokeMax")?.value, 10) || 999;

  let results = [];
  let totalCount = 0;
  let directCount = 0;
  let indirectCount = 0;

  try {
    const params = new URLSearchParams();
    params.set("components", chipsArray.join(" "));
    // サーバー側は "transitive" で間接検索を処理
    params.set("mode", hierarchyFilter === "indirect" ? "transitive" : hierarchyFilter);
    params.set("tier", categoryFilter);
    if (minStroke > 0) params.set("min_strokes", String(minStroke));
    if (maxStroke < 999) params.set("max_strokes", String(maxStroke));

    const res = await fetch(`/api/ids-find?${params.toString()}`);
    if (res.ok) {
      const data = await res.json();
      results = data.results || [];
      totalCount = data.total !== undefined ? data.total : results.length;

      if (data.direct_total !== undefined && data.indirect_total !== undefined) {
        directCount = data.direct_total;
        indirectCount = data.indirect_total;
      } else {
        directCount = results.filter(r =>
          r.is_direct === 1 || r.is_direct === true || chipsArray.some(c => (r.chise_ids || r.ids || "").includes(c))
        ).length;
        indirectCount = Math.max(0, totalCount - directCount);
      }
    }
  } catch (e) {
    console.warn("逆引きAPI通信待機中(ローカルフォールバック実行):", e);
    results = DEMO_FIND_DATABASE.filter(item => {
      // 全部品一致（AND検索）
      const matchesAll = chipsArray.every(c => item.components.includes(c));
      if (!matchesAll) return false;

      if (hierarchyFilter === "direct" && item.is_direct !== 1) return false;
      if (hierarchyFilter === "indirect" && item.is_direct !== 0) return false;
      if (minStroke > 0 && item.stroke_count < minStroke) return false;
      if (maxStroke < 999 && item.stroke_count > maxStroke) return false;

      return true;
    });
    totalCount = results.length;
    directCount = results.filter(r => r.is_direct === 1).length;
    indirectCount = results.filter(r => r.is_direct === 0).length;
  }

  updateResultsSummary(totalCount, directCount, indirectCount);
  renderFindResults(results, chipsArray);
}

/**
 * 逆引き検索結果の描画
 */
function renderFindResults(results, activeKeywords = []) {
  const resultsGrid = document.getElementById("resultsGrid");
  if (!resultsGrid) return;
  resultsGrid.innerHTML = "";

  if (results.length === 0) {
    resultsGrid.innerHTML = `
      <div class="state-message">
        <p>該当する包含漢字が見つかりませんでした。</p>
        <p style="font-size:0.75rem;">フィルタ条件を緩和するか、キャンバスやツリーの部品をクリックして検索してください。</p>
      </div>
    `;
    return;
  }

  results.forEach(res => {
    const card = document.createElement("div");
    card.className = "result-card";

    const char = res.char || res.literal || "";
    const codepoint = res.codepoint || getCodepointHex(char);
    const tier = res.tier || "通常漢字";
    const strokeText = res.stroke_count ? `${res.stroke_count}画` : "画数未詳";
    const idsStr = res.chise_ids || res.ids || "";
    const viaChar = res.via_char || res.via || "";

    const isDirect = (res.is_direct !== undefined)
      ? (res.is_direct === 1 || res.is_direct === true)
      : (activeKeywords.length === 0 || activeKeywords.some(kw => idsStr.includes(kw)));

    // 左側: グリフ、情報、バッジ、IDS表示
    const left = document.createElement("div");
    left.className = "result-card-left";

    const glyphBox = document.createElement("div");
    glyphBox.className = "result-glyph-box";
    glyphBox.innerHTML = renderGlyphHTML(char);
    left.appendChild(glyphBox);

    const info = document.createElement("div");
    info.className = "result-info";

    const header = document.createElement("div");
    header.className = "result-header-row";

    const title = document.createElement("span");
    title.className = "result-char-title";
    title.textContent = char;
    header.appendChild(title);

    const cp = document.createElement("span");
    cp.className = "result-codepoint";
    cp.textContent = codepoint;
    header.appendChild(cp);

    info.appendChild(header);

    // バッジ行
    const badgesRow = document.createElement("div");
    badgesRow.className = "result-badges-row";

    // 頻度バッジ
    if (res.freq !== undefined && res.freq !== null && res.freq > 0) {
      const freqBadge = document.createElement("span");
      freqBadge.className = "badge badge-freq";
      freqBadge.textContent = `頻度 #${res.freq}`;
      badgesRow.appendChild(freqBadge);
    }

    // 学年・常用バッジ
    if (res.grade !== undefined && res.grade !== null && res.grade > 0) {
      const gradeBadge = document.createElement("span");
      gradeBadge.className = "badge badge-grade";
      if (res.grade >= 1 && res.grade <= 6) {
        gradeBadge.textContent = `小学${res.grade}年`;
      } else if (res.grade === 8) {
        gradeBadge.textContent = "常用漢字";
      } else if (res.grade === 9 || res.grade === 10) {
        gradeBadge.textContent = "人名用漢字";
      } else {
        gradeBadge.textContent = `学年${res.grade}`;
      }
      badgesRow.appendChild(gradeBadge);
    }

    const tierBadge = document.createElement("span");
    tierBadge.className = "badge badge-tier-basic";
    tierBadge.textContent = tier;
    badgesRow.appendChild(tierBadge);

    const strokeBadge = document.createElement("span");
    strokeBadge.className = "badge";
    strokeBadge.style.background = "var(--bg-tertiary)";
    strokeBadge.textContent = strokeText;
    badgesRow.appendChild(strokeBadge);

    // 階層・直接/間接バッジ
    if (isDirect) {
      const directBadge = document.createElement("span");
      directBadge.className = "badge badge-direct";
      directBadge.textContent = "直接構成";
      badgesRow.appendChild(directBadge);
    } else {
      const indirectBadge = document.createElement("span");
      indirectBadge.className = "badge badge-indirect";
      if (viaChar) {
        indirectBadge.innerHTML = `間接(経由: <a class="via-link" data-via="${escapeAttr(viaChar)}">${escapeAttr(viaChar)}</a>)`;
        const viaLink = indirectBadge.querySelector(".via-link");
        if (viaLink) {
          viaLink.addEventListener("click", (e) => {
            e.stopPropagation();
            inspectCharacter(viaChar);
          });
        }
      } else {
        indirectBadge.textContent = "間接(深層展開)";
      }
      badgesRow.appendChild(indirectBadge);
    }

    info.appendChild(badgesRow);

    // IDS表示（検索部品を強調表示）
    if (idsStr) {
      const idsRow = document.createElement("div");
      idsRow.className = "result-ids-row";
      let formattedIds = idsStr;
      activeKeywords.forEach(kw => {
        if (kw && formattedIds.includes(kw)) {
          formattedIds = formattedIds.split(kw).join(`<span class="result-ids-highlight">${kw}</span>`);
        }
      });
      idsRow.innerHTML = `構造: ${formattedIds}`;
      info.appendChild(idsRow);
    }

    // 読み表示
    let readingsList = [];
    if (Array.isArray(res.ja_on) || Array.isArray(res.ja_kun)) {
      if (res.ja_on && res.ja_on.length > 0) readingsList.push(res.ja_on.join("・"));
      if (res.ja_kun && res.ja_kun.length > 0) readingsList.push(res.ja_kun.join("・"));
    } else if (res.readings) {
      readingsList.push(res.readings);
    }

    if (readingsList.length > 0) {
      const readRow = document.createElement("div");
      readRow.className = "result-readings-row";
      readRow.textContent = `読み: ${readingsList.join(" / ")}`;
      info.appendChild(readRow);
    }

    left.appendChild(info);
    card.appendChild(left);

    // クリックでこの文字を調査
    card.addEventListener("click", () => inspectCharacter(char));

    resultsGrid.appendChild(card);
  });
}

function updateResultsSummary(total, direct, indirect) {
  document.getElementById("resultsTotalCount").textContent = total;
  document.getElementById("resultsDirectCount").textContent = direct;
  document.getElementById("resultsIndirectCount").textContent = indirect;
}

// =============================================================================
// 7.5 収録熟語・語彙検索（第4カラム）
// =============================================================================

let wordsAbortController = null;

async function loadWordsForCurrentKanji() {
  const wordsGrid = document.getElementById("wordsGrid");
  const wordsTotalBadge = document.getElementById("wordsTotalBadge");
  const wordsTotalCount = document.getElementById("wordsTotalCount");
  const wordsTopCount = document.getElementById("wordsTopCount");
  const wordsHighCount = document.getElementById("wordsHighCount");

  const targetKanji = state.currentChar;
  if (!targetKanji) return;

  if (wordsAbortController) {
    wordsAbortController.abort();
  }
  wordsAbortController = new AbortController();

  if (wordsGrid) {
    wordsGrid.innerHTML = `
      <div class="state-message">
        <div class="state-spinner"></div>
        <p>「${targetKanji}」を含む熟語・語彙を検索中...</p>
      </div>
    `;
  }

  const posFilter = state.wordsFilter.position || "all";
  const tierFilter = state.wordsFilter.tier || "all";
  const keyword = state.wordsFilter.keyword || "";

  const url = `/api/words?kanji=${encodeURIComponent(targetKanji)}&position=${encodeURIComponent(posFilter)}&tier=${encodeURIComponent(tierFilter)}&keyword=${encodeURIComponent(keyword)}&limit=100`;

  try {
    const res = await fetch(url, { signal: wordsAbortController.signal });
    if (!res.ok) {
      throw new Error(`API error: ${res.status}`);
    }
    const data = await res.json();
    state.wordsData = data;

    const total = data.total || 0;
    const summary = data.summary || {};

    if (wordsTotalBadge) wordsTotalBadge.textContent = `${total}語`;
    if (wordsTotalCount) wordsTotalCount.textContent = total;
    if (wordsTopCount) wordsTopCount.textContent = summary.top || 0;
    if (wordsHighCount) wordsHighCount.textContent = summary.high || 0;

    renderWordsGrid(data.results || [], targetKanji);
  } catch (err) {
    if (err.name === "AbortError") return;
    if (wordsGrid) {
      wordsGrid.innerHTML = `
        <div class="state-message">
          <p>語彙データの読み込みに失敗しました。</p>
          <p style="font-size:0.75rem;">サーバー接続状態をご確認ください。</p>
        </div>
      `;
    }
  }
}

function renderWordsGrid(words, currentKanji) {
  const wordsGrid = document.getElementById("wordsGrid");
  if (!wordsGrid) return;
  wordsGrid.innerHTML = "";

  if (!words || words.length === 0) {
    wordsGrid.innerHTML = `
      <div class="state-message">
        <p>該当する熟語・語彙が見つかりませんでした。</p>
        <p style="font-size:0.75rem;">フィルタ条件を緩和するか、別の漢字をお試しください。</p>
      </div>
    `;
    return;
  }

  words.forEach(w => {
    const card = document.createElement("div");
    card.className = "word-card";

    // 上部ヘッダー（見出し語、読み、バッジ群）
    const topRow = document.createElement("div");
    topRow.className = "word-card-top";

    const lemmaGroup = document.createElement("div");
    lemmaGroup.className = "word-lemma-group";

    const lemmaSpan = document.createElement("span");
    lemmaSpan.className = "word-lemma";

    // 提示漢字をハイライト
    let lemmaHtml = "";
    for (const ch of (w.lemma || "")) {
      if (ch === currentKanji) {
        lemmaHtml += `<span class="highlight-kanji">${escapeAttr(ch)}</span>`;
      } else {
        lemmaHtml += escapeAttr(ch);
      }
    }
    lemmaSpan.innerHTML = lemmaHtml;
    lemmaGroup.appendChild(lemmaSpan);

    if (w.reading) {
      const readSpan = document.createElement("span");
      readSpan.className = "word-reading";
      readSpan.textContent = `【${w.reading}】`;
      lemmaGroup.appendChild(readSpan);
    }
    topRow.appendChild(lemmaGroup);

    // バッジ群（頻度、位置、品詞）
    const badgesRow = document.createElement("div");
    badgesRow.className = "word-badges-row";

    // 頻度バッジ
    const tier = w.frequency_tier || "専門・稀少";
    const freqBadge = document.createElement("span");
    let tierClass = "badge-freq-rare";
    if (tier === "最頻出") tierClass = "badge-freq-top";
    else if (tier === "頻出") tierClass = "badge-freq-high";
    else if (tier === "一般") tierClass = "badge-freq-mid";
    else if (tier === "発展") tierClass = "badge-freq-adv";

    freqBadge.className = `badge ${tierClass}`;
    freqBadge.textContent = (w.frequency_display && w.frequency_display !== "未詳")
      ? `${tier} ${w.frequency_display}`
      : tier;
    badgesRow.appendChild(freqBadge);

    // 出現位置バッジ
    if (w.position_type) {
      const posMap = {
        head: "語頭",
        middle: "語中",
        tail: "語尾",
        single: "単独",
      };
      const posBadge = document.createElement("span");
      posBadge.className = "badge badge-position";
      posBadge.textContent = posMap[w.position_type] || w.position_type;
      badgesRow.appendChild(posBadge);
    }

    // 品詞バッジ
    if (w.pos) {
      const posBadge = document.createElement("span");
      posBadge.className = "badge badge-pos";
      posBadge.textContent = w.pos;
      badgesRow.appendChild(posBadge);
    }

    topRow.appendChild(badgesRow);
    card.appendChild(topRow);

    // 語釈・意味リスト
    const defCont = document.createElement("div");
    defCont.className = "word-definition";

    const defs = (Array.isArray(w.definitions) && w.definitions.length > 0)
      ? w.definitions
      : (w.definition ? [w.definition] : []);

    if (defs.length > 1) {
      defs.slice(0, 3).forEach((d, idx) => {
        const item = document.createElement("div");
        item.className = "word-def-item";
        const num = ["①", "②", "③"][idx] || `(${idx + 1})`;
        item.innerHTML = `<span class="word-def-num">${num}</span> ${escapeAttr(d)}`;
        defCont.appendChild(item);
      });
    } else if (defs.length === 1) {
      defCont.textContent = defs[0];
    } else {
      defCont.textContent = "語釈未詳";
      defCont.style.color = "var(--text-muted)";
    }
    card.appendChild(defCont);

    // カードフッター: 構成漢字の調査ジャンプボタン
    const otherKanjis = [];
    const kanjiRegex = /[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF\u{20000}-\u{2FA1F}\u{30000}-\u{3347F}]/u;
    for (const c of (w.lemma || "")) {
      if (kanjiRegex.test(c) && c !== currentKanji && !otherKanjis.includes(c)) {
        otherKanjis.push(c);
      }
    }

    if (otherKanjis.length > 0) {
      const footer = document.createElement("div");
      footer.className = "word-card-footer";

      const linksWrap = document.createElement("div");
      linksWrap.className = "word-kanji-links";
      linksWrap.innerHTML = `<span>構成漢字:</span>`;

      otherKanjis.slice(0, 3).forEach(ok => {
        const btnJump = document.createElement("button");
        btnJump.type = "button";
        btnJump.className = "word-kanji-jump-btn";
        btnJump.textContent = `「${ok}」を調査 →`;
        btnJump.title = `「${ok}」を主文字として詳細分解します`;
        btnJump.addEventListener("click", (e) => {
          e.stopPropagation();
          inspectCharacter(ok);
        });
        linksWrap.appendChild(btnJump);
      });

      footer.appendChild(linksWrap);

      const srcLabel = document.createElement("span");
      srcLabel.className = "word-source-label";
      srcLabel.textContent = w.source || "国語辞典";
      footer.appendChild(srcLabel);

      card.appendChild(footer);
    }

    wordsGrid.appendChild(card);
  });
}

// =============================================================================
// 8. パンくずリスト & ナビゲーション
// =============================================================================

function updateBreadcrumbsUI() {
  const trail = document.getElementById("breadcrumbsTrail");
  if (!trail) return;

  // ラベル保持
  trail.innerHTML = `<span class="breadcrumb-label">探索履歴:</span>`;

  state.history.forEach((char, idx) => {
    if (idx > 0) {
      const sep = document.createElement("span");
      sep.className = "breadcrumb-sep";
      sep.textContent = "→";
      trail.appendChild(sep);
    }

    const item = document.createElement("button");
    item.className = `breadcrumb-item ${idx === state.historyIndex ? "active" : ""}`;
    item.innerHTML = `${renderGlyphHTML(char, "crumb-glyph")} <span>(${getCodepointHex(char)})</span>`;
    item.addEventListener("click", () => {
      state.historyIndex = idx;
      inspectCharacter(char, false);
    });
    trail.appendChild(item);
  });

  // 進む・戻るボタンの活性化
  const btnBack = document.getElementById("btnHistoryBack");
  const btnForward = document.getElementById("btnHistoryForward");
  if (btnBack) btnBack.disabled = state.historyIndex <= 0;
  if (btnForward) btnForward.disabled = state.historyIndex >= state.history.length - 1;
}

// =============================================================================
// 9. イベントリスナー初期化 & 起動処理
// =============================================================================

function initEventListeners() {
  // テーマ切替
  const themeBtn = document.getElementById("themeToggleBtn");
  if (themeBtn) {
    document.documentElement.setAttribute("data-theme", state.theme);
    const themeLabel = document.getElementById("themeToggleText");
    if (themeLabel) {
      themeLabel.textContent = state.theme === "dark" ? "外観: 暗色" : "外観: 明色";
    }
    themeBtn.addEventListener("click", () => {
      state.theme = state.theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", state.theme);
      if (typeof localStorage !== "undefined") {
        localStorage.setItem("kanji_theme", state.theme);
      }
      if (themeLabel) {
        themeLabel.textContent = state.theme === "dark" ? "外観: 暗色" : "外観: 明色";
      }
    });
  }

  // 表示モード切替（筆画表示 vs 明朝体印刷書体）
  const btnKvg = document.getElementById("btnModeKvg");
  const btnMincho = document.getElementById("btnModeMincho");
  if (btnKvg && btnMincho) {
    btnKvg.addEventListener("click", () => {
      if (state.activeDisplayMode === "kvg") return;
      state.activeDisplayMode = "kvg";
      btnKvg.classList.add("active");
      btnMincho.classList.remove("active");
      renderCanvas();
    });
    btnMincho.addEventListener("click", () => {
      if (state.activeDisplayMode === "mincho") return;
      state.activeDisplayMode = "mincho";
      btnMincho.classList.add("active");
      btnKvg.classList.remove("active");
      renderCanvas();
    });
  }

  // 統合検索バー
  const searchInput = document.getElementById("mainSearchInput");
  const btnInspect = document.getElementById("btnInspect");
  const btnFind = document.getElementById("btnFind");

  if (btnInspect && searchInput) {
    btnInspect.addEventListener("click", () => {
      const val = searchInput.value.trim();
      if (val) inspectCharacter(val);
    });
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = searchInput.value.trim();
        if (val) inspectCharacter(val);
      }
    });
  }

  if (btnFind && searchInput) {
    btnFind.addEventListener("click", () => {
      const val = searchInput.value.trim();
      if (val) addFindChip(val);
    });
  }

  // クイック探索プリセット
  document.querySelectorAll(".preset-chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const drilldown = btn.getAttribute("data-drilldown");
      if (drilldown) {
        // 段階的ドリルダウン例 (蛍 -> 𰃮 -> 𭕄)
        const sequence = drilldown.split(",");
        state.history = [];
        sequence.forEach((ch, i) => {
          state.history.push(ch);
          state.historyIndex = i;
        });
        inspectCharacter(sequence[0], false);
      } else {
        const kanji = btn.getAttribute("data-kanji");
        if (kanji) inspectCharacter(kanji);
      }
    });
  });

  // 履歴進む・戻る・消去
  const btnBack = document.getElementById("btnHistoryBack");
  const btnForward = document.getElementById("btnHistoryForward");
  const btnClear = document.getElementById("btnHistoryClear");

  if (btnBack) {
    btnBack.addEventListener("click", () => {
      if (state.historyIndex > 0) {
        state.historyIndex--;
        inspectCharacter(state.history[state.historyIndex], false);
      }
    });
  }

  if (btnForward) {
    btnForward.addEventListener("click", () => {
      if (state.historyIndex < state.history.length - 1) {
        state.historyIndex++;
        inspectCharacter(state.history[state.historyIndex], false);
      }
    });
  }

  if (btnClear) {
    btnClear.addEventListener("click", () => {
      state.history = [state.currentChar];
      state.historyIndex = 0;
      updateBreadcrumbsUI();
    });
  }

  // キャンバス内空白領域への移動時および領域からの退出時にホバーハイライトを解除
  const canvasContainer = document.getElementById("canvasSvgContainer");
  if (canvasContainer) {
    canvasContainer.addEventListener("mouseover", (e) => {
      const hitNode = e.target?.closest ? e.target.closest("[data-path]") : null;
      const hitPath = hitNode ? hitNode.getAttribute("data-path") : null;
      if ((!hitPath || hitPath === "0") && state.hoveredPath) {
        clearComponentHover();
      }
    });
    canvasContainer.addEventListener("mouseleave", () => {
      clearComponentHover();
    });
  }

  // 段階的ロック階層探索コントローラー
  const btnLockStepUp = document.getElementById("btnLockStepUp");
  if (btnLockStepUp) {
    btnLockStepUp.addEventListener("click", () => {
      stepLockScopeUp();
    });
  }

  const btnResetLock = document.getElementById("btnResetLock");
  if (btnResetLock) {
    btnResetLock.addEventListener("click", () => {
      resetLockedScope();
    });
  }

  // Escキーで選択固定（ロック）解除
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.lockedPath !== null) {
      resetLockedScope();
    }
  });

  // 逆引きチップ入力
  const findInput = document.getElementById("findComponentInput");
  if (findInput) {
    findInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = findInput.value.trim();
        if (val) {
          addFindChip(val);
          findInput.value = "";
        }
      }
    });
  }

  const btnClearFind = document.getElementById("btnClearFindChips");
  if (btnClearFind) {
    btnClearFind.addEventListener("click", clearFindChips);
  }

  // フィルタ変更イベント
  const filterHierarchy = document.getElementById("filterHierarchy");
  const filterCategory = document.getElementById("filterCategory");
  const btnApplyFind = document.getElementById("btnApplyFind");

  if (filterHierarchy) filterHierarchy.addEventListener("change", executeFindSearch);
  if (filterCategory) filterCategory.addEventListener("change", executeFindSearch);
  if (btnApplyFind) btnApplyFind.addEventListener("click", executeFindSearch);

  // 熟語検索・フィルタイベント（第4カラム）
  const wordsInput = document.getElementById("wordsKeywordInput");
  let wordsDebounceTimer = null;
  if (wordsInput) {
    wordsInput.addEventListener("input", (e) => {
      clearTimeout(wordsDebounceTimer);
      wordsDebounceTimer = setTimeout(() => {
        state.wordsFilter.keyword = e.target.value.trim();
        loadWordsForCurrentKanji();
      }, 250);
    });
  }

  const filterWordPos = document.getElementById("filterWordPosition");
  if (filterWordPos) {
    filterWordPos.addEventListener("change", (e) => {
      state.wordsFilter.position = e.target.value;
      loadWordsForCurrentKanji();
    });
  }

  const filterWordTier = document.getElementById("filterWordTier");
  if (filterWordTier) {
    filterWordTier.addEventListener("change", (e) => {
      state.wordsFilter.tier = e.target.value;
      loadWordsForCurrentKanji();
    });
  }

  const btnClearWords = document.getElementById("btnClearWordsFilter");
  if (btnClearWords) {
    btnClearWords.addEventListener("click", () => {
      state.wordsFilter = { position: "all", tier: "all", keyword: "" };
      if (wordsInput) wordsInput.value = "";
      if (filterWordPos) filterWordPos.value = "all";
      if (filterWordTier) filterWordTier.value = "all";
      loadWordsForCurrentKanji();
    });
  }
}

// 起動初期化
document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  renderFindChips();

  const urlParams = new URLSearchParams(window.location.search);
  const themeParam = urlParams.get("theme");
  if (themeParam === "dark" || themeParam === "light") {
    state.theme = themeParam;
    document.documentElement.setAttribute("data-theme", state.theme);
    const themeLabel = document.getElementById("themeToggleText");
    if (themeLabel) {
      themeLabel.textContent = state.theme === "dark" ? "外観: 暗色" : "外観: 明色";
    }
  }

  const initialChar = urlParams.get("char") || urlParams.get("c") || urlParams.get("q") || "蛍";
  const initialHover = urlParams.get("hover") || urlParams.get("path");
  const initialLock = urlParams.get("lock");

  inspectCharacter(initialChar).then(() => {
    if (initialLock) {
      lockComponentScope(initialLock);
    } else if (initialHover) {
      handleComponentHover(initialHover);
    }
  });
});
