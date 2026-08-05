<p align="center">
  <img src="solus.png" alt="Solus logo" width="160">
</p>

<h1 align="center">Solus</h1>

<p align="center">
  A Python wrapper that drives the Gemini web app through a real browser, so anyone can
  script conversations with Gemini without needing a paid API key.
</p>

## What it does

Solus uses [Playwright](https://playwright.dev/python/) to open Chrome, navigate to
[gemini.google.com](https://gemini.google.com/), and drive the chat UI exactly like a
human would: typing a prompt, pressing Enter, and reading back the rendered response.
There is no official Gemini API call involved — it's browser automation packaged behind
a simple client interface, which is what makes it usable without a paid API plan.

## Installation

```bash
pip install -e .
playwright install chromium
```

Requires Python 3.9+. The only runtime dependency is `playwright`.

## Quick start

```python
from solus import Solus

client = Solus()
print(client.send_message("What is the capital of Portugal?"))
client.quit()
```

`Solus` also works as a context-manager-free resource that cleans itself up automatically
via `atexit`, so `client.quit()` is optional but recommended for deterministic shutdown.

## Persistent sessions (staying logged in)

By default, every `Solus()` instance launches a fresh, throwaway browser profile, so
you'll be asked to log in to your Google account on every run. To persist your session
across runs, enable `persistent_session`:

```python
from solus import Solus

client = Solus(persistent_session=True)
client.send_message("Summarize this in one sentence: ...")
client.quit()
```

The first time you do this, a visible (non-headless) browser window opens so you can log
in manually. The session is saved to a local Chrome profile directory
(`~/.solus/chrome-profile` by default) and reused on subsequent runs — you won't need to
log in again unless the session expires. Pass `profile_dir="/custom/path"` to control
where that profile is stored.

## Full example

A small script that keeps a persistent session, asks a few follow-up questions in the
same conversation, and shuts down cleanly whether or not something goes wrong:

```python
from solus import Solus


def main():
    client = Solus(persistent_session=True, headless=True)

    questions = [
        "What is the capital of Portugal?",
        "What is that city's population?",
    ]

    try:
        for question in questions:
            answer = client.send_message(question)
            print(f"> {question}\n{answer}\n")
    finally:
        client.quit()


if __name__ == "__main__":
    main()
```

Because `persistent_session=True` reuses the saved Chrome profile, only the very first
run requires you to log in by hand — every run after that picks up the existing session.

## API reference

### `Solus(system_prompt=None, headless=True, channel="chrome", persistent_session=False, profile_dir=None)`

| Parameter            | Type          | Default    | Description                                                             |
|-----------------------|---------------|------------|---------------------------------------------------------------------------|
| `system_prompt`       | `str \| None` | `None`     | If given, sent as the first message right after the client is ready.      |
| `headless`            | `bool`        | `True`     | Run Chrome without a visible window.                                      |
| `channel`             | `str`         | `"chrome"` | Playwright browser channel to launch.                                     |
| `persistent_session`  | `bool`        | `False`    | Reuse a saved Chrome profile so login persists across runs.               |
| `profile_dir`         | `str \| None` | `None`     | Custom path for the persistent profile. Defaults to `~/.solus/chrome-profile`. |

### `client.send_message(prompt: str) -> str`

Sends `prompt` to Gemini and returns the assistant's reply as plain text once generation
finishes. Raises `ClosedError` if the client was already closed, or
`ResponseTimeoutError` if no response starts arriving within the configured timeout
(this usually means Gemini's DOM/selectors changed upstream).

### `client.quit()`

Closes the browser and stops the underlying Playwright driver. Idempotent — safe to call
more than once. Registered automatically via `atexit`, so it runs on normal interpreter
exit even if you forget to call it.

### Exceptions

All exceptions live under a common `SolusError` base, importable from the package root:

- `SolusError` — base exception for the library. Catching this alone covers both
  exceptions below.
- `ClosedError` — raised when calling `send_message` on a client that has already been
  closed via `quit()`.
- `ResponseTimeoutError` — raised when Gemini's response doesn't appear within the
  expected time window.

```python
from solus import Solus, SolusError, ClosedError, ResponseTimeoutError

client = Solus()
try:
    print(client.send_message("Hello"))
except SolusError as error:
    print(f"Solus failed: {error}")
finally:
    client.quit()
```

## Disclaimer

Solus automates Gemini's public web interface rather than calling an official API. This
is intended for personal scripting and experimentation by users without access to a paid
API plan. Automating a web UI may be subject to the target platform's Terms of Service —
use responsibly, keep request volume reasonable, and review Google's terms before
relying on this in anything beyond personal, low-volume use.
