# What

- Admin-only `/test` pull-request comment runs a live extract against a real model.
- The workflow checks out the default branch only; it never executes pull-request code with secrets.
- Default `pytest` still skips that test unless `TENSEMEM_LIVE=1` and `OPENAI_API_KEY` are set.

# Why

Pull-request CI should stay deterministic and free of model calls. Maintainers still need an on-demand integration check of the extract path on a fixed chat, without giving a privileged `issue_comment` workflow the pull request's tree.
