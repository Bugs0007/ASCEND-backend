"""
GET /api/analytics/decay/ — projects, cert domains and applications
untouched for >= DECAY_DAYS (14) days. This is an earlier, softer warning
than the 21-day funnel ghost rule (core.analytics.funnel) — different
constant, different purpose: decay flags things worth a nudge, ghost
reclassifies a stalled application for funnel reporting.
"""
from django.utils import timezone

from core.constants import DECAY_DAYS
from core.models import Application, CertDomain, Project


def _project_last_touch(project):
    candidates = [project.updated_at.date()]
    last_milestone = project.milestones.order_by("-updated_at").first()
    if last_milestone is not None:
        candidates.append(last_milestone.updated_at.date())
    return max(candidates)


def compute(as_of=None, projects_qs=None, cert_domains_qs=None, applications_qs=None):
    as_of = as_of or timezone.localdate()
    projects_qs = projects_qs if projects_qs is not None else Project.objects.all()
    cert_domains_qs = cert_domains_qs if cert_domains_qs is not None else CertDomain.objects.all()
    applications_qs = applications_qs if applications_qs is not None else Application.objects.all()

    stale_projects = []
    for project in projects_qs:
        last_touch = _project_last_touch(project)
        days = (as_of - last_touch).days
        if days >= DECAY_DAYS:
            stale_projects.append({"code": project.code, "name": project.name, "days_untouched": days})

    stale_cert_domains = []
    for domain in cert_domains_qs:
        if domain.last_studied is None:
            days = None
            stale = True
        else:
            days = (as_of - domain.last_studied).days
            stale = days >= DECAY_DAYS
        if stale:
            stale_cert_domains.append(
                {
                    "cert_code": domain.cert_code,
                    "domain_no": domain.domain_no,
                    "name": domain.name,
                    "days_untouched": days,
                }
            )

    stale_applications = []
    for app in applications_qs:
        if app.stage not in Application.IN_FLIGHT_STAGES:
            continue
        reference = app.last_update or app.applied_on
        days = (as_of - reference).days
        if days >= DECAY_DAYS:
            stale_applications.append(
                {"company": app.company, "role": app.role, "days_untouched": days}
            )

    return {
        "decay_days": DECAY_DAYS,
        "projects": stale_projects,
        "cert_domains": stale_cert_domains,
        "applications": stale_applications,
    }
