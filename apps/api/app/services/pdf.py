"""PDF rendering for assessment reports and proposals (ReportLab, no external services)."""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BRAND = colors.HexColor("#1e3a8a")
_styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_styles["Heading1"], textColor=BRAND, fontSize=20, spaceAfter=8)
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], textColor=BRAND, fontSize=13, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("body", parent=_styles["BodyText"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, textColor=colors.HexColor("#555555"))


def _esc(s) -> str:
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bullets(items) -> ListFlowable:
    return ListFlowable([ListItem(Paragraph(_esc(i), BODY), leftIndent=10) for i in items], bulletType="bullet",
                        start="•", leftIndent=12)


def _table(rows, widths=None) -> Table:
    t = Table([[Paragraph(_esc(c), BODY) for c in r] for r in rows], colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf7")),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c7cfdd")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _footer(label: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(18 * mm, 10 * mm, f"DeployMind · {label} · generated {datetime.now():%Y-%m-%d %H:%M}")
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def assessment_pdf(org_name: str, assessment, scores, opportunities) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=f"AI Readiness Report - {org_name}")
    f, r = assessment.findings, assessment.report or {}
    s = [Paragraph("AI Readiness Report", H1), Paragraph(_esc(org_name), H2),
         Paragraph(f"Overall score <b>{assessment.overall_score}/100</b> · {_esc(assessment.classification)}", BODY),
         Paragraph(_esc(f.get("classification_text", "")), SMALL),
         Paragraph("Scores are computed by a deterministic weighted model (question bank v"
                   f"{assessment.question_version}). Narrative text is AI-assisted"
                   f"{' (mock provider)' if (r.get('provenance') or {}).get('is_mock') else ''}.", SMALL),
         Spacer(1, 6)]
    if r.get("executive_summary"):
        s += [Paragraph("Executive summary", H2), Paragraph(_esc(r["executive_summary"]), BODY)]
    s += [Paragraph("Dimension scores", H2),
          _table([["Dimension", "Score", "Level", "Weight", "Commentary"]] +
                 [[sc.dimension.title(), f"{sc.score}", sc.level, f"{float(sc.weight):.0%}",
                   (r.get("dimension_commentary") or {}).get(sc.dimension, "")] for sc in scores],
                 [32 * mm, 16 * mm, 24 * mm, 16 * mm, 86 * mm])]
    s += [Paragraph("Strengths", H2), _bullets([x["title"] for x in f.get("strengths", [])] or ["None identified"]),
          Paragraph("Weaknesses", H2), _bullets([x["title"] for x in f.get("weaknesses", [])] or ["None identified"]),
          Paragraph("Risks", H2), _bullets([f"[{x['severity']}] {x['risk']}" for x in f.get("risks", [])] or ["None"]),
          Paragraph("Recommendations", H2),
          _bullets([x["recommendation"] for x in f.get("recommendations", [])] + r.get("adoption_recommendations", []))]
    if f.get("first_project"):
        s += [Paragraph("Recommended first AI project", H2), Paragraph(_esc(f["first_project"]["title"]), BODY),
              Paragraph(_esc(r.get("first_project_rationale", "")), BODY)]
    s.append(PageBreak())
    s += [Paragraph("30 / 60 / 90 day action plan", H2)]
    for w in f.get("plan_30_60_90", []):
        s += [Paragraph(f"<b>{_esc(w['window'])}</b> - {_esc(w['focus'])}", BODY), _bullets(w["actions"])]
    s += [Paragraph("3 / 6 / 12 month roadmap", H2),
          _table([["Horizon", "Milestone", "Outcomes"]] +
                 [[x["horizon"], x["milestone"], "; ".join(x["outcomes"])] for x in f.get("roadmap", [])],
                 [24 * mm, 60 * mm, 90 * mm])]
    if opportunities:
        s += [Paragraph("Prioritised AI opportunities", H2),
              Paragraph("Financial values are illustrative estimates based on stated assumptions, not guaranteed "
                        "outcomes.", SMALL),
              _table([["#", "Opportunity", "Priority", "Impact", "Complexity", "Effort (wks)", "Est. annual value"]] +
                     [[o.rank, o.title, f"{o.priority_score}", o.business_impact, o.implementation_complexity,
                       o.effort_weeks, f"{o.roi_assumptions['currency']} {o.roi_assumptions['estimated_annual_value_low']:,}"
                       f"-{o.roi_assumptions['estimated_annual_value_high']:,}"] for o in opportunities],
                     [8 * mm, 50 * mm, 18 * mm, 16 * mm, 20 * mm, 20 * mm, 42 * mm])]
    doc.build(s, onFirstPage=_footer("AI Readiness Report"), onLaterPages=_footer("AI Readiness Report"))
    return buf.getvalue()


def proposal_pdf(org_name: str, proposal, content: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=proposal.title)
    cur = content.get("currency", proposal.currency)
    s = [Paragraph("Proposal", H1), Paragraph(_esc(proposal.title), H2),
         Paragraph(f"Prepared for {_esc(org_name)} · version {proposal.current_version} · status {proposal.status}", SMALL)]
    if proposal.status in ("draft", "in_review"):
        s.append(Paragraph("<b>DRAFT - not yet approved by an authorised engineer.</b>", SMALL))
    for title, key in [("Executive summary", "executive_summary"), ("Business problem", "business_problem"),
                       ("Proposed solution", "proposed_solution"), ("Technical architecture", "technical_architecture")]:
        s += [Paragraph(title, H2), Paragraph(_esc(content.get(key, "")), BODY)]
    s += [Paragraph("Deliverables", H2), _bullets(content.get("deliverables", [])),
          Paragraph("Milestones & timeline", H2),
          _table([["Milestone", "Start week", "Duration (weeks)"]] +
                 [[m["title"], m["start_week"], m["weeks"]] for m in content.get("milestones", [])]),
          Paragraph(f"Total timeline: {content.get('timeline_weeks')} weeks", BODY),
          Paragraph("Team", H2),
          _table([["Role", "Allocation"]] + [[t["role"], f"{t['allocation']:.0%}"] for t in content.get("team", [])]),
          Paragraph("Estimated costs", H2),
          _table([["Item", f"Amount ({cur})"]] + [[c["item"], f"{c['amount']:,.0f}"] for c in content.get("costs", [])]
                 + [["Total (estimate)", f"{content.get('total', 0):,.0f}"]], [130 * mm, 44 * mm]),
          Paragraph(_esc(content.get("estimate_label", "")), SMALL),
          Paragraph("Risks and assumptions", H2), _bullets(content.get("risks_and_assumptions", [])),
          Paragraph("Acceptance criteria", H2), _bullets(content.get("acceptance_criteria", [])),
          Paragraph("Support agreement", H2), Paragraph(_esc(content.get("support_agreement", "")), BODY)]
    doc.build(s, onFirstPage=_footer("Proposal"), onLaterPages=_footer("Proposal"))
    return buf.getvalue()
