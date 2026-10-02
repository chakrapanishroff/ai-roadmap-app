"""AI Engineer Roadmap: an interactive learning hub built from AI_Engineer_Roadmap.txt"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

import streamlit as st
import streamlit.components.v1 as components

from roadmap_parser import Resource, Section, parse_roadmap

st.set_page_config(page_title="AI Engineer Roadmap", page_icon="🧭", layout="wide")

ROADMAP_FILE = Path(__file__).parent / "AI_Engineer_Roadmap.txt"

PAGE_HOME = "Overview"
PAGE_PATH = "Learning path"
PAGE_SEARCH = "Search all links"
PAGE_PROJECTS = "Project ladder"
PAGE_BOOKS = "Books"
PAGE_PLAN = "Timeline and habits"
PAGES = [PAGE_HOME, PAGE_PATH, PAGE_SEARCH, PAGE_PROJECTS, PAGE_BOOKS, PAGE_PLAN]

KIND_ICON = {
    "Video": "🎥", "Paper": "📄", "GitHub": "💻", "Community": "💬", "Blog": "✍️",
    "Course": "🎓", "Docs": "📖", "Book": "📚", "Practice": "🏋️", "Feed": "📡",
    "Newsletter": "📰", "Resource": "🔗",
}

st.markdown(
    """
<style>
.block-container {padding-top: 2.2rem; max-width: 1250px;}
.page-title {font-size: 2.3rem; font-weight: 800; letter-spacing: -0.02em; margin: 0 0 .15rem 0; line-height: 1.15;}
.page-sub {font-size: 1.05rem; opacity: .75; margin: 0 0 1.2rem 0; max-width: 62ch;}
.chip {display:inline-block; padding: 2px 11px; margin: 3px 5px 3px 0; border-radius: 999px;
       font-size: .8rem; background: rgba(127,127,127,.14); border: 1px solid rgba(127,127,127,.28);}
