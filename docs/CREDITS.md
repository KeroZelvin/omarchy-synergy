# Attribution and submission routes

The included bridge patches are based on [iamnarayana/wayland-kdeconnect-fix](https://github.com/iamnarayana/wayland-kdeconnect-fix) at `ea55f66c8238235983d60d381bf2abe1fed50043`, forked from [gfhdhytghd/hypr-kdeconnect-fix](https://github.com/gfhdhytghd/hypr-kdeconnect-fix). Its original MIT license, copyright and source history remain intact.

[tedwardd's community patch](https://gist.github.com/tedwardd), titled `deskflow-remote-desktop-fix.patch`, was a reference for the EIS/keyboard compatibility investigation. It was not applied wholesale. In particular, this series does not adopt blanket empty-app-ID acceptance or claim clipboard support in a backend that does not implement it. Credit for identifying and publishing those compatibility observations belongs to that contributor.

The [Omarchy Synergy/Deskflow community discussion](https://github.com/omacom/omarchy/discussions/10097) supplied the initial setup context. This repository links that discussion and supplies its own setup guide; the separate proposed manual PR is not included here.

The clipboard companion was written separately as Python glue over wl-clipboard and SSH; it was not forked from ssh-clipboard or an existing project named Clipboard Companion. It has its own [MIT license](../LICENSE). [Deskflow's current position on wl-clipboard fallback](https://github.com/deskflow/deskflow/issues/10315#issuecomment-6339920489) is why this candidate is prepared as a standalone companion rather than a core fallback PR.

A separate Synergy 3 layout report is prepared outside this repository and directed to [Synergy product support](https://support.symless.com/hc/en-us/articles/360020995737-Contacting-our-support-team). Synergy's [repository signpost](https://github.com/symless/synergy) directs community core contributions to Deskflow; the generator examined here belongs to the Synergy 3 service. No vendor source or binaries are redistributed.

OpenAI Codex (GPT-6) assisted with investigation, changes, documentation and tests. Interactive hardware acceptance was performed by the system owner. Maintainer review, publication and acceptance of the cleaned candidate remain separate steps.
