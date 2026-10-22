"""Hintergrund-Jobs: brew-Befehle nacheinander ausführen, Ausgabe live sammeln, sudo-Passwort per UI erfragen."""
import itertools
import os
import queue
import signal
import subprocess
import threading
import time


class Job:
    def __init__(self, jid, title, cmds):
        self.id, self.title, self.cmds = jid, title, cmds
        self.lines, self.status = [], "queued"
        self.created, self.finished = time.time(), None
        self.proc, self.cancel_requested = None, False

    def add(self, line):
        self.lines.append(line)

    def summary(self):
        return {"id": self.id, "title": self.title, "status": self.status, "lines": len(self.lines),
                "created": self.created, "finished": self.finished}


class JobManager:
    def __init__(self, brew, env, askpass, on_success):
        self.brew, self.env, self.askpass, self.on_success = brew, env, askpass, on_success
        self.jobs, self.order = {}, []
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.counter = itertools.count(1)
        self.pending = None
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, title, cmds):
        job = Job(next(self.counter), title, cmds)
        with self.lock:
            self.jobs[job.id] = job
            self.order.append(job.id)
            for old in self.order[:-30]:
                self.jobs.pop(old, None)
            self.order = self.order[-30:]
        self.q.put(job)
        return job

    def get(self, jid):
        return self.jobs.get(jid)

    def listing(self):
        with self.lock:
            prompt = self.pending["prompt"] if self.pending else None
            return {"jobs": [self.jobs[i].summary() for i in reversed(self.order) if i in self.jobs], "prompt": prompt}

    def cancel(self, jid):
        job = self.jobs.get(jid)
        if not job or job.status in ("done", "error", "cancelled"):
            return False
        job.cancel_requested = True
        if job.proc and job.proc.poll() is None:
            try:
                os.killpg(job.proc.pid, signal.SIGTERM)
            except OSError:
                pass
        self.answer(None)
        return True

    # --- sudo-Passwortabfrage (vom Askpass-Helfer aufgerufen) ---
    def ask_password(self, prompt):
        state = {"prompt": prompt, "event": threading.Event(), "answer": None}
        with self.lock:
            self.pending = state
        got = state["event"].wait(180)
        with self.lock:
            self.pending = None
        return state["answer"] if got else None

    def answer(self, password):
        with self.lock:
            st = self.pending
        if not st:
            return False
        st["answer"] = password
        st["event"].set()
        return True

    def _worker(self):
        while True:
            job = self.q.get()
            if job.cancel_requested:
                job.status, job.finished = "cancelled", time.time()
                continue
            self._run(job)

    def _run(self, job):
        job.status = "running"
        ok = True
        env = dict(self.env, SUDO_ASKPASS=self.askpass)
        for cmd in job.cmds:
            if job.cancel_requested:
                break
            job.add("$ brew " + " ".join(cmd["args"]))
            try:
                proc = subprocess.Popen([*self.brew, *cmd["args"]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, env=env, text=True, bufsize=1,
                                        start_new_session=True)
            except OSError as e:
                job.add(f"[Fehler: {e}]")
                ok = False
                continue
            job.proc = proc
            for line in proc.stdout:
                job.add(line.rstrip("\n"))
            rc = proc.wait()
            if rc != 0:
                ok = False
                job.add(f"[Fehler: Exit-Code {rc}]")
            else:
                try:
                    self.on_success(cmd)
                except Exception as e:  # Verlauf darf den Job nie kippen
                    job.add(f"[Hinweis: {e}]")
        job.status = "cancelled" if job.cancel_requested else ("done" if ok else "error")
        job.finished = time.time()
