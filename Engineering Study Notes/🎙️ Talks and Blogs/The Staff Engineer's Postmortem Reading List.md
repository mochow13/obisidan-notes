---
title: "The Staff Engineer's Postmortem Reading List"
aliases:
  - Engineering Incident Reading List
  - Distributed Systems Postmortems
  - Production Incident Case Studies
created: 2026-10-20
type: reading-list
status: in-progress
tags:
  - engineering
  - backend
  - distributed-systems
  - reliability
  - sre
  - postmortems
  - incident-management
  - staff-engineering
---
> [!abstract] Overview
> A curated collection of **34 engineering incident reports from approximately 25 companies**, plus **3 follow-up engineering analyses**.
>
> Primarily covering **2022–2026**, with older classics that every senior, staff, and principal backend engineer should study.
>
> **Goal:** Understand how production systems fail, why failures cascade, how teams recover, and how to design more resilient infrastructure.

## Reading Progress

- [ ] Part 1 — Essential reading (10 reports)
- [ ] Part 2 — Modern incidents (17 reports)
- [ ] Part 3 — Follow-up engineering analyses (3 articles)
- [ ] Part 4 — Timeless classics (7 reports)

---

# Part 1 — Essential Reading

> [!important] Start Here
> These 10 reports offer some of the most transferable lessons for senior and staff backend engineers.

## 1. AWS — US-East-1 DynamoDB / EC2 Cascading Outage (2025)

- [ ] Read postmortem

**Company:** Amazon Web Services  
**Year:** 2025  
**Topics:** `DNS` `Race Conditions` `Control Planes` `Cascading Failures` `Recovery`

**URL:** https://aws.amazon.com/message/101925/

### Summary
A latent race condition in DynamoDB's automated DNS system triggered widespread service disruption across several AWS services.

The incident demonstrated that restoring an initial failed dependency does not guarantee the immediate recovery of downstream systems.

### Key Lessons
- DNS is a critical infrastructure dependency.
- Latent race conditions can be activated by routine operations.
- Shared infrastructure creates correlated failure modes.
- Recovery across distributed dependencies can take significantly longer than fixing the original problem.
- Systems should be designed for dependency recovery, not just dependency failure.

---

## 2. Google Cloud — Global API Outage (2025)

- [ ] Read postmortem

**Company:** Google Cloud  
**Year:** 2025  
**Topics:** `Global Configuration` `Data Validation` `Null Pointers` `Thundering Herd` `Regional Isolation`

**URL:** https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW

### Summary
Invalid quota-policy data was replicated globally and caused crashes in a critical API-management component.

The widespread distribution of bad configuration data, combined with retry and recovery behavior, turned a software defect into a global disruption.

### Key Lessons
- Globally replicated configuration requires rigorous validation.
- Control-plane bugs can affect otherwise healthy regional infrastructure.
- Backoff and jitter are essential for safe recovery.
- Regional redundancy does not automatically provide regional isolation.
- Configuration propagation should have explicit blast-radius controls.

---

## 3. Cloudflare — November 18 Global Outage (2025)

- [ ] Read postmortem

**Company:** Cloudflare  
**Year:** 2025  
**Topics:** `Configuration Generation` `Database Permissions` `Blast Radius` `Traffic Processing`

**URL:** https://blog.cloudflare.com/18-november-2025-outage/

### Summary
A database permission change resulted in duplicate entries in a generated Bot Management feature file, contributing to widespread request-processing failures.

An internal data-generation issue propagated into infrastructure responsible for serving production traffic.

### Key Lessons
- Configuration and generated data should be treated like production code.
- Internal database changes can have unexpected downstream consequences.
- Data-generation pipelines require validation and size limits.
- Global deployment increases the consequences of hidden assumptions.
- Fail-safe behavior matters when traffic-processing components encounter invalid inputs.

---

## 4. Roblox — 73-Hour Outage (2022)

- [ ] Read postmortem

**Company:** Roblox  
**Year:** 2022 (incident in 2021)  
**Topics:** `Consul` `BoltDB` `Resource Contention` `Distributed Systems` `Disaster Recovery`

**URL:** https://about.roblox.com/newsroom/2022/01/roblox-return-to-service-10-28-10-31-2021

### Summary
A combination of Consul streaming behavior and BoltDB performance problems caused a catastrophic infrastructure failure.

The outage lasted approximately 73 hours, and dependencies within the monitoring and operational infrastructure complicated the recovery.

### Key Lessons
- Coordination systems are critical infrastructure.
- Resource contention can create unexpected cascading effects.
- Observability infrastructure should not depend entirely on the systems it monitors.
- Distributed system recovery can be substantially harder than failure detection.
- Architectural complexity affects operational recovery.

---

## 5. Atlassian — Accidental Deletion of Customer Sites (2022)

- [ ] Read postmortem

**Company:** Atlassian  
**Year:** 2022  
**Topics:** `Destructive Automation` `Data Recovery` `Backups` `Operational Safety` `Incident Communication`

