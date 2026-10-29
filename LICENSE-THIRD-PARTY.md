# Third-Party Component Licenses

Pergel is distributed under multiple licenses. The core project code (under
`src/brand/`, `src/search/`, `src/router/`, `src/infra/`, `src/api/`,
`src/devtools/`, `src/net_lab/`, `tests/`) is MIT licensed (see LICENSE).

The following third-party components retain their own licenses:

## Chromium (BSD-3-Clause)

The desktop shell is Chromium-based. Chromium's own license and copyright
notices apply. "Chromium" and "Google Chrome" are trademarks of Google LLC.
This project is not affiliated with, sponsored by, or endorsed by Google.
Rebranding is limited to resource pack (`.pak`) editing and does not change
Chromium's original license rights.

## lightpanda (AGPL-3.0)

The automation/fetch layer uses the `lightpanda-io/browser` engine, which is
licensed under GNU AGPL-3.0. This repository does not claim ownership of the
engine; it is used as a client only. Per AGPL requirements, services offering
this engine over a network must make source code available.

## Other dependencies

For a detailed third-party license list, see component notes under `docs/rea/`
and package dependency manifests.

---

## Trademark Note

"Pergel" is the name of this project. There is no official connection,
sponsorship, or endorsement with Chromium or Google Chrome.

## Contributing

By submitting contributions to this repository, contributors accept the above
license terms.
