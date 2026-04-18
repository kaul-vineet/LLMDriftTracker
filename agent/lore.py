"""
agent/lore.py — themed status output (GoT + LotR, no animations)
"""
import random

_R = random.choice


def _got(*msgs):   return _R(msgs)
def _lotr(*msgs):  return _R(msgs)
def _any(*msgs):   return _R(msgs)


# ── Startup ────────────────────────────────────────────────────────────────────
def starting(interval: int):
    msg = _any(
        f"⚔  The Night's Watch takes its post. Polling every {interval} minute(s).",
        f"🧙  You shall not drift. Watching every {interval} minute(s).",
        f"💍  The Eye opens. Polling every {interval} minute(s).",
        f"🐉  The dragon wakes. Polling every {interval} minute(s).",
    )
    print(f"\n{msg}\n")


# ── Cycle ──────────────────────────────────────────────────────────────────────
def cycle_start(ts: str):
    msg = _any(
        f"🏰  A raven arrives from the Citadel — {ts}",
        f"🌄  The Fellowship rides at dawn — {ts}",
        f"⚔  The Watch begins its round — {ts}",
        f"💍  The Eye stirs once more — {ts}",
    )
    print(f"\n{msg}")


def cycle_idle():
    print(_any(
        "🏰  All is quiet on the Wall. The realm holds.",
        "🌿  Even the Shire is undisturbed. No drift detected.",
        "❄   The Night is dark, but nothing stirs.",
        "🌟  The stars are right. No changes this watch.",
    ))


def cycle_complete(n: int):
    print(_any(
        f"⚔  The watch is complete. {n} matter(s) brought before the Small Council.",
        f"📜  {n} scroll(s) sealed and sent by raven.",
        f"🧙  It is done. {n} drift report(s) dispatched.",
        f"🐉  Dracarys was not needed — {n} verdict(s) rendered.",
    ))


# ── Dataverse ─────────────────────────────────────────────────────────────────
def bots_found(env: str, n: int, scope: str):
    print(_any(
        f"📋  {env}: {n} agent(s) answering the call ({scope}).",
        f"🗺   {env}: {n} name(s) appear in the great ledger ({scope}).",
    ))


def bots_failed(env: str, err):
    print(_any(
        f"🔥  {env}: the raven fell before arriving — {err}",
        f"⚠   {env}: a shadow blocks the path — {err}",
    ))


# ── Model version ─────────────────────────────────────────────────────────────
def no_change(name: str):
    print(_any(
        f"🏰  {name}: holds its post. No drift.",
        f"🌿  {name}: steady as the Shire. No change.",
    ))


def model_changed(name: str, old: str, new: str):
    print(_any(
        f"🐉  {name}: the dragon has shed its skin — {old} → {new}",
        f"⚔   {name}: a new sword is forged — {old} → {new}",
        f"💍  {name}: the ring changes hands — {old} → {new}",
        f"🌑  {name}: darkness gathers — model drift detected: {old} → {new}",
    ))


# ── Eval ──────────────────────────────────────────────────────────────────────
def eval_no_testsets(name: str):
    print(_any(
        f"📜  {name}: no scrolls found. The trial cannot begin.",
        f"⚔   {name}: no champion steps forward. Skipping.",
    ))


def eval_start(name: str, test_set: str):
    print(_any(
        f"⚔   {name}: trial by combat begins — '{test_set}'",
        f"🧙  {name}: the quest is undertaken — '{test_set}'",
        f"🐉  {name}: the dragon judges — '{test_set}'",
    ))


_SPIN = ["⚔", "·", "🗡", "·"]


def eval_polling(run_id: str, state: str, elapsed: int, timeout: int, total: int = 0):
    frame = _SPIN[(elapsed // 20) % len(_SPIN)]
    cases = f"  {total} cases" if total else ""
    line  = f"   {frame}  {elapsed}s  {state}{cases}  run={run_id[:8]}"
    print(f"\r{line:<72}", end="", flush=True)


def eval_poll_done():
    print()


def eval_done(name: str):
    print(_any(
        f"⚔   {name}: the verdict is reached.",
        f"🏰  {name}: the Citadel has spoken.",
        f"🧙  {name}: so it is written, so it shall be.",
    ))


def eval_error(name: str, err):
    print(_any(
        f"🔥  {name}: Dracarys — something burns: {err}",
        f"🌑  {name}: the shadow takes it — {err}",
        f"⚠   {name}: a raven fell in transit — {err}",
    ))


# ── Report ────────────────────────────────────────────────────────────────────
def report_saved(path: str):
    print(_any(
        f"📜  The scroll is sealed → {path}",
        f"🏰  The Citadel records are updated → {path}",
    ))


def report_sent(recipient: str):
    print(_any(
        f"🦅  The raven flies to {recipient}.",
        f"📯  Word is sent by horn to {recipient}.",
    ))


def report_skipped():
    print(_any(
        "📜  No raven sent — SMTP not configured.",
        "🏰  The scroll remains in the tower — SMTP not configured.",
    ))