**URL:** https://www.atlassian.com/blog/how-we-build/post-incident-review-april-2022-outage

### Summary
A maintenance script accidentally deleted hundreds of customer sites.

Some affected customers experienced restoration efforts lasting up to two weeks.

### Key Lessons
- Destructive automation requires strict safety controls.
- Administrative scripts should enforce blast-radius limits.
- Restore procedures need regular production-like testing.
- Large-scale recovery requires accurate dependency mapping.
- Customer communication is a core component of incident management.

---

## 6. GitHub — March Database Incidents (2022)

- [ ] Read postmortem

**Company:** GitHub  
**Year:** 2022  
**Topics:** `MySQL` `Database Contention` `Failover` `Capacity Planning` `Load Shedding`

**URL:** https://github.blog/news-insights/company-news/github-availability-report-march-2022/

### Summary
GitHub experienced repeated incidents involving critical MySQL infrastructure and insufficient database headroom.

The incidents demonstrated how database performance degradation can rapidly become a system-wide availability problem.

### Key Lessons
- Capacity headroom is a reliability feature.
- Database contention propagates into application availability.
- Load shedding can prevent cascading failures.
- Database failover needs careful operational design.
- Sharding and workload isolation reduce systemic risk.

---

## 7. Discord — Voice Infrastructure Cascading Failure (2026)

- [ ] Read postmortem

**Company:** Discord  
**Year:** 2026  
**Topics:** `Kubernetes` `Elixir` `Message Queues` `Cascading Overload` `Real-Time Infrastructure`

**URL:** https://discord.com/blog/behind-the-scenes-of-the-3-25-26-voice-outage

### Summary
A routine infrastructure change removed a significant amount of session-management capacity.

The resulting overload propagated into downstream voice infrastructure.

### Key Lessons
- Capacity reduction can trigger non-linear system behavior.
- Recovery traffic can overwhelm dependent services.
- Real-time architectures require careful overload handling.
- Queues and session-management services need explicit capacity limits.
- Graceful degradation should be designed before an incident.

---

## 8. CrowdStrike — Falcon Update / Windows Outage (2024)

- [ ] Read root-cause analysis

**Company:** CrowdStrike  
**Year:** 2024  
**Topics:** `Deployment Safety` `Content Validation` `Canary Releases` `Global Blast Radius` `Software Quality`

**URL:** https://www.crowdstrike.com/en-us/blog/channel-file-291-rca-available/

### Summary
A faulty content update caused widespread Windows system crashes.

The incident demonstrates how non-code updates can have consequences comparable to deploying faulty executable software.

### Key Lessons
- Configuration and content updates deserve rigorous testing.
- Canary deployments are essential for high-blast-radius software.
- Validation should cover malformed and unexpected input.
- Global rollout should be progressive and reversible.
- Recovery design matters when affected systems cannot boot normally.

---

## 9. Cloudflare — Workers KV Outage (2025)

- [ ] Read postmortem

**Company:** Cloudflare  
**Year:** 2025  
**Topics:** `Storage Systems` `Third-Party Dependencies` `Shared Infrastructure` `Fault Isolation`

**URL:** https://blog.cloudflare.com/cloudflare-service-outage-june-12-2025/

### Summary
A failure involving underlying storage infrastructure disrupted Workers KV and several dependent Cloudflare products.

It revealed how shared components can amplify the impact of an external infrastructure failure.

### Key Lessons
- Shared dependencies create hidden correlated risks.
- Multi-product platforms need strong failure isolation.
- Dependency redundancy must be tested against real outage scenarios.
- Cache and storage architecture directly affect availability.
- An independent recovery path can be as important as an independent data path.

---

## 10. Microsoft Azure — Front Door Outage (2024)

- [ ] Read post-incident review

**Company:** Microsoft Azure  
**Year:** 2024  
**Topics:** `Networking` `DDoS Protection` `Configuration Safety` `Routing` `Automation`

**URL:** https://azure.status.microsoft/status/history/?trackingId=KTY1-HW8

### Summary
A DDoS mitigation operation contributed to a network misconfiguration, causing packet loss and customer-facing connectivity failures.

### Key Lessons
- Defensive automation can itself become a failure source.
- Network configuration changes require strict validation.
- Security and reliability controls must be coordinated.
- Automated mitigation should have safety boundaries.
- Recovery should not depend on the same mechanism that introduced the failure.

---

# Part 2 — Modern Postmortems (2022–2026)

## A. Platform Failures, Cascading Outages, and Recovery

### 11. Datadog — March 8 Platform-Level Incident (2023)

- [ ] Read postmortem

**Topics:** `Kubernetes` `Networking` `Security Updates` `Correlated Failures` `Infrastructure Dependencies`

**URL:** https://www.datadoghq.com/blog/engineering/2023-03-08-deep-dive-into-platform-level-impact/

**Summary:** An automatic security update triggered a networking interaction that disconnected Kubernetes nodes across multiple cloud providers.

