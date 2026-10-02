"""Renders ranked OpportunityBriefs to a single rep-ready PDF:
a summary ranking table, followed by one detail card per account.
"""
from __future__ import annotations

import datetime as dt

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .schema import OpportunityBrief

_TIER_COLOR = {"A": colors.HexColor("#1a7f37"), "B": colors.HexColor("#9a6700"), "C": colors.HexColor("#6e7781")}
_URGENCY_COLOR = {"High": colors.HexColor("#cf222e"), "Medium": colors.HexColor("#9a6700"), "Low": colors.HexColor("#6e7781")}


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Title2", fontSize=20, leading=24, spaceAfter=6))
    styles.add(ParagraphStyle(name="SubTitle", fontSize=10, textColor=colors.grey, spaceAfter=16))
    styles.add(ParagraphStyle(name="CardHeading", fontSize=15, leading=18, spaceAfter=4))
    styles.add(ParagraphStyle(name="Label", fontSize=9, textColor=colors.grey, spaceBefore=8, spaceAfter=2))
    styles.add(ParagraphStyle(name="Body", fontSize=10.5, leading=14))
    styles.add(ParagraphStyle(name="Small", fontSize=8, textColor=colors.grey))
    return styles


def render_pdf(briefs: list[OpportunityBrief], output_path: str, title: str = "Media-Opportunity Radar") -> None:
    styles = _styles()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=LETTER,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        title=title,
    )
    story = []

    story.append(Paragraph(title, styles["Title2"]))
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    mode_note = "LIVE (Claude + web search)" if any(b.data_mode == "live" for b in briefs) else "MOCK (offline demo, no live data)"
    story.append(Paragraph(f"Generated {generated} · data mode: {mode_note} · {len(briefs)} accounts", styles["SubTitle"]))

    table_data = [["#", "Account", "Industry", "Tier", "Urgency", "Signal (short)"]]
    for i, b in enumerate(briefs, start=1):
        short = b.signal_summary if len(b.signal_summary) <= 90 else b.signal_summary[:87] + "..."
        table_data.append([str(i), b.account, b.industry, b.tier, b.urgency, short])

    table = Table(table_data, colWidths=[0.3 * inch, 1.3 * inch, 1.0 * inch, 0.5 * inch, 0.6 * inch, 2.8 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2328")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(PageBreak())

    for i, b in enumerate(briefs, start=1):
        story.append(Paragraph(f"{i}. {b.account}", styles["CardHeading"]))
        story.append(
            Paragraph(
                f'<font color="{_TIER_COLOR[b.tier].hexval()}"><b>Tier {b.tier}</b></font> &nbsp;·&nbsp; '
                f'<font color="{_URGENCY_COLOR[b.urgency].hexval()}"><b>{b.urgency} urgency</b></font> &nbsp;·&nbsp; '
                f"{b.industry} &nbsp;·&nbsp; confidence: {b.confidence} &nbsp;·&nbsp; mode: {b.data_mode}",
                styles["Small"],
            )
        )

        story.append(Paragraph("Signal", styles["Label"]))
        story.append(Paragraph(b.signal_summary, styles["Body"]))

        story.append(Paragraph("Why now", styles["Label"]))
        story.append(Paragraph(b.why_now, styles["Body"]))

        story.append(Paragraph("Recommended action", styles["Label"]))
        story.append(Paragraph(b.recommended_action, styles["Body"]))

        if b.warm_path:
            story.append(Paragraph("Warm path", styles["Label"]))
            story.append(Paragraph(b.warm_path, styles["Body"]))

        if b.sources:
            story.append(Paragraph("Sources", styles["Label"]))
            for s in b.sources:
                story.append(Paragraph(f'<link href="{s.url}">{s.title}</link>', styles["Small"]))

        story.append(Spacer(1, 18))
        if i != len(briefs):
            story.append(PageBreak())

    doc.build(story)
