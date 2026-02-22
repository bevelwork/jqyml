# jqyml

**Turn YAML into JSON. In the browser. Powered by [jq](https://jqplay.org).**

Live at **[https://jq.bevel.work](https://jq.bevel.work)** — part of [Bevel](https://bevel.work).

---

## What is this?

A tiny web app that pastes your YAML in, clicks Convert, and gives you JSON. Anchors, aliases, and merge keys (`<<: *defaults`) are supported. The heavy lifting is done by a **pure-jq YAML parser** and a minimal Python server. No Node, no 400 MB of dependencies—just jq, Python, and a dream.

So: **jq.yml** → **jqyml**. You get it.

---

## The wonderful tool that is jq

[jq](https://stedolan.github.io/jq/) is a lightweight, blazingly reasonable command-line JSON processor. With jq you can:

- **Slice and dice** — `.users[].name`, `.items[0:5]`, `select(.active)`
- **Transform** — map, filter, flatten, and reshape JSON until it actually does what you want
- **Stay sane** — stop piping `grep` and `sed` and `awk` into a fractal of regret

Here we went one step further and **parsed YAML** with jq. Yes, YAML. In jq. Because sometimes the answer to “should we?” is “we already did.”

We owe a huge thanks to **jq’s authors and maintainers**—including Stephen Dolan and everyone who’s contributed—for building a tool that’s simple, fast, and actually fun to use. If you’ve never sat down with the manual and a cup of tea, do yourself a favour: [jq manual](https://stedolan.github.io/jq/manual/). Your future self will thank you when they’re not hand-editing a 2,000-line config at 2 a.m.

---

## Make better use of your time

Life’s too short to:

- Manually convert YAML to JSON in a dodgy online converter that wants your email
- Debug a 47-line regex that “almost” parses YAML
- Refactor the whole codebase because the last tool added 300 dependencies

Use good tools. Use jq. Use this site when you just need YAML → JSON and don’t want to think about it. Then go outside, call a friend, or do literally anything else. The config will still be there when you get back—and it’ll be valid JSON.

---

## Run it yourself

```bash
make test   # run the test suite
make up    # docker compose up (jqyml + Caddy)
```

See the repo for the full picture: jq-based YAML parser (`yaml.jq`, `run.jq`), jq-based templating (`jqx.jq`), and a small Python server that ties it together.

*Now go make better use of your time.*