**Key Lessons:**
- Multi-cloud does not guarantee failure independence.
- Common software dependencies create correlated risks.
- Routine security updates require operational safeguards.
- Infrastructure-wide changes can defeat otherwise independent failure domains.

---

### 12. PagerDuty — Kafka Outages (2025)

- [ ] Read postmortem

**Topics:** `Kafka` `JVM` `Memory Exhaustion` `Transactional Outbox` `Feature Rollouts`

**URL:** https://www.pagerduty.com/eng/august-28-kafka-outages-what-happened-and-how-were-improving/

**Summary:** A new feature unintentionally created millions of Kafka producers, exhausting broker memory and disrupting dependent services.

**Key Lessons:**
- Small application changes can cause infrastructure-wide resource exhaustion.
- Kafka producer lifecycle management matters.
- Feature flags and rollouts need resource-level monitoring.
- Memory exhaustion can turn performance degradation into cascading outages.

---

### 13. OpenAI — Kubernetes Control-Plane Outage (2024)

- [ ] Read postmortem

**Topics:** `Kubernetes` `Telemetry` `Control Planes` `Observability` `Recovery`

**URL:** https://status.openai.com/incidents/01JMYB483C404VMPCW726E8MET/write-up

**Summary:** A telemetry deployment overwhelmed Kubernetes control planes, complicating both diagnosis and remediation.

**Key Lessons:**
- Observability systems can cause production outages.
- Excessive monitoring traffic can overload infrastructure components.
- Control planes require independent capacity protection.
- Incident remediation should remain possible when orchestration is unhealthy.

---

### 14. Vercel — AWS-Dependent Service Disruption (2025)

- [ ] Read postmortem

**Topics:** `AWS` `Caching` `Feature Flags` `Control Planes` `Dependency Isolation`

**URL:** https://vercel.com/blog/update-regarding-vercel-service-disruption-on-october-20-2025

**Summary:** An AWS outage exposed cascading problems involving caching and dependency on a feature-flag provider.

**Key Lessons:**
- Third-party SaaS dependencies can become availability bottlenecks.
- Feature-flag infrastructure is part of the production dependency graph.
- Serving planes should be isolated from control-plane failures.
- Cache behavior during infrastructure recovery needs deliberate design.

---

### 15. Render — Extended Service Disruption (2024)

- [ ] Read postmortem

**Topics:** `Stateful Infrastructure` `Storage` `AWS API Limits` `Fleet Restarts` `Recovery Capacity`

**URL:** https://render.com/blog/root-cause-analysis-extended-service-disruption-3-26-24

**Summary:** An unintended fleet-wide restart exposed disk attachment rate limits and prolonged recovery of PostgreSQL, Redis, and other stateful services.

**Key Lessons:**
- Recovery operations can encounter infrastructure API limits.
- Massive simultaneous restarts are fundamentally different from normal operation.
- Stateful workloads require special recovery planning.
- Disaster recovery capacity must be tested, not assumed.

---

### 16. Fly.io — Orchestration Outage (2024)

- [ ] Read postmortem

**Topics:** `Orchestration` `Control Planes` `Deployment Reliability` `Infrastructure Isolation`

**URL:** https://fly.io/infra-log/2024-10-26/

**Summary:** A fleet-wide orchestration failure disrupted deployments and machine-management operations.

**Key Lessons:**
- Running workloads should remain isolated from orchestration failures.
- Deployment control planes require independent recovery mechanisms.
- Fleet-wide operations have unique failure characteristics.
- Management-plane reliability is a distinct engineering problem.

---

## B. Databases, Data Loss, and Migrations

### 17. Figma — Redis / ElastiCache Disruptions (2022)

- [ ] Read postmortem

**Topics:** `Redis` `Pub/Sub` `ElastiCache` `CPU Saturation` `Scaling`

**URL:** https://www.figma.com/blog/postmortem-service-disruptions-on-june-6-and-7-2022/

**Summary:** An AWS ElastiCache issue under Redis Pub/Sub workloads caused CPU saturation. Adding capacity unexpectedly made the problem worse.

**Key Lessons:**
- Horizontal scaling can amplify certain bottlenecks.
- Resource exhaustion is not always solved by adding capacity.
- Managed services can expose surprising behavior under specific workloads.
- Performance scaling assumptions need realistic validation.

---

### 18. Linear — Production Data-Loss Incident (2024)

- [ ] Read postmortem

**Topics:** `PostgreSQL` `Migrations` `TRUNCATE CASCADE` `PITR` `Data Recovery`

**URL:** https://linear.app/now/linear-incident-on-jan-24th-2024

**Summary:** A PostgreSQL migration using `TRUNCATE ... CASCADE` deleted production data. Caching masked parts of the incident, while recovery required restoring data and reconstructing lost changes.

**Key Lessons:**
- Database migrations are high-risk production operations.
- Destructive SQL commands require strict safeguards.
- Caches can hide data corruption.
- Point-in-time recovery should be regularly tested.
- Event logs can provide valuable recovery mechanisms.

---

### 19. Supabase — Regional Infrastructure Outage (2026)

- [ ] Read postmortem

