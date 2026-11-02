import os
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# Color Palette
DARK_NAVY = RGBColor(15, 23, 42)      # #0F172A
ROYAL_BLUE = RGBColor(46, 49, 146)    # #2E3192
EMERALD = RGBColor(16, 185, 129)     # #10B981
SLATE_GRAY = RGBColor(71, 85, 105)   # #475569
LIGHT_BG = RGBColor(248, 250, 252)   # #F8FAFC
CARD_BG = RGBColor(255, 255, 255)    # #FFFFFF
BORDER_COLOR = RGBColor(226, 232, 240) # #E2E8F0
TEXT_MAIN = RGBColor(30, 41, 59)     # #1E293B

def create_deck():
    prs = pptx.Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    img_dir = r"C:\Users\sudee\.gemini\antigravity\brain\f3e07ded-59de-4948-92f6-c8af76b5a340\.user_uploaded"
    img1 = os.path.join(img_dir, "media__1785237463120.png")
    img2 = os.path.join(img_dir, "media__1785402005225.png")
    img3 = os.path.join(img_dir, "media__1785402041007.png")
    img4 = os.path.join(img_dir, "media__1785402122643.png")

    def set_slide_background(slide, color):
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = color

    def add_header(slide, title_text, category_text="IFQM ENTERPRISE AI CASE SYNTHESIS PLATFORM"):
        # Header banner
        header_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.733), Inches(0.9))
        tf = header_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        p1 = tf.paragraphs[0]
        p1.text = category_text.upper()
        p1.font.size = Pt(10)
        p1.font.bold = True
        p1.font.color.rgb = ROYAL_BLUE

        p2 = tf.add_paragraph()
        p2.text = title_text
        p2.font.size = Pt(22)
        p2.font.bold = True
        p2.font.color.rgb = DARK_NAVY

    # ==========================================
    # SLIDE 1: Title Slide (Dark Theme)
    # ==========================================
    slide1 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide1, DARK_NAVY)

    # Decorative Card
    card = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.2), Inches(11.333), Inches(5.1))
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(30, 41, 59)
    card.line.color.rgb = RGBColor(51, 65, 85)

    tb = slide1.shapes.add_textbox(Inches(1.5), Inches(1.8), Inches(10.333), Inches(4.0))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "INDIAN FOUNDATION FOR QUALITY MANAGEMENT (IFQM)"
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = EMERALD

    p2 = tf.add_paragraph()
    p2.text = "Enterprise AI Case Synthesis Platform"
    p2.font.size = Pt(36)
    p2.font.bold = True
    p2.font.color.rgb = RGBColor(255, 255, 255)

    p3 = tf.add_paragraph()
    p3.text = "Automated Harvard & Ivey-Standard Case Study & Faculty Teaching Note Generator"
    p3.font.size = Pt(18)
    p3.font.color.rgb = RGBColor(203, 213, 225)

    p4 = tf.add_paragraph()
    p4.text = "\nProject Technical Presentation & Demonstration | Powered by Agentic RAG & SFT"
    p4.font.size = Pt(12)
    p4.font.color.rgb = RGBColor(148, 163, 184)

    # ==========================================
    # SLIDE 2: Project Objectives & Core Problem
    # ==========================================
    slide2 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide2, LIGHT_BG)
    add_header(slide2, "Project Background & Core Objectives")

    # Card 1: Problem Statement
    c1 = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.5), Inches(5.6), Inches(5.2))
    c1.fill.solid()
    c1.fill.fore_color.rgb = CARD_BG
    c1.line.color.rgb = BORDER_COLOR

    tb = slide2.shapes.add_textbox(Inches(1.1), Inches(1.8), Inches(5.0), Inches(4.6))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "🎯 The Problem We Solved"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = ROYAL_BLUE

    bullets1 = [
        "Traditional case writing takes 3-6 months of manual field interviews, data entry, and editing.",
        "Corporate annual reports (100+ pages) are difficult to analyze and translate into teaching dilemmas.",
        "Generic LLMs generate inaccurate AI hallucinations and repetitive corporate fluff.",
        "Faculty lack automated tools to create student cases alongside matching teaching notes."
    ]
    for b in bullets1:
        p_b = tf.add_paragraph()
        p_b.text = "• " + b
        p_b.font.size = Pt(13)
        p_b.font.color.rgb = TEXT_MAIN

    # Card 2: Solution & Objectives
    c2 = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(1.5), Inches(5.7), Inches(5.2))
    c2.fill.solid()
    c2.fill.fore_color.rgb = CARD_BG
    c2.line.color.rgb = BORDER_COLOR

    tb2 = slide2.shapes.add_textbox(Inches(7.1), Inches(1.8), Inches(5.1), Inches(4.6))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    p = tf2.paragraphs[0]
    p.text = "🚀 Our Solution & Objectives"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = EMERALD

    bullets2 = [
        "Automates Harvard/Ivey standard business case creation in under 3 minutes.",
        "Ingests multi-modal data: PDF annual reports, executive audio recordings, transcripts, and web data.",
        "Integrates 20-claim Adversarial Verification (CoVe) to enforce >90% factual accuracy.",
        "Exports dual Word documents: Student Case Study Volume + Faculty Teaching Note Volume."
    ]
    for b in bullets2:
        p_b = tf2.add_paragraph()
        p_b.text = "• " + b
        p_b.font.size = Pt(13)
        p_b.font.color.rgb = TEXT_MAIN

    # ==========================================
    # SLIDE 3: Technical Architecture (Agentic RAG + SFT)
    # ==========================================
    slide3 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide3, LIGHT_BG)
    add_header(slide3, "System Architecture: Agentic RAG & Supervised Fine-Tuning")

    # 4 Architecture Columns
    col_width = Inches(2.7)
    col_gap = Inches(0.3)
    start_x = Inches(0.8)

    arch_items = [
        ("1. Multi-Modal Ingestion", ROYAL_BLUE, [
            "50x Fast PyMuPDF C-parser for 100+ pg PDFs.",
            "Gemini 2.5 Flash native speech-to-text audio transcription.",
            "DuckDuckGo + Crawl4AI web search fallback."
        ]),
        ("2. Hybrid RAG Vector Engine", ROYAL_BLUE, [
            "ChromaDB dense vector embeddings.",
            "BM25 sparse keyword matching.",
            "Reciprocal Rank Fusion (RRF) for 100% grounded retrieval."
        ]),
        ("3. Agentic Verification Loop", EMERALD, [
            "Autonomous multi-agent synthesis & generation.",
            "Chain-of-Verification (CoVe) 20-claim fact auditor.",
            "Banned-word filter for academic Harvard tone."
        ]),
        ("4. SFT & Dual Word Exporter", EMERALD, [
            "Supervised Fine-Tuned (SFT) model weights.",
            "Automated financial charts & timeline milestones.",
            "1-Click Student Case & Teaching Note export."
        ])
    ]

    for idx, (title, col_color, points) in enumerate(arch_items):
        x_pos = start_x + idx * (col_width + col_gap)
        card = slide3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x_pos, Inches(1.5), col_width, Inches(5.2))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = BORDER_COLOR

        tb = slide3.shapes.add_textbox(x_pos + Inches(0.15), Inches(1.7), col_width - Inches(0.3), Inches(4.8))
        tf = tb.text_frame
        tf.word_wrap = True

        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = col_color

        for pt in points:
            p_b = tf.add_paragraph()
            p_b.text = "• " + pt
            p_b.font.size = Pt(11)
            p_b.font.color.rgb = TEXT_MAIN

    # ==========================================
    # SLIDE 4: Stage 3 & 4 - Interactive Brief & Live Exhibits
    # ==========================================
    slide4 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide4, LIGHT_BG)
    add_header(slide4, "Stage 3 & 4: Interactive Brief Tree & Live Exhibit Weaver")

    # Left: Screenshot 1
    if os.path.exists(img1):
        slide4.shapes.add_picture(img1, Inches(0.8), Inches(1.5), Inches(7.5), Inches(5.2))

    # Right: Explanatory Box
    card = slide4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.6), Inches(1.5), Inches(3.9), Inches(5.2))
    card.fill.solid()
    card.fill.fore_color.rgb = CARD_BG
    card.line.color.rgb = BORDER_COLOR

    tb = slide4.shapes.add_textbox(Inches(8.8), Inches(1.7), Inches(3.5), Inches(4.8))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "Key Capabilities Highlighted:"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = ROYAL_BLUE

    points4 = [
        "Executive Protagonist Identification: Extracts leaders like Jensen Huang (NVIDIA CEO) & decision dilemmas.",
        "Historical Timeline Milestones: Extracts key company foundation and strategic evolution dates.",
        "Interactive Live Exhibit Weaver: Dynamically parses financial and operational metrics (Operating Margins, Defect Rates, R&D Capex).",
        "Times New Roman 11pt Academic Preview: Live rendering of generated chapters."
    ]
    for pt in points4:
        p_b = tf.add_paragraph()
        p_b.text = "• " + pt
        p_b.font.size = Pt(11)
        p_b.font.color.rgb = TEXT_MAIN

    # ==========================================
    # SLIDE 5: Human-in-the-Loop Review & Steerage
    # ==========================================
    slide5 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide5, LIGHT_BG)
    add_header(slide5, "Live Generation: Human-in-the-Loop Steerage & Approval")

    # Left: Screenshot 4
    if os.path.exists(img4):
        slide5.shapes.add_picture(img4, Inches(0.8), Inches(1.5), Inches(7.5), Inches(5.2))

    # Right: Explanatory Box
    card = slide5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.6), Inches(1.5), Inches(3.9), Inches(5.2))
    card.fill.solid()
    card.fill.fore_color.rgb = CARD_BG
    card.line.color.rgb = BORDER_COLOR

    tb = slide5.shapes.add_textbox(Inches(8.8), Inches(1.7), Inches(3.5), Inches(4.8))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "Interactive Controls During Generation:"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = EMERALD

    points5 = [
        "Approve & Continue Section Control: Allows reviewing each chapter before approving.",
        "Local Steerage Directive: Guide the AI on specific focus areas (e.g., European defect rates or financial ratios).",
        "Injected Overview / Manual Data: Append custom quotes, plant logs, or metrics on the fly.",
        "Dynamic Context Discovery: System alerts when Six Sigma or Lean Quality context is discovered and suggests 1-click injection."
    ]
    for pt in points5:
        p_b = tf.add_paragraph()
        p_b.text = "• " + pt
        p_b.font.size = Pt(11)
        p_b.font.color.rgb = TEXT_MAIN

    # ==========================================
    # SLIDE 6: Stage 5 - Chapter Configuration & Custom Injection
    # ==========================================
    slide6 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide6, LIGHT_BG)
    add_header(slide6, "Stage 5: Custom Chapter Configuration & Injection")

    # Left: Screenshot 2
    if os.path.exists(img2):
        slide6.shapes.add_picture(img2, Inches(0.8), Inches(1.5), Inches(7.5), Inches(5.2))

    # Right: Explanatory Box
    card = slide6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.6), Inches(1.5), Inches(3.9), Inches(5.2))
    card.fill.solid()
    card.fill.fore_color.rgb = CARD_BG
    card.line.color.rgb = BORDER_COLOR

    tb = slide6.shapes.add_textbox(Inches(8.8), Inches(1.7), Inches(3.5), Inches(4.8))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "Customization Features:"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = ROYAL_BLUE

    points6 = [
        "Configure Chapters to Include: Checkboxes to select or hide specific chapters (Opening Hook, Company Background, Root Cause Analysis, etc.).",
        "Dynamic Section & Exhibit Injector: Create custom standard chapters or Mermaid process flow diagrams.",
        "Source Citation Grounding: Automatic inline page citations like [infosys-ar-25.pdf] for complete transparency."
    ]
    for pt in points6:
        p_b = tf.add_paragraph()
        p_b.text = "• " + pt
        p_b.font.size = Pt(11)
        p_b.font.color.rgb = TEXT_MAIN

    # ==========================================
    # SLIDE 7: Synthesis Complete & Dual Export
    # ==========================================
    slide7 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide7, LIGHT_BG)
    add_header(slide7, "Synthesis Complete: 1-Click Dual Word (.docx) Export")

    # Left: Screenshot 3
    if os.path.exists(img3):
        slide7.shapes.add_picture(img3, Inches(0.8), Inches(1.5), Inches(7.5), Inches(5.2))

    # Right: Explanatory Box
    card = slide7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.6), Inches(1.5), Inches(3.9), Inches(5.2))
    card.fill.solid()
    card.fill.fore_color.rgb = CARD_BG
    card.line.color.rgb = BORDER_COLOR

    tb = slide7.shapes.add_textbox(Inches(8.8), Inches(1.7), Inches(3.5), Inches(4.8))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "Final Output Deliverables:"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = EMERALD

    points7 = [
        "Synthesis Complete Interface: Appears immediately after all chapters are verified and approved.",
        "Download Case Volume (.docx): Complete student case study with formatted financial charts and timeline diagrams.",
        "Download Teaching Note (.docx): Full faculty teaching guide with learning objectives, discussion answers, and classroom board plans.",
        "Instant Session Reset: 'Create Another Case Study' button for rapid iteration."
    ]
    for pt in points7:
        p_b = tf.add_paragraph()
        p_b.text = "• " + pt
        p_b.font.size = Pt(11)
        p_b.font.color.rgb = TEXT_MAIN

    # ==========================================
    # SLIDE 8: Project Impact & Summary USPs
    # ==========================================
    slide8 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide8, DARK_NAVY)

    tb = slide8.shapes.add_textbox(Inches(0.8), Inches(0.6), Inches(11.733), Inches(0.8))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    p.text = "SUMMARY OF KEY PROJECT INNOVATIONS & USPs"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = RGBColor(255, 255, 255)

    col_w = Inches(3.6)
    col_g = Inches(0.4)

    usps = [
        ("⚡ 99% Time Reduction", "Reduced case preparation time from 3-6 months down to <3 minutes of automated synthesis."),
        ("🛡️ >90% Fact-Checked", "20-claim Chain-of-Verification (CoVe) audit engine ensures zero AI hallucinations."),
        ("🎓 Harvard/Ivey Standard", "Supervised Fine-Tuned (SFT) model enforces formal academic tone with zero corporate fluff.")
    ]

    for idx, (title, desc) in enumerate(usps):
        x = Inches(0.8) + idx * (col_w + col_g)
        card = slide8.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(1.8), col_w, Inches(4.5))
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(30, 41, 59)
        card.line.color.rgb = RGBColor(51, 65, 85)

        tb = slide8.shapes.add_textbox(x + Inches(0.2), Inches(2.2), col_w - Inches(0.4), Inches(3.8))
        tf = tb.text_frame
        tf.word_wrap = True

        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(18)
        p.font.bold = True
        p.font.color.rgb = EMERALD

        p2 = tf.add_paragraph()
        p2.text = "\n" + desc
        p2.font.size = Pt(14)
        p2.font.color.rgb = RGBColor(226, 232, 240)

    output_path = r"d:\ifqm-case-generator\IFQM_Enterprise_AI_Case_Synthesis_Presentation.pptx"
    prs.save(output_path)
    print(f"Presentation saved successfully to: {output_path}")

if __name__ == "__main__":
    create_deck()
