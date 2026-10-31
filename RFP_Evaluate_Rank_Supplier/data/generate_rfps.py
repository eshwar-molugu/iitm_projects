"""Generate four fictional supplier proposals (PDF) for one invented RFP.

Run from the project root:  python3 data/generate_rfps.py
All companies, people, prices and references are invented.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

OUT_DIR = Path(__file__).resolve().parent / "rfps"

CSS = """
body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #1b2430; line-height: 1.35; }
h1 { font-size: 16pt; color: #17324d; margin: 0 0 4pt 0; }
h2 { font-size: 12pt; color: #17324d; margin: 12pt 0 4pt 0; border-bottom: 1px solid #c9d3df; }
p { margin: 3pt 0 6pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt 0; }
th, td { border: 1px solid #b8c4d2; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #e6edf5; }
.meta { color: #55657a; font-size: 9pt; }
"""


def _page(title: str, meta: str, body: str) -> str:
    return (
        f"<html><head><style>{CSS}</style></head><body>"
        f"<h1>{title}</h1><p class='meta'>{meta}</p>{body}</body></html>"
    )


META = (
    "Response to RFP-2026-017: Procurement Workflow Automation Platform for GreenLeaf Retail Pvt. Ltd. "
    "Requirement: 500 users, 3 regional offices, SAP S/4HANA plus supplier-portal integration, go-live within "
    "8 months, 3-year term. All prices in INR lakh, excluding GST."
)


APEX = _page(
    "Apex Systems - Proposal for FlowCore Enterprise",
    META,
    """
<h2>1. Executive Summary and Understanding of the Requirement</h2>
<p>Apex Systems proposes FlowCore Enterprise, a workflow automation platform built on Kafka-based microservices
running on Kubernetes. We understand GreenLeaf needs purchase-to-pay and supplier onboarding flows for 500 users
across three regional offices, with bidirectional synchronisation to SAP S/4HANA and a secure supplier portal.</p>

<h2>2. Proposed Solution and Implementation Approach</h2>
<p>The architecture separates the workflow engine, the SAP integration layer and the supplier portal. The SAP
connector is certified and uses asynchronous retries with dead-letter queues. Load testing was run to 2,000
concurrent users in our lab, so the 500-user requirement has 4x headroom. The platform runs active-active across two
availability zones with a contracted 99.95% monthly SLA, RPO of 5 minutes and RTO of 30 minutes.</p>
<p>Implementation follows four stages: discovery, configuration of three regional approval matrices, SAP
integration build and test, and phased cutover. Each stage ends with a documented sign-off by GreenLeaf.</p>

<h2>3. Timeline, Team Structure and Milestones</h2>
<p>Total duration is 9 months. Milestone M2 (SAP integration in test) slipped by one month in our last comparable
engagement; we have included one month of contingency in the plan, so go-live is at month 9, one month beyond
the 8-month target.</p>
<table>
<tr><th>Role</th><th>Headcount</th><th>Responsibility</th></tr>
<tr><td>Delivery lead</td><td>1</td><td>Plan, governance, escalations</td></tr>
<tr><td>Solution architects</td><td>2</td><td>Integration design, security design</td></tr>
<tr><td>Developers</td><td>6</td><td>Workflow build, SAP connector configuration</td></tr>
<tr><td>Test and QA</td><td>3</td><td>Functional, performance and security testing</td></tr>
<tr><td>Trainers and change</td><td>2</td><td>Role-based training, adoption support</td></tr>
<tr><td>Support engineers</td><td>1</td><td>Hypercare shadowing</td></tr>
</table>
<p>Total team size is 15 people. Milestones: M1 design sign-off (month 2), M2 SAP integration in test (month 5),
M3 pilot office live (month 7), M4 full go-live (month 9).</p>

<h2>4. Price Table and Assumptions</h2>
<table>
<tr><th>Item</th><th>Amount (INR lakh)</th></tr>
<tr><td>Licences (3 years)</td><td>1,100</td></tr>
<tr><td>Implementation services</td><td>1,350</td></tr>
<tr><td>Training</td><td>150</td></tr>
<tr><td>Support (3 years)</td><td>800</td></tr>
<tr><td><b>Total</b></td><td><b>3,400</b></td></tr>
</table>
<p>Assumptions: GreenLeaf provides SAP sandbox access within 4 weeks of kickoff; change requests beyond 10% of
effort are priced separately at the agreed rate card. Prices exclude GST and travel.</p>

<h2>5. Security, Compliance and Risk Controls</h2>
<p>FlowCore Enterprise holds ISO 27001:2022 and SOC 2 Type II certifications (reports available under NDA). Controls
include role-based access with MFA for all users, AES-256 encryption at rest and TLS 1.3 in transit, and an
8-year immutable audit log. We run independent penetration tests twice a year; the latest report found no critical
issues. Data is stored in India-region data centres.</p>
<p>Key delivery risks: SAP sandbox availability (mitigated by an early environment request), change in approval
matrices during build (mitigated by a frozen design at M1), and supplier-portal onboarding volumes (mitigated by
load tests already completed).</p>

<h2>6. Support Model, Relevant Experience and References</h2>
<p>Support runs 24 hours a day, five days a week (Monday to Friday), with a 1-hour response for severity 1
incidents. We have delivered 22 comparable deployments in manufacturing and retail. Two named references are
available on request: a national retail chain (420 users, eight sites) and an apparel manufacturer (600 users,
SAP ECC migration to S/4HANA).</p>
""",
)


BRIGHTPATH = _page(
    "BrightPath Tech - Proposal for QuickFlow",
    META,
    """
<h2>1. Executive Summary and Understanding of the Requirement</h2>
<p>BrightPath Tech offers QuickFlow, a multi-tenant approval and procurement application that can be configured
quickly for GreenLeaf. We understand the need for purchase requests, approvals and supplier onboarding across three
offices, with an integration to SAP S/4HANA.</p>

<h2>2. Proposed Solution and Implementation Approach</h2>
<p>QuickFlow is a web application with standard approval templates and a supplier portal. SAP connectivity is
planned through a middleware component; the middleware option is to be confirmed after we review GreenLeaf's SAP
landscape. Load testing has not yet been performed; we expect the platform to scale to the required user count
based on prior deployments.</p>

<h2>3. Timeline, Team Structure and Milestones</h2>
<p>Total duration is 14 weeks. The team has 6 people. No dated milestones are included beyond go-live in week 14.</p>
<table>
<tr><th>Role</th><th>Headcount</th><th>Responsibility</th></tr>
<tr><td>Project manager</td><td>1</td><td>Plan and reporting</td></tr>
<tr><td>Consultant</td><td>2</td><td>Configuration and testing</td></tr>
<tr><td>Developer</td><td>2</td><td>Templates and integration work</td></tr>
<tr><td>Trainer</td><td>1</td><td>End-user training</td></tr>
</table>

<h2>4. Price Table and Assumptions</h2>
<table>
<tr><th>Item</th><th>Amount (INR lakh)</th></tr>
<tr><td>Licence (year 1)</td><td>600</td></tr>
<tr><td>Implementation</td><td>560</td></tr>
<tr><td>Support (year 1)</td><td>140</td></tr>
<tr><td><b>Total</b></td><td><b>1,300</b></td></tr>
</table>
<p>Assumptions: support for years 2 and 3 is not included in this price; it is quoted at 18% of the annual licence
fee. SAP middleware licences and their implementation are not included. GST is excluded.</p>

<h2>5. Security, Compliance and Risk Controls</h2>
<p>BrightPath intends to pursue ISO 27001 certification once the platform is in production. Access control uses
username and password; multi-factor authentication is on the roadmap. Data is encrypted in line with industry
standards. We have no certifications at present and no independent audit reports. Audit logging is available
but retention periods are not specified.</p>
<p>Key risks: SAP middleware scope is undefined, the timeline assumes no major change requests, and the company
has not yet tested performance at scale.</p>

<h2>6. Support Model, Relevant Experience and References</h2>
<p>Support is by email during business hours (9am to 6pm, Monday to Friday). BrightPath was founded in 2023 and
has completed one small deployment for a 60-user logistics firm. No customer references are available at this
time.</p>
""",
)


NEXAWORKS = _page(
    "NexaWorks - Proposal for NexaFlow Suite",
    META,
    """
<h2>1. Executive Summary and Understanding of the Requirement</h2>
<p>NexaWorks proposes NexaFlow Suite, a modular, API-first procurement workflow platform. We understand GreenLeaf
needs approvals, supplier onboarding and invoice workflows for 500 users in three offices, integrated with SAP
S/4HANA and a supplier portal, live within 8 months.</p>

<h2>2. Proposed Solution and Implementation Approach</h2>
<p>NexaFlow uses a modular design: workflow, supplier management and SAP integration are separate modules behind
published REST APIs. The SAP connector is certified by the SAP partner programme. Delivery follows three phases,
each closed by a go/no-go gate: Phase 1 foundation and design, Phase 2 build and SAP integration test, Phase 3
pilot and regional rollout. Performance was validated at 1,500 concurrent users with a 99.9% availability SLA.</p>

<h2>3. Timeline, Team Structure and Milestones</h2>
<p>Total duration is 7 months, with a weekly plan shared through a common project tracker. Payments are linked to
milestones M1 to M4: M1 design approved (month 1), M2 SAP integration passed test (month 4), M3 pilot office live
(month 6), M4 full go-live and hypercare start (month 7).</p>
<table>
<tr><th>Role</th><th>Headcount</th><th>Responsibility</th></tr>
<tr><td>Engagement director and delivery lead</td><td>2</td><td>Governance, scope and risk</td></tr>
<tr><td>Solution architects</td><td>2</td><td>Design and SAP integration</td></tr>
<tr><td>Developers</td><td>4</td><td>Workflow and portal build</td></tr>
<tr><td>Test engineers</td><td>2</td><td>Functional, performance and security testing</td></tr>
<tr><td>Trainers and change lead</td><td>2</td><td>Training and adoption</td></tr>
</table>
<p>Total team size is 12 people. The risk register lists 9 items with owners, triggers and responses.</p>

<h2>4. Price Table and Assumptions</h2>
<table>
<tr><th>Item</th><th>Amount (INR lakh)</th></tr>
<tr><td>Licences (3 years)</td><td>720</td></tr>
<tr><td>Implementation (fixed price)</td><td>880</td></tr>
<tr><td>Training</td><td>120</td></tr>
<tr><td>Support (3 years)</td><td>580</td></tr>
<tr><td><b>Total</b></td><td><b>2,300</b></td></tr>
</table>
<p>The implementation is a fixed price. Change requests are priced at the rate card of INR 1.2 lakh per
person-week. Assumptions: GreenLeaf provides a SAP test system and a named product owner. GST is excluded.</p>

<h2>5. Security, Compliance and Risk Controls</h2>
<p>NexaWorks is ISO 27001:2022 certified (certificate available on request). SOC 2 Type II is in progress, with
the report expected in Q4 2026. Controls include SSO with MFA, role-based access reviewed quarterly, encryption
at rest and in transit, and audit logs retained for 3 years. Vulnerability scanning runs weekly and a third-party
penetration test is completed before each major release.</p>
<p>Principal risks and responses are listed in the 9-item register: SAP environment readiness (weekly readiness
check), scope creep (change board with fixed rate card), and key-person dependency (named deputies for each role).</p>

<h2>6. Support Model, Relevant Experience and References</h2>
<p>Critical issues receive 24x7 support with SLAs: P1 response in 30 minutes and restoration target 4 hours. A
customer success manager is assigned to GreenLeaf, and hypercare runs for 60 days after go-live. NexaWorks has
completed 14 deployments. Three named references are available: a grocery retailer (700 users, four countries),
a consumer goods company (SAP S/4HANA, 450 users) and a logistics provider (300 users, two regions).</p>
""",
)


ORBIT = _page(
    "Orbit Digital - Proposal for OrbitProcure",
    META,
    """
<h2>1. Executive Summary and Understanding of the Requirement</h2>
<p>Orbit Digital proposes OrbitProcure, a procurement platform with supplier onboarding, sourcing and contract
management modules. We understand GreenLeaf's need for a platform for 500 users across three offices and an
integration with SAP S/4HANA and a supplier portal.</p>

<h2>2. Proposed Solution and Implementation Approach</h2>
<p>OrbitProcure is a mature product with more than 40 deployments. For the SAP integration we will use
suitable connectors, to be finalised in discovery once GreenLeaf confirms its SAP version and custom objects.
The supplier portal is included as a standard module. Performance has been demonstrated at customer sites of
comparable size; a formal load test is proposed for the test phase.</p>

<h2>3. Timeline, Team Structure and Milestones</h2>
<p>Total duration is 8 months. The plan describes phases (discovery, build, test, deployment) but does not set
dated milestones; these will be agreed after discovery. The team has 11 people.</p>
<table>
<tr><th>Role</th><th>Headcount</th><th>Responsibility</th></tr>
<tr><td>Programme manager</td><td>1</td><td>Governance and reporting</td></tr>
<tr><td>Business analysts</td><td>2</td><td>Requirements and process design</td></tr>
<tr><td>Technical consultants</td><td>4</td><td>Configuration and integration</td></tr>
<tr><td>Testers</td><td>2</td><td>Test execution</td></tr>
<tr><td>Trainers</td><td>2</td><td>Training and support</td></tr>
</table>

<h2>4. Price Table and Assumptions</h2>
<table>
<tr><th>Item</th><th>Amount (INR lakh)</th></tr>
<tr><td>Licences (3 years)</td><td>800</td></tr>
<tr><td>Implementation</td><td>980</td></tr>
<tr><td>Training</td><td>140</td></tr>
<tr><td>Support (3 years)</td><td>630</td></tr>
<tr><td><b>Total</b></td><td><b>2,550</b></td></tr>
</table>
<p>Assumptions: implementation is time and materials within the estimated effort; connector licences are
extra if more than two SAP interfaces are required. GST is excluded.</p>

<h2>5. Security, Compliance and Risk Controls</h2>
<p>Orbit Digital states that it is ISO 27001 aligned and applies basic controls, including password policies and
role-based access. Data is backed up daily. Multi-factor authentication is available as an option. Audit trail
coverage and encryption details are described in general terms only; no certificate number or audit report is
provided.</p>
<p>Risks: integration scope is not yet fixed and may affect cost and timeline; the plan has no dated milestones
until discovery is complete.</p>

<h2>6. Support Model, Relevant Experience and References</h2>
<p>Support is available from 8am to 8pm, Monday to Saturday. Orbit Digital has operated for 15 years and has over
40 deployments, including awards for procurement technology. Five referenceable customers are available with
published outcomes, including a 22% reduction in purchase cycle time at a retail group and a 35% reduction in
supplier onboarding effort at a manufacturer.</p>
""",
)


PROPOSALS = {
    "Apex_Systems.pdf": APEX,
    "BrightPath_Tech.pdf": BRIGHTPATH,
    "NexaWorks.pdf": NEXAWORKS,
    "Orbit_Digital.pdf": ORBIT,
}


def build_pdf(html: str, path: Path) -> None:
    story = fitz.Story(html=html)
    writer = fitz.DocumentWriter(str(path))
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (48, 48, -48, -48)
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, html in PROPOSALS.items():
        path = OUT_DIR / filename
        build_pdf(html, path)
        with fitz.open(str(path)) as doc:
            print(f"wrote {path} ({doc.page_count} pages)")


if __name__ == "__main__":
    main()