**Topics:** `AWS VPC` `Infrastructure Automation` `IAM` `Network Isolation` `Permissions`

**URL:** https://supabase.com/blog/supabase-incident-on-february-12-2026

**Summary:** An internal monitoring deployment inadvertently enabled AWS VPC Block Public Access across a region.

**Key Lessons:**
- Operational automation should follow least-privilege principles.
- Monitoring deployments can have infrastructure-wide consequences.
- IAM permission boundaries are reliability controls.
- Infrastructure changes need blast-radius restrictions.

---

### 20. Neon — Database Compute Startup Failures (2025)

- [ ] Read postmortem

**Topics:** `PostgreSQL` `Serverless Databases` `Query Planner` `Control Planes` `Resource Exhaustion`

**URL:** https://neon.com/blog/postmortem-delayed-start-compute-operations

**Summary:** A PostgreSQL query-plan regression in control-plane infrastructure contributed to capacity and IP allocation issues, delaying database compute startup.

**Key Lessons:**
- Control-plane database performance affects product availability.
- Query-plan regressions can become infrastructure-wide incidents.
- Serverless database architectures introduce specialized recovery dependencies.
- Resource exhaustion can propagate across provisioning systems.

---

### 21. GitHub — Git Database Availability Issues (2023)

- [ ] Read postmortem

**Topics:** `Git Storage` `Replication` `Failover` `Configuration Changes` `Rollback`

**URL:** https://github.blog/news-insights/company-news/addressing-githubs-recent-availability-issues/

**Summary:** Configuration changes and failover complications contributed to Git database disruptions, with rollback proving more difficult than expected.

**Key Lessons:**
- Rollback procedures must be independently verified.
- Stateful system failover is operationally complex.
- Replication architecture affects recovery behavior.
- Configuration changes need explicit failure-domain awareness.

---

## C. Dependencies, Change Safety, and Security

### 22. CircleCI — Security Incident (2023)

- [ ] Read incident report

**Topics:** `CI/CD Security` `Secrets` `Credential Rotation` `Supply Chain` `Incident Response`

**URL:** https://circleci.com/blog/jan-4-2023-incident-report/

**Summary:** A security incident required broad credential rotation and highlighted the sensitive trust relationships between CI/CD platforms and customer environments.

**Key Lessons:**
- CI/CD systems are high-value security dependencies.
- Secrets exposure has a broad downstream blast radius.
- Credential rotation requires robust operational processes.
- Security incidents and reliability incidents share many coordination challenges.

---

### 23. Tailscale — TLS Certificate Outage (2024)

- [ ] Read postmortem

**Topics:** `TLS` `Certificates` `IPv6` `Monitoring` `Dependency Management`

**URL:** https://tailscale.com/blog/tls-outage-20240307

**Summary:** Certificate renewal failed because of an unusual interaction involving hosting and IPv6 configuration. Existing monitoring failed to detect the problem.

**Key Lessons:**
- Certificate automation needs end-to-end monitoring.
- Health checks should validate actual customer-facing paths.
- Hidden infrastructure assumptions eventually become incidents.
- Simple dependencies can produce complicated failures.

---

### 24. Cloudflare — Control-Plane and Analytics Outage (2023)

- [ ] Read postmortem

**Topics:** `Control Planes` `Data Centers` `Disaster Recovery` `Failover` `Redundancy`

**URL:** https://blog.cloudflare.com/post-mortem-on-cloudflare-control-plane-and-analytics-outage/

**Summary:** A major data-center incident disrupted administrative services and analytics, exposing weaknesses in failover arrangements.

**Key Lessons:**
- Disaster recovery must be tested under realistic conditions.
- Backup infrastructure is only useful if it can take over.
- Control-plane availability and data-plane availability are different concerns.
- Infrastructure dependency mapping is essential.

---

### 25. Cloudflare — DNS Resolver Outage (2025)

- [ ] Read postmortem

**Topics:** `DNS` `BGP` `Routing` `Configuration Management` `Latent Defects`

**URL:** https://blog.cloudflare.com/cloudflare-1-1-1-1-incident-on-july-14-2025/

**Summary:** A dormant configuration error was activated by a subsequent change, resulting in the withdrawal of resolver routes.

**Key Lessons:**
- Latent configuration bugs can remain undetected for long periods.
- Routing changes can have global consequences.
- Configuration dependencies should be explicit and testable.
- Network rollouts require progressive safety controls.

---

### 26. Vercel — Edge Middleware Outage (2024)

- [ ] Read postmortem

**Topics:** `Edge Computing` `Third-Party Dependencies` `Global Configuration` `Resilience`

**URL:** https://vercel.com/blog/update-regarding-vercel-service-disruption-on-august-7-2024

**Summary:** An upstream provider entered an erroneous global configuration state, causing an Edge Middleware disruption.

**Key Lessons:**
- Managed infrastructure does not eliminate dependency risk.
- Global configuration errors can undermine regional redundancy.
- Independent mitigation strategies are valuable.
- Third-party service failure modes should be explicitly modeled.

