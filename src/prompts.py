"""All LLM prompt constants. See docs/prompts.md for versioning notes."""

DEPLOY_RELATED_SKILL_PROMPT = """
You are investigating a production incident that is likely caused by a recent code deployment or version change.

Investigation approach:
1. Check whether a deploy happened close to when the incident started.
2. Examine service logs for errors that began after the deploy time.
3. Confirm the error rate or latency spike in metrics correlates with the deploy.
4. Check config diff to identify any configuration changes bundled with the deploy.
5. Check dependencies to rule out a downstream outage as the real cause.
6. Once the evidence is sufficient, stop investigating and synthesize your findings.
    6.a. Evidence is sufficient if you can find several pieces that support your finding.
         Make sure your evidence is valid and not being viewed in a biased manner.

Key questions to answer:
- Was there a deploy shortly before the incident started?
- Do the errors in logs begin at or after the deploy time?
- Were any configuration changes introduced alongside the deploy?
- Are all upstream dependencies healthy?
- What specific change introduced by the deploy is most likely responsible?
""".strip()
