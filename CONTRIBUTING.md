# Contributing

Thanks for taking an interest. This is a small, deliberately boring tool: standard library only, deterministic output, and conservative defaults. Changes should keep it that way.

## Ground rules

1. **No real data, ever.** Do not commit exports, screenshots or examples that come from a real organisation, and do not use real group, permission or product names. The demo data is synthetic and uses generic `module.action` permission names. Pull requests containing real access data will be closed and the history asked to be rewritten.
2. **Standard library only** for the core package. Test and tooling dependencies are fine under the `dev` extra.
3. **Deterministic output.** The same inputs and parameters must give byte-identical files. Never iterate over a set or dict whose order matters without sorting, and never write timestamps into outputs.
4. **No silent privilege gain.** Any change to the design logic must keep the rule that a user's gain of access is either prevented or listed in `impact.csv`. There are tests for this; please extend them rather than loosen them.
5. **British English, plain tone.** No marketing language and no claims that are not backed by a run you can reproduce.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

## Changing behaviour

Output files under `examples/` are checked by a test, so a behaviour change needs the examples regenerated in the same commit:

```bash
cd examples
access-rat generate-demo --out demo-data
access-rat analyse --data demo-data --out demo-output
access-rat analyse --data demo-data --max-gain-share 1 --out demo-output-aggressive
cd ..
python -m pytest -q
```

If the numbers in `README.md` or `docs/worked-example.md` change, update them from the new `summary.json` files. Every figure in the documentation must come from an actual run. The screenshots can be regenerated with `python scripts/make_screenshots.py` (needs Playwright and Chromium).

## Pull request checklist

- [ ] Tests added or updated and passing
- [ ] Examples regenerated if output changed
- [ ] Documentation figures updated from real output
- [ ] No real data, names or credentials anywhere in the diff
- [ ] `docs/limitations.md` updated if the change alters what the tool does or does not decide

## Reporting security concerns

The tool reads local CSV files and makes no network calls. If you find a way for crafted input to cause harm, for example through the HTML report, please open a private security advisory on the repository rather than a public issue.