---

### 27. Linear — Permission Boundary Incident (2026)

- [ ] Read incident analysis

**Topics:** `Authorization` `Multi-Tenancy` `Variable Shadowing` `Performance Optimizations` `Data Isolation`

**URL:** https://linear.app/now/linear-incident-on-mar-24th-2026

**Summary:** A variable-shadowing bug introduced during a performance optimization bypassed permission filtering for private team data.

**Key Lessons:**
- Authorization logic is a critical security boundary.
- Performance optimizations can accidentally violate access-control invariants.
- Multi-tenant systems require systematic isolation testing.
- Code review and testing should prioritize security-sensitive data flows.

---

# Part 3 — Follow-Up Engineering Analyses

> [!tip] Go Beyond Root Cause
> Understanding why an incident happened is useful. Understanding how an organization changed its architecture and operating practices afterward is even more valuable.

## 28. Datadog — Deep Dive into Incident Response (2023)

- [ ] Read analysis

**Topics:** `Incident Command` `Coordination` `Communication` `Incident Management`

**URL:** https://www.datadoghq.com/blog/engineering/2023-03-08-deep-dive-into-incident-response/

**Summary:** Explains how hundreds of engineers coordinated diagnosis, recovery, and communications during a major platform outage.

**Key Lessons:**
- Large incidents require organizational coordination.
- Incident command structures reduce communication overhead.
- Clear ownership accelerates recovery.
- Good incident management is a technical leadership skill.

