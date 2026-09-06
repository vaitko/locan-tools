# Security

If you find a vulnerability in this code or in the live service at locan.ai / api.locan.ai, please e-mail
**security@locan.ai** (or gintaras@locan.ai) with the details and a way to reproduce it. We answer within
a few days and fix confirmed issues before discussing them publicly.

Please do not run automated scanners or load tests against the live API — it is a free service on a
small budget, and the daily quotas exist so it stays free for everyone.

Things that are **not** vulnerabilities: the analytics tokens in `site/src/data/site.ts` (write-only keys
meant for browsers), the public API base URL, and infrastructure identifiers in the CloudFormation templates.
