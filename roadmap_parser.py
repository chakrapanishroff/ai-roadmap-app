"""Parses AI_Engineer_Roadmap.txt into structured data.

Edit the .txt file (add/remove URLs, rename sections) and the app updates itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

HEADER_RE = re.compile(r"^-{20,}\n[ \t]*(.+?)[ \t]*\n-{20,}[ \t]*$", re.M)
URL_RE = re.compile(r"https?://[^\s,;)]+")
KEEP_UPPER = {"AI", "ML", "GPU", "NLP"}


@dataclass
class Resource:
    uid: int
    title: str
    url: str
    domain: str
    kind: str
    section: str
    group: str


@dataclass
class Section:
    key: str
    label: str  # e.g. "Phase 3"
    name: str  # e.g. "Transformers & LLMs"
    duration: str = ""
    tag: str = ""  # e.g. "CORE", "JOB SKILLS"
    topics: str = ""
    groups: list[tuple[str, list[Resource]]] = field(default_factory=list)

    @property
    def resources(self) -> list[Resource]:
        return [r for _, rs in self.groups for r in rs]

    @property
    def title(self) -> str:
        return f"{self.label}: {self.name}" if self.label else self.name


@dataclass
class Roadmap:
    sections: list[Section] = field(default_factory=list)
    projects: list[tuple[str, list[tuple[int, str]]]] = field(default_factory=list)
    books: list[tuple[str, str]] = field(default_factory=list)
    timeline_note: str = ""
    timeline: list[tuple[str, str]] = field(default_factory=list)
    habits: list[str] = field(default_factory=list)

    @property
    def resources(self) -> list[Resource]:
        return [r for s in self.sections for r in s.resources]


def _pretty(word: str) -> str:
    if word in KEEP_UPPER or not word.isupper():
        return word
    lw = word.lower()
    for i, ch in enumerate(lw):
        if ch.isalpha():
            return lw[:i] + ch.upper() + lw[i + 1:]
    return word


def _pretty_name(name: str) -> str:
    return " ".join(_pretty(w) for w in name.split())


def classify(url: str) -> str:
    u = urlparse(url)
    host = u.netloc.lower().removeprefix("www.")
    path = u.path.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "Video"
    if host.endswith("arxiv.org") and "/abs/" in path:
        return "Paper"
    if host == "github.com":
        return "GitHub"
    if "reddit.com" in host or "alignmentforum.org" in host:
        return "Community"
    if host.endswith("arxiv.org") and "/list/" in path:
        return "Feed"
    if "huggingface.co" in host and (path.startswith("/papers") or path.startswith("/spaces/mteb")):
        return "Feed"
    if "huggingface.co" in host and path.startswith("/spaces"):
        return "Practice"
    if "leetcode.com" in host:
        return "Practice"
    if "anthropic.com" in host and "/research" in path:
        return "Feed"
    if "jax-ml.github.io" in host or "karpathy.ai" in host:
        return "Course" if "karpathy" in host else "Book"
    if host in {"substack.com"} or host.endswith(".substack.com") or host in {
        "jalammar.github.io", "lilianweng.github.io", "hamel.dev", "eugeneyan.com",
        "simonwillison.net", "magazine.sebastianraschka.com", "distill.pub",
        "transformer-circuits.pub", "huyenchip.com",
    }:
        return "Blog"
    if any(k in host for k in ("coursera.org", "course.fast.ai", "ocw.mit.edu", "cs50.harvard.edu",
                                "cs229.stanford.edu", "cs231n.stanford.edu", "stanford-cs336",
                                "web.stanford.edu", "missing.csail.mit.edu", "madewithml.com",
                                "fullstackdeeplearning.com", "linuxjourney.com", "arena.education",
                                "3blue1brown.com", "khanacademy.org", "roadmap.sh")):
        return "Course"
    if "huggingface.co" in host and "/learn/" in path:
        return "Course"
    if "kaggle.com" in host:
        return "Course" if "/learn" in path else "Practice"
    if "deeplearning.ai" in host:
        return "Course" if "short-courses" in path else "Newsletter"
    if any(k in host for k in ("d2l.ai", "deeplearningbook.org", "neuralnetworksanddeeplearning.com",
                                "mml-book.github.io", "statlearning.com", "scaling-book")):
        return "Book"
    if host in {"latent.space", "www.latent.space"} or "latent.space" in host:
        return "Newsletter"
    if host.startswith("docs.") or "/docs" in path or "readthedocs" in host or host.startswith("doc."):
        return "Docs"
    if any(k in host for k in ("pytorch.org", "numpy.org", "pandas.pydata.org", "matplotlib.org",
                                "scikit-learn.org", "fastapi.tiangolo.com", "kubernetes.io",
                                "mlflow.org", "vllm.ai", "deepspeed.ai", "triton-lang.org",
                                "modelcontextprotocol.io", "langchain", "trychroma.com",
                                "qdrant.tech", "sbert.net", "langfuse.com", "promptfoo.dev",
                                "ollama.com", "dvc.org", "modal.com", "ai.google.dev",
                                "platform.openai.com", "python.org")):
        return "Docs"
    return "Resource"


def _parse_resource_body(body: str, section_name: str) -> tuple[list[tuple[str, list[Resource]]], str]:
    groups: list[tuple[str, list[Resource]]] = []
    topics: list[str] = []
    in_topics = False

    def current() -> list[Resource]:
        if not groups:
            groups.append(("", []))
        return groups[-1][1]

    for raw in body.splitlines():
        line = raw.rstrip()
        if line.startswith("="):
            continue
        if not line.strip():
            in_topics = False
            continue
        if line.startswith("Topics:"):
            in_topics = True
            topics.append(line[len("Topics:"):].strip())
            continue
        if in_topics:
            topics.append(line.strip())
            continue
        if line.startswith("- "):
            idx = line.find(": http")
            if idx == -1:
                continue
            title = line[2:idx].strip()
            urls = URL_RE.findall(line[idx:])
            for u in urls:
                domain = urlparse(u).netloc.removeprefix("www.")
                t = title if len(urls) == 1 else f"{title} ({domain})"
                current().append(Resource(0, t, u, domain, classify(u), section_name, groups[-1][0]))
            continue
        # anything else is a sub-heading
        groups.append((line.strip(), []))

    return [(g, rs) for g, rs in groups if rs], " ".join(topics)


def parse_roadmap(path: str | Path) -> Roadmap:
    text = Path(path).read_text(encoding="utf-8")
    rm = Roadmap()
    matches = list(HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        header = m.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end]
        up = header.upper()

        pm = re.match(r"PHASE\s+(\d+)\s*-\s*(.+?)\s*(?:\(([^)]*)\))?\s*(?:<--\s*(.+))?$", header)
        if pm:
            num, name, dur, tag = pm.groups()
            sec = Section(key=f"phase{num}", label=f"Phase {num}", name=_pretty_name(name),
                          duration=(dur or "").strip(), tag=(tag or "").strip())
            sec.groups, sec.topics = _parse_resource_body(body, sec.title)
            rm.sections.append(sec)
        elif up.startswith("DAILY"):
            sec = Section(key="daily", label="", name="News, communities and practice")
            sec.groups, sec.topics = _parse_resource_body(body, sec.title)
            rm.sections.append(sec)
        elif up.startswith("BOOKS"):
            for line in body.splitlines():
                bm = re.match(r"^\d+\.\s+(.+)$", line.strip())
                if bm:
                    t, _, note = bm.group(1).partition(" - ")
                    rm.books.append((t.strip(), note.strip()))
        elif up.startswith("PROJECT LADDER"):
            level = ""
            for line in body.splitlines():
                if line.startswith("="):
                    continue
                im = re.match(r"^\s{0,2}(\d+)\.\s+(.+)$", line)
                if im and level:
                    rm.projects[-1][1].append((int(im.group(1)), im.group(2).strip()))
                elif line.startswith("    ") and level and rm.projects[-1][1]:
                    n, t = rm.projects[-1][1][-1]
                    rm.projects[-1][1][-1] = (n, f"{t} {line.strip()}")
                elif line.strip() and not line.startswith(" "):
                    level = line.strip()
                    rm.projects.append((level, []))
        elif up.startswith("SUGGESTED TIMELINE"):
            nm = re.search(r"\(([^)]*)\)", header)
            rm.timeline_note = nm.group(1) if nm else ""
            for line in body.splitlines():
                tm = re.match(r"^(Months?\s+[\d-]+)\s*:\s*(.+)$", line.strip())
                if tm:
                    rm.timeline.append((tm.group(1), tm.group(2).strip()))
        elif up.startswith("HABITS"):
            for line in body.splitlines():
                if line.startswith("- "):
                    rm.habits.append(line[2:].strip())

    uid = 0
    for r in rm.resources:
        r.uid = uid
        uid += 1
    return rm


if __name__ == "__main__":
    rm = parse_roadmap(Path(__file__).parent / "AI_Engineer_Roadmap.txt")
    for s in rm.sections:
        print(f"{s.title!r:55} dur={s.duration!r:12} tag={s.tag!r:12} res={len(s.resources)} groups={[g for g, _ in s.groups]}")
    print("total resources:", len(rm.resources))
    print("projects:", [(lv, len(it)) for lv, it in rm.projects])
    print("books:", len(rm.books), "timeline:", len(rm.timeline), "habits:", len(rm.habits))