**Related:** [[#11. Datadog — March 8 Platform-Level Incident (2023)]]

---

## 29. Cloudflare — Rearchitecting Workers KV for Redundancy (2025)

- [ ] Read architectural follow-up

**Topics:** `Storage Architecture` `Redundancy` `Dependency Isolation` `Resilience Engineering`

**URL:** https://blog.cloudflare.com/rearchitecting-workers-kv-for-redundancy/

**Summary:** Explains architectural improvements made to reduce dependency risk and improve Workers KV resilience.

**Key Lessons:**
- Postmortem actions should address systemic architectural weaknesses.
- Redundancy needs careful failure-mode analysis.
- Reliability improvements often require substantial design changes.
- Removing shared failure points improves resilience across products.

**Related:** [[#9. Cloudflare — Workers KV Outage (2025)]]

---

## 30. Render — Surviving the AWS October Outage (2025)

- [ ] Read analysis

**Topics:** `Cloud Resilience` `Fault Isolation` `Serving Planes` `Recovery Architecture`

**URL:** https://render.com/blog/how-render-services-stayed-up-during-the-aws-october-outage

**Summary:** Examines why existing Render services largely remained available during a major AWS disruption, while some management and provisioning operations experienced degradation.

**Key Lessons:**
- Existing workloads should not depend on the constant availability of provisioning systems.
- Serving-plane isolation reduces cloud-provider failure exposure.
- Graceful degradation is an architectural capability.
- Reliability should be evaluated at the dependency boundary, not just the service boundary.

---

# Part 4 — Timeless Classics

> [!important] Required Reading
> These reports are older but remain foundational to understanding modern distributed systems and production reliability.

## 31. Meta / Facebook — October 4 Global Outage (2021)

- [ ] Read postmortem

**Topics:** `BGP` `DNS` `Networking` `Circular Dependencies` `Disaster Recovery`

**URL:** https://engineering.fb.com/2021/10/05/networking-traffic/outage-details/

### Summary
A backbone configuration change disconnected Facebook's data centers from the internet.

The network disruption affected DNS and internal tools required for recovery, making remediation significantly more difficult.

### Key Lessons
- Infrastructure dependencies can become circular.
- DNS and BGP failures can disable entire platforms.
- Recovery tools must work when primary infrastructure is unavailable.
- Physical and operational access are essential parts of resilience.
- Global networks require strict configuration safeguards.

---

## 32. Fastly — June 8 Global CDN Outage (2021)

- [ ] Read postmortem

**Topics:** `CDN` `Latent Bugs` `Configuration Safety` `Global Rollouts` `Incident Recovery`

**URL:** https://www.fastly.com/blog/summary-of-june-8-outage

### Summary
A valid customer configuration triggered a previously undiscovered software defect, causing widespread CDN disruption.

### Key Lessons
- Valid inputs can expose latent implementation bugs.
- Globally distributed configuration requires careful safeguards.
- Faulty configuration should not cause infrastructure-wide failure.
- Fast detection and rollback drastically reduce incident duration.
- Global platforms need mechanisms to limit rollout blast radius.

---

## 33. GitLab — Production Database Deletion (2017)

- [ ] Read postmortem

**Topics:** `PostgreSQL` `Backups` `Replication` `Human Error` `Disaster Recovery`

**URL:** https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/

### Summary
A production database directory was accidentally deleted during maintenance.

The incident revealed that several backup and replication safeguards were ineffective.

### Key Lessons
- Having backups does not mean being able to restore.
- Backup restoration should be tested continuously.
- Production operations require safeguards against destructive commands.
- Human error should be anticipated in system design.
- Recovery time objectives must be validated empirically.

> [!quote] Core Principle
> A backup that has never been restored is an assumption, not a recovery strategy.

---

## 34. GitHub — October 21 MySQL Outage (2018)

- [ ] Read postmortem

**Topics:** `MySQL` `Network Partitions` `Replication` `Consistency` `Failover`

**URL:** https://github.blog/news-insights/company-news/oct21-post-incident-analysis/

### Summary
A network partition caused database failovers and inconsistent primary/replica states.

Restoring connectivity did not immediately restore service because the database topology and replicated data required careful reconciliation.

### Key Lessons
- Network partitions are unavoidable distributed-system failure modes.
- Failover automation can introduce consistency risks.
- Database recovery may require manual reconciliation.
- Availability and consistency tradeoffs become concrete during incidents.
- Replication topology influences recovery complexity.

---

## 35. Cloudflare — Catastrophic Regex Outage (2019)

- [ ] Read postmortem

**Topics:** `Regular Expressions` `CPU Exhaustion` `Algorithmic Complexity` `WAF` `Global Deployment`

**URL:** https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/

### Summary
A Web Application Firewall rule containing a catastrophically inefficient regular expression exhausted CPU resources across Cloudflare's global edge network.

### Key Lessons
- Algorithmic complexity is a production reliability concern.
- Configuration changes can be as dangerous as binary deployments.
- Test data must cover pathological inputs.
- Global rollout requires staged deployment.
- Kill switches and rollback mechanisms are critical.

---

## 36. AWS S3 — February 28 Service Disruption (2017)

- [ ] Read postmortem

**Topics:** `Operational Automation` `Capacity` `Recovery` `Administrative Safety` `Infrastructure Dependencies`

**URL:** https://aws.amazon.com/message/41926/

### Summary
An incorrect input to an operational command removed more S3 subsystem capacity than intended.

Restart and recovery dependencies prolonged the service disruption.

### Key Lessons
- Administrative tools should enforce strict operational limits.
- Recovery from large-scale component loss needs dedicated design.
- System startup dependencies affect recovery time.
- Routine operations can cause catastrophic outages without safeguards.
- Blast-radius limits should be embedded in automation.

---

## 37. Knight Capital — Trading System Failure (2012)

- [ ] Read incident analysis

**Topics:** `Deployment Verification` `Dead Code` `Risk Controls` `Kill Switches` `Operational Safety`

**URL:** https://www.sec.gov/newsroom/press-releases/2013-222

### Summary
An inconsistent software deployment activated obsolete trading functionality, resulting in uncontrolled trading and enormous financial losses.

### Key Lessons
- Deployments require verification across every instance.
- Dormant code can create unexpected operational risks.
- Automated systems need independent safety controls.
- Kill switches should exist before production emergencies.
- Small deployment mistakes can have disproportionate consequences.

---

# Part 5 — Study by Failure Mode

Use this section when you want to deepen your understanding of a particular distributed-systems problem.

## Cascading Failures and Overload

- [ ] [[#1. AWS — US-East-1 DynamoDB / EC2 Cascading Outage (2025)]]
- [ ] [[#4. Roblox — 73-Hour Outage (2022)]]
- [ ] [[#7. Discord — Voice Infrastructure Cascading Failure (2026)]]
- [ ] [[#12. PagerDuty — Kafka Outages (2025)]]
- [ ] [[#17. Figma — Redis / ElastiCache Disruptions (2022)]]

**Questions:**
- How did the original failure propagate?
- Were retries or queues amplifying load?
- Could load shedding have prevented the cascade?
- What prevented graceful degradation?

## Database Reliability and Data Recovery

- [ ] [[#6. GitHub — March Database Incidents (2022)]]
- [ ] [[#18. Linear — Production Data-Loss Incident (2024)]]
- [ ] [[#20. Neon — Database Compute Startup Failures (2025)]]
- [ ] [[#33. GitLab — Production Database Deletion (2017)]]
- [ ] [[#34. GitHub — October 21 MySQL Outage (2018)]]

**Questions:**
- What was the actual recovery point objective (RPO)?
- What was the actual recovery time objective (RTO)?
- Were backups and replication independent?
- Did failover introduce consistency problems?
- How was data integrity verified after restoration?

## Control-Plane and Infrastructure Failures

- [ ] [[#2. Google Cloud — Global API Outage (2025)]]
- [ ] [[#13. OpenAI — Kubernetes Control-Plane Outage (2024)]]
- [ ] [[#16. Fly.io — Orchestration Outage (2024)]]
- [ ] [[#24. Cloudflare — Control-Plane and Analytics Outage (2023)]]
- [ ] [[#31. Meta / Facebook — October 4 Global Outage (2021)]]

**Questions:**
- Could serving traffic continue without the control plane?
- Did recovery require a functioning control plane?
- Which shared services caused correlated failures?
- Were the recovery mechanisms independent of the failure?

## Configuration and Deployment Safety

- [ ] [[#3. Cloudflare — November 18 Global Outage (2025)]]
- [ ] [[#8. CrowdStrike — Falcon Update / Windows Outage (2024)]]
- [ ] [[#19. Supabase — Regional Infrastructure Outage (2026)]]
- [ ] [[#25. Cloudflare — DNS Resolver Outage (2025)]]
- [ ] [[#32. Fastly — June 8 Global CDN Outage (2021)]]
- [ ] [[#35. Cloudflare — Catastrophic Regex Outage (2019)]]
- [ ] [[#37. Knight Capital — Trading System Failure (2012)]]

**Questions:**
- Could the change have been validated before production?
- Was the rollout progressive?
- What was the expected blast radius?
- Was rollback possible and reliable?
- Did configuration changes receive the same rigor as code changes?

## Dependency Isolation and Resilience

- [ ] [[#9. Cloudflare — Workers KV Outage (2025)]]
- [ ] [[#11. Datadog — March 8 Platform-Level Incident (2023)]]
- [ ] [[#14. Vercel — AWS-Dependent Service Disruption (2025)]]
- [ ] [[#26. Vercel — Edge Middleware Outage (2024)]]
- [ ] [[#29. Cloudflare — Rearchitecting Workers KV for Redundancy (2025)]]
- [ ] [[#30. Render — Surviving the AWS October Outage (2025)]]

**Questions:**
- Were apparently independent systems sharing a dependency?
- Could the platform serve traffic during dependency failure?
- Were circuit breakers, timeouts, and fallbacks effective?
- Did redundancy truly eliminate a failure mode or merely move it?

## Operational Excellence and Incident Leadership

- [ ] [[#5. Atlassian — Accidental Deletion of Customer Sites (2022)]]
- [ ] [[#15. Render — Extended Service Disruption (2024)]]
- [ ] [[#23. Tailscale — TLS Certificate Outage (2024)]]
- [ ] [[#28. Datadog — Deep Dive into Incident Response (2023)]]
- [ ] [[#36. AWS S3 — February 28 Service Disruption (2017)]]

**Questions:**
- How quickly was the incident detected?
- What slowed down diagnosis?
- Did teams have clear roles and decision-making authority?
- Were operational tools safe and sufficiently tested?
- Which improvements reduce both incident likelihood and recovery time?

---

# Part 6 — A Four-Week Reading Plan

> [!tip] Recommended
> A practical starting sequence that prioritizes different failure classes instead of reading many similar incidents back-to-back.

## Week 1 — Database Reliability and Disaster Recovery

- [ ] GitHub 2018 — MySQL partition and failover
- [ ] GitLab 2017 — Production database deletion
- [ ] Linear 2024 — PostgreSQL migration data loss

**Focus:** Consistency, replication, backup verification, recovery procedures.

## Week 2 — Distributed Systems and Cascading Failures

- [ ] Roblox 2022 — Consul infrastructure failure
- [ ] Datadog 2023 — Platform-wide networking incident
- [ ] PagerDuty 2025 — Kafka resource exhaustion

**Focus:** Coordination, overload, failure propagation, dependency isolation.

## Week 3 — Configuration, Deployment, and Control Planes

- [ ] Google Cloud 2025 — Global API outage
- [ ] Cloudflare 2025 — November global outage
- [ ] OpenAI 2024 — Kubernetes control-plane outage

**Focus:** Configuration safety, change management, control-plane robustness.

## Week 4 — Architecture and Staff-Level Incident Leadership

- [ ] AWS 2025 — DynamoDB / EC2 cascading outage
- [ ] Atlassian 2022 — Site deletion and disaster recovery
- [ ] Datadog 2023 — Incident response coordination
- [ ] Cloudflare 2025 — Rearchitecting Workers KV

**Focus:** Blast-radius design, recovery architecture, cross-team coordination, systemic improvements.

---

# Part 7 — Postmortem Analysis Framework

> [!question] What Should a Staff Engineer Extract from Every Incident?
> Don't just memorize the root cause. Understand the conditions that allowed the incident to happen and why recovery was difficult.

For each report, answer the following questions.

## 1. Trigger

- What immediate event triggered the incident?
- Was it a deployment, configuration change, infrastructure failure, or traffic pattern?
- Was the trigger expected to be safe?

## 2. Latent Conditions

- What preexisting architectural weaknesses contributed?
- Which assumptions were incorrect?
- Was technical debt involved?
- Why hadn't the weakness caused an incident previously?

## 3. Blast Radius

- Which components were affected?
- Why did the failure propagate?
- Were there shared dependencies?
- What failure-domain boundaries were crossed?

## 4. Detection and Diagnosis

- How was the incident first detected?
- Did observability reveal the actual problem?
- Were alerts actionable?
- Which signals were misleading or missing?

## 5. Mitigation and Recovery

- What stopped the immediate failure?
- What slowed recovery?
- Did retries, queues, caches, or control planes complicate remediation?
- Could recovery have been performed without the affected infrastructure?

## 6. Corrective Actions

- Which changes were tactical?
- Which changes addressed architectural weaknesses?
- Were meaningful safeguards added?
- How can effectiveness be measured?

## 7. Organizational Lessons

- Were ownership boundaries clear?
- Did communication help or hinder recovery?
- Were incident roles defined?
- Did organizational structure contribute to technical failure?

## 8. Transferability

- Could the same failure mode occur in our systems?
- Which architectural assumptions should we revisit?
- What operational safeguards are missing?
- Which lessons would justify a technical roadmap investment?

---

# Part 8 — Reusable Incident Study Template

Copy this template when taking notes on an individual incident.

## Incident: <Company / Incident Name>

**Source:**  
**Incident Date:**  
**Report Date:**  
**Severity:**  
**Duration:**  
**Systems Affected:**  
**Failure Categories:**  

### Executive Summary

<!-- Explain the incident in 3–5 sentences. -->

### Architecture Before the Incident

<!-- Describe the relevant system and its dependencies. -->

### Trigger

<!-- What immediate event started the failure? -->

### Timeline

| Time | Event | Impact |
|------|-------|--------|
| | | |

### Root Cause

<!-- Describe the underlying technical defect or failure. -->

### Contributing Factors

<!-- Which design decisions, assumptions, or operational practices amplified the incident? -->

### Blast Radius

<!-- Explain how the failure propagated across services, regions, or dependencies. -->

### Detection and Response

<!-- How was it detected? How did the team respond? -->

### Recovery

<!-- How was service restored? What complicated recovery? -->

### Corrective Actions

| Action | Type | Expected Benefit |
|--------|------|------------------|
| | Prevention | |
| | Detection | |
| | Mitigation | |
| | Recovery | |

### Staff-Level Takeaways

1.
2.
3.

### Applicability to Our Systems

<!-- Where could similar failure modes exist in our infrastructure? -->

### Follow-Up Questions

- [ ] 
- [ ] 
- [ ] 

---

# Final Takeaways

The strongest lessons across these incidents are:

1. **Failures are rarely caused by one bug.** They emerge from interacting technical and organizational conditions.
2. **Redundancy is not the same as independence.** Multiple regions, replicas, or providers may still share critical dependencies.
3. **Recovery is a separate engineering problem.** A system that survives isolated component failures may still be extremely difficult to restore after a large-scale disruption.
4. **Configuration is production code.** Feature flags, routing policies, database migrations, and security updates deserve deployment safeguards.
5. **Backups are not recovery until restoration is tested.** Actual recovery time and data integrity matter more than theoretical backup coverage.
6. **Control planes should not be required to keep existing workloads serving traffic.** Failure to separate management from serving infrastructure can expand outages.
7. **Observability must survive the incidents it diagnoses.** Monitoring systems and telemetry pipelines can themselves become failure sources.
8. **Large-scale automated operations require enforced blast-radius limits.** Human mistakes should not be able to destroy entire fleets or datasets.
9. **Incident response is an engineering capability.** Coordination, ownership, communication, and decision-making materially affect outage duration.
10. **The best postmortems produce architectural change.** A corrective action should eliminate or contain a class of failures, not merely prevent the exact same sequence of events.

> [!quote] Core Engineering Principle
> The most resilient systems aren't those that never fail. They're those that limit failure propagation, degrade gracefully, and can be recovered predictably.

---

# References and Further Reading

For ongoing study, follow these original engineering sources:

- [Cloudflare Blog](https://blog.cloudflare.com/)
- [AWS Post-Event Summaries](https://aws.amazon.com/premiumsupport/technology/pes/)
- [Google Cloud Service Health](https://status.cloud.google.com/)
- [GitHub Engineering Blog](https://github.blog/)
- [Meta Engineering](https://engineering.fb.com/)
- [Datadog Engineering](https://www.datadoghq.com/blog/engineering/)
- [Discord Engineering](https://discord.com/category/engineering)
- [Atlassian Engineering](https://www.atlassian.com/blog/how-we-build)
- [Vercel Blog](https://vercel.com/blog)
- [Render Blog](https://render.com/blog)
- [Fly.io Infrastructure Log](https://fly.io/infra-log/)
- [Linear Now](https://linear.app/now)
- [Supabase Blog](https://supabase.com/blog)
- [Neon Blog](https://neon.com/blog)
- [PagerDuty Engineering](https://www.pagerduty.com/eng/)
- [Tailscale Blog](https://tailscale.com/blog)
- [OpenAI Status](https://status.openai.com/)
- [CircleCI Blog](https://circleci.com/blog/)
- [GitLab Blog](https://about.gitlab.com/blog/)
- [Fastly Blog](https://www.fastly.com/blog)

## Related Topics

- [[Distributed Systems]]
- [[Site Reliability Engineering]]
- [[Incident Management]]
- [[Database Reliability]]
- [[Disaster Recovery]]
- [[Capacity Planning]]
- [[Observability]]
- [[Change Management]]
- [[Staff Engineering]]
- [[System Design]]

#engineering #distributed-systems #sre #reliability #postmortems #staff-engineering