.chip-accent {background: rgba(14,124,134,.15); border-color: rgba(14,124,134,.55); font-weight: 600;}
.res-title {font-weight: 650; font-size: 1.02rem; line-height: 1.3; margin-bottom: 2px;}
.res-meta {font-size: .8rem; opacity: .65; margin-bottom: 8px; word-break: break-all;}
.tl {border-left: 3px solid rgba(14,124,134,.6); margin-left: 8px; padding-left: 22px;}
.tl-item {position: relative; padding: 4px 0 18px 0;}
.tl-item:before {content: ""; position: absolute; left: -31px; top: 9px; width: 13px; height: 13px;
                 border-radius: 50%; background: #0E7C86; border: 3px solid rgba(255,255,255,.9);}
.tl-when {font-weight: 750; font-size: 1.05rem;}
.tl-what {opacity: .85;}
div[data-testid="stMetricValue"] {font-weight: 800;}
</style>
""",
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------- data
@st.cache_data(show_spinner=False)
def load_roadmap():
    return parse_roadmap(ROADMAP_FILE)


RM = load_roadmap()
SECTIONS: list[Section] = RM.sections
SECTION_LABELS = [s.title for s in SECTIONS]

# ----------------------------------------------------------------------------- state
if "done" not in st.session_state:
    st.session_state.done = set()
if "page" not in st.session_state:
    st.session_state.page = PAGE_HOME
if "phase_sel" not in st.session_state:
    st.session_state.phase_sel = SECTION_LABELS[0]

done: set[str] = st.session_state.done


def toggle(item_id: str, widget_key: str) -> None:
    if st.session_state[widget_key]:
        st.session_state.done.add(item_id)
    else:
        st.session_state.done.discard(item_id)


def go_section(label: str) -> None:
    st.session_state.page = PAGE_PATH
    st.session_state.phase_sel = label


def section_progress(s: Section) -> tuple[int, int]:
    urls = {r.url for r in s.resources}
    return len(urls & done), len(urls)


def overall_progress() -> tuple[int, int]:
    urls = {r.url for r in RM.resources}
    projects = {f"project:{n}" for _, items in RM.projects for n, _ in items}
    books = {f"book:{i}" for i in range(len(RM.books))}
    everything = urls | projects | books
    return len(everything & done), len(everything)


def check_item(item_id: str, key: str, label: str) -> None:
    st.session_state[key] = item_id in done
    st.checkbox(label, key=key, on_change=toggle, args=(item_id, key))


# ----------------------------------------------------------------------------- preview dialog
def embed_url(url: str) -> str | None:
    u = urlparse(url)
    host = u.netloc.lower().removeprefix("www.")
    if u.scheme != "https":
        return None  # browsers block http pages inside an https app
    if host == "youtube.com" and u.path == "/watch":
        vid = parse_qs(u.query).get("v", [""])[0]
        if vid:
            return f"https://www.youtube.com/embed/{vid}"
    if host == "youtube.com" and u.path.startswith("/@"):
        return None
    return url


@st.dialog("Preview", width="large")
def preview_dialog(title: str, url: str) -> None:
    st.markdown(f"#### {title}")
    st.link_button("Open in a new tab", url, type="primary")
    src = embed_url(url)
    if src is None:
        st.info("This link can't be shown inside the app. Use “Open in a new tab”.")
        return
    st.caption(
        "Many sites (GitHub, Coursera, Reddit, and some docs sites) block embedding. "
        "If the frame below stays blank, use “Open in a new tab”."
    )
    components.iframe(src, height=620, scrolling=True)


# ----------------------------------------------------------------------------- link checker
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RoadmapLinkCheck/1.0)"}


@st.cache_data(ttl=3600, show_spinner=False)
def check_url(url: str) -> str:
    import requests

    try:
        r = requests.head(url, allow_redirects=True, timeout=8, headers=HEADERS)
        if r.status_code >= 400:
            r = requests.get(url, stream=True, allow_redirects=True, timeout=8, headers=HEADERS)
            r.close()
        code = r.status_code
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}"
    if code < 400:
        return "ok"
    if code in (401, 403, 429, 999):
        return f"blocked ({code}), probably fine in a browser"
    return f"broken ({code})"


def run_link_check(resources: list[Resource]) -> None:
    with st.spinner(f"Checking {len(resources)} links..."):
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(lambda r: check_url(r.url), resources))
    bad = [(r, s) for r, s in zip(resources, results) if s != "ok"]
    if not bad:
        st.success(f"All {len(resources)} links responded normally.")
        return
    st.warning(f"{len(bad)} of {len(resources)} links need a look.")
    st.dataframe(
        [{"Title": r.title, "Status": s, "URL": r.url} for r, s in bad],
        hide_index=True,
        use_container_width=True,
        column_config={"URL": st.column_config.LinkColumn("URL")},
    )


# ----------------------------------------------------------------------------- UI pieces
def resource_card(r: Resource, prefix: str) -> None:
    with st.container(border=True):
        st.markdown(f'<div class="res-title">{r.title}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="res-meta">{KIND_ICON.get(r.kind, "🔗")} {r.kind} on {r.domain}</div>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        c1.link_button("Open", r.url, use_container_width=True)
        if c2.button("Preview", key=f"{prefix}_pv_{r.uid}", use_container_width=True):
            preview_dialog(r.title, r.url)
        check_item(r.url, f"{prefix}_cb_{r.uid}", "Mark as done")


def resource_grid(resources: list[Resource], prefix: str, ncols: int = 2) -> None:
    cols = st.columns(ncols)
    for i, r in enumerate(resources):
        with cols[i % ncols]:
            resource_card(r, prefix)


def chips(items: list[str], accent: bool = False) -> None:
    cls = "chip chip-accent" if accent else "chip"
    st.markdown("".join(f'<span class="{cls}">{i}</span>' for i in items), unsafe_allow_html=True)


def page_header(title: str, sub: str) -> None:
    st.markdown(f'<div class="page-title">{title}</div><div class="page-sub">{sub}</div>',
                unsafe_allow_html=True)


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### 🧭 AI Engineer Roadmap")
    st.radio("Go to", PAGES, key="page", label_visibility="collapsed")
    d, t = overall_progress()
    st.divider()
    st.markdown("**Your progress**")
    st.progress(d / t if t else 0.0, text=f"{d} of {t} items done")
    with st.expander("Save or restore progress"):
        st.caption(
            "Progress lives in this browser session only. Download it before you close the tab "
            "and upload it next time to carry on."
        )
        st.download_button(
            "Download progress",
            data=json.dumps(sorted(done), indent=2),
            file_name="ai_roadmap_progress.json",
            mime="application/json",
            use_container_width=True,
        )
        up = st.file_uploader("Restore from file", type="json", label_visibility="collapsed")
        if up is not None and st.session_state.get("_restored") != up.file_id:
            try:
                data = json.loads(up.getvalue())
                if isinstance(data, list):
                    st.session_state.done = {str(x) for x in data}
                    st.session_state["_restored"] = up.file_id
                    st.rerun()
            except json.JSONDecodeError:
                st.error("That file isn't valid progress JSON.")
        if st.button("Reset all progress", use_container_width=True):
            st.session_state.done = set()
            st.rerun()

page = st.session_state.page

# ----------------------------------------------------------------------------- pages
if page == PAGE_HOME:
    page_header(
        "Become an AI engineer",
        f"{len(RM.resources)} hand-picked links, {sum(len(i) for _, i in RM.projects)} projects and "
        f"{len(RM.books)} books, ordered from Python basics to GPU kernels. "
        "Build something at every stage: watching is not learning.",
    )
    m = st.columns(4)
    m[0].metric("Phases", sum(1 for s in SECTIONS if s.key.startswith("phase")))
    m[1].metric("Links", len(RM.resources))
    m[2].metric("Projects", sum(len(i) for _, i in RM.projects))
    m[3].metric("Done", f"{d}/{t}")

    st.markdown("#### Pick a phase")
    cols = st.columns(3)
    for i, s in enumerate(SECTIONS):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{s.title}**")
                meta = [x for x in (s.duration, s.tag) if x]
                if meta:
                    chips(meta, accent=bool(s.tag))
                sd, st_ = section_progress(s)
                st.progress(sd / st_ if st_ else 0.0, text=f"{sd} of {st_} links done")
                st.button("Open this phase", key=f"home_open_{s.key}", on_click=go_section,
                          args=(s.title,), use_container_width=True)

elif page == PAGE_PATH:
    st.selectbox("Phase", SECTION_LABELS, key="phase_sel")
    sec = SECTIONS[SECTION_LABELS.index(st.session_state.phase_sel)]
    page_header(sec.title, "Work top to bottom. Open a link, then tick it off when you've finished.")
    meta = [x for x in (sec.duration, sec.tag) if x]
    if meta:
        chips(meta, accent=bool(sec.tag))
    if sec.topics:
        st.markdown("**Topics to cover**")
        chips([t.strip().rstrip(".") for t in sec.topics.split(",") if t.strip()])
    sd, st_ = section_progress(sec)
    st.progress(sd / st_ if st_ else 0.0, text=f"{sd} of {st_} links done")

    for gi, (group, resources) in enumerate(sec.groups):
        if group:
            st.subheader(group)
        resource_grid(resources, f"lp{gi}")

    with st.expander("Check that these links still work"):
        st.caption("Links change over time. This pings every URL in the phase from the server.")
        if st.button("Run link check", key="lc_btn"):
            run_link_check(sec.resources)

elif page == PAGE_SEARCH:
    page_header("Search all links", "Find anything across every phase by title, site, or topic.")
    f1, f2 = st.columns([2, 3])
    q = f1.text_input("Search", placeholder="e.g. LoRA, vLLM, Karpathy, RAG")
    kinds = sorted({r.kind for r in RM.resources})
    kind_sel = f2.multiselect("Type", kinds, placeholder="All types")
    f3, f4 = st.columns([3, 2])
    sec_sel = f3.multiselect("Phase", SECTION_LABELS, placeholder="All phases")
    hide_done = f4.toggle("Hide completed", value=False)

    results = []
    for s in SECTIONS:
        if sec_sel and s.title not in sec_sel:
            continue
        for g, rs in s.groups:
            for r in rs:
                hay = f"{r.title} {r.domain} {r.url} {g} {s.name}".lower()
                if q and not all(w in hay for w in q.lower().split()):
                    continue
                if kind_sel and r.kind not in kind_sel:
                    continue
                if hide_done and r.url in done:
                    continue
                results.append(r)

    st.caption(f"{len(results)} matching links")
    if not results:
        st.info("Nothing matches. Try fewer words or clear a filter.")
    else:
        shown = results[:60]
        resource_grid(shown, "sr", ncols=3)
        if len(results) > len(shown):
            st.caption(f"Showing the first {len(shown)}. Narrow the search to see the rest.")

elif page == PAGE_PROJECTS:
    page_header("Project ladder",
                "Put every project on GitHub. A small finished project beats a big abandoned one.")
    total_p = sum(len(i) for _, i in RM.projects)
    done_p = sum(1 for _, items in RM.projects for n, _ in items if f"project:{n}" in done)
    st.progress(done_p / total_p if total_p else 0.0, text=f"{done_p} of {total_p} projects built")
    for level, items in RM.projects:
        st.subheader(level)
        for n, text in items:
            with st.container(border=True):
                c1, c2 = st.columns([6, 1.4])
                c1.markdown(f"**{text}**")
                with c2:
                    check_item(f"project:{n}", f"pj_{n}", "Built")

elif page == PAGE_BOOKS:
    page_header("Books", "Pick a few and read them alongside the courses, not instead of them.")
    for i, (title, note) in enumerate(RM.books):
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 1.6, 1.3])
            c1.markdown(f"**{title}**")
            if note:
                c1.caption(note)
            c2.link_button("Find online", f"https://www.google.com/search?q={quote_plus(title + ' book')}",
                           use_container_width=True)
            with c3:
                check_item(f"book:{i}", f"bk_{i}", "Read")

elif page == PAGE_PLAN:
    page_header("Timeline and habits", RM.timeline_note.capitalize() if RM.timeline_note else "")
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Month by month")
        html = '<div class="tl">' + "".join(
            f'<div class="tl-item"><div class="tl-when">{w}</div><div class="tl-what">{what}</div></div>'
            for w, what in RM.timeline
        ) + "</div>"
        st.markdown(html, unsafe_allow_html=True)
    with right:
        st.subheader("Habits of strong AI engineers")
        for h in RM.habits:
            with st.container(border=True):
                st.markdown(h)
