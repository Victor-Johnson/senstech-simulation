#!/usr/bin/env python3
"""Render the markdown slide-doc into a self-contained HTML presentation.

Reads analysis/reports/presentation_material_penetration_and_phase2.md, splits it
into slides, and emits a standalone HTML deck (relative image paths, keyboard nav,
toggleable speaker-notes panel). Open the .html in a browser to present.
"""
import re
import sys
from pathlib import Path
import markdown

BASE = Path("/home/victor-pc/itek/senstech-simulation/analysis/reports")
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "presentation_material_penetration_and_phase2.md"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "presentation.html"

md = markdown.Markdown(extensions=["tables"])


def render(text: str) -> str:
    md.reset()
    return md.convert(text.strip())


raw = SRC.read_text()
chunks = re.split(r"\n---\n", raw)

slides = []  # each: dict(kind, title, num, body_html, speak_html, qa_html)
for ch in chunks:
    ch = ch.strip()
    if not ch:
        continue
    # part / wrap-up dividers (top-level # headers that are not ## or ###)
    for m in re.finditer(r"^# (PART .+|Wrap-up.*)$", ch, flags=re.M):
        slides.append({"kind": "divider", "title": m.group(1)})
    sm = re.search(r"^## (Slide \d+ [—-] .+)$", ch, flags=re.M)
    if not sm:
        continue
    title_line = sm.group(1)
    num = re.search(r"Slide (\d+)", title_line).group(1)
    title = re.sub(r"^Slide \d+ [—-]\s*", "", title_line)
    after = ch[sm.end():]
    # split content / speak / qa
    parts = re.split(r"\n\*\*🎙 Speak:\*\*", after, maxsplit=1)
    body = parts[0]
    speak = qa = ""
    if len(parts) > 1:
        sp = re.split(r"\n\*\*❓ Likely Q → A:\*\*", parts[1], maxsplit=1)
        speak = sp[0]
        if len(sp) > 1:
            qa = sp[1]
    # drop the timing/figure italic line from body
    body = re.sub(r"^\*\(timing:.*?\)\*\s*", "", body.strip(), flags=re.S)
    slides.append({
        "kind": "slide", "num": num, "title": title,
        "body": render(body),
        "speak": render(speak.replace("🎙 Speak:", "").strip()) if speak else "",
        "qa": render(qa.replace("❓ Likely Q → A:", "").strip()) if qa else "",
    })

# build HTML
cards = []
for i, s in enumerate(slides):
    if s["kind"] == "divider":
        cards.append(f'<section class="slide divider"><div class="dwrap"><h1>{s["title"]}</h1></div></section>')
    else:
        notes = ""
        if s["speak"]:
            notes += f'<div class="ntitle">Speak</div>{s["speak"]}'
        if s["qa"]:
            notes += f'<div class="ntitle">Anticipated Q &rarr; A</div>{s["qa"]}'
        cards.append(
            f'<section class="slide"><div class="swrap"><div class="stag">Slide {s["num"]}</div>'
            f'<h2>{s["title"]}</h2><div class="sbody">{s["body"]}</div></div>'
            f'<div class="notes">{notes}</div></section>')

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CdTe Detector Selection — Presentation</title>
<style>
 :root{{--ink:#12130f;--sub:#4b4b46;--accent:#2a78d6;--surf:#fbfbf8;--line:#e6e6e0;}}
 *{{box-sizing:border-box;}} html,body{{margin:0;height:100%;background:#20211d;color:var(--ink);
   font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;}}
 #deck{{height:100vh;display:flex;align-items:center;justify-content:center;}}
 .slide{{display:none;width:min(1180px,94vw);height:min(720px,92vh);background:var(--surf);
   border-radius:16px;box-shadow:0 18px 60px rgba(0,0,0,.45);overflow:hidden;position:relative;}}
 .slide.active{{display:flex;flex-direction:column;}}
 .swrap{{padding:34px 46px 14px;flex:1;overflow:auto;}}
 .stag{{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:700;}}
 h2{{font-size:30px;margin:.15em 0 .5em;line-height:1.15;}}
 .sbody{{font-size:20px;color:var(--ink);line-height:1.5;}}
 .sbody ul{{margin:.3em 0 .5em 1.1em;padding:0;}} .sbody li{{margin:.28em 0;}}
 .sbody strong{{color:#111;}} .sbody code{{background:#eef1ee;padding:1px 6px;border-radius:5px;
   font-size:.9em;color:#0a3a66;}}
 .sbody img{{display:block;max-height:46vh;max-width:100%;margin:12px auto;border:1px solid var(--line);
   border-radius:8px;background:#fff;}}
 .sbody table{{border-collapse:collapse;margin:8px 0;font-size:16px;}}
 .sbody th,.sbody td{{border:1px solid var(--line);padding:5px 12px;text-align:left;}}
 .sbody th{{background:#f0f2ef;}}
 .divider{{background:linear-gradient(135deg,#1f2b3d,#2a78d6);color:#fff;display:none;}}
 .divider.active{{display:flex;align-items:center;justify-content:center;}}
 .divider h1{{font-size:44px;text-align:center;padding:0 8%;line-height:1.2;}}
 .notes{{display:none;border-top:2px solid var(--line);background:#f4f5f1;color:var(--sub);
   padding:12px 46px 16px;font-size:15px;line-height:1.45;max-height:34vh;overflow:auto;}}
 body.shownotes .notes{{display:block;}}
 .ntitle{{font-weight:700;color:var(--accent);text-transform:uppercase;font-size:12px;
   letter-spacing:.06em;margin:8px 0 2px;}}
 .notes p{{margin:.35em 0;}} .notes em{{color:#333;}}
 #bar{{position:fixed;bottom:0;left:0;right:0;height:4px;background:rgba(255,255,255,.12);}}
 #prog{{height:100%;background:var(--accent);width:0;transition:width .2s;}}
 #hud{{position:fixed;top:12px;right:16px;color:#cfcfc6;font-size:13px;font-weight:600;
   background:rgba(0,0,0,.35);padding:4px 10px;border-radius:20px;}}
 #help{{position:fixed;bottom:12px;left:16px;color:#9a9a90;font-size:12px;}}
</style></head><body>
<div id="deck">{''.join(cards)}</div>
<div id="hud"><span id="cur">1</span> / {len([c for c in cards])}</div>
<div id="bar"><div id="prog"></div></div>
<div id="help">← → navigate · <b>N</b> notes · <b>F</b> fullscreen</div>
<script>
 const S=[...document.querySelectorAll('.slide')];let i=0;
 function show(n){{i=Math.max(0,Math.min(S.length-1,n));S.forEach((s,k)=>s.classList.toggle('active',k===i));
   document.getElementById('cur').textContent=i+1;
   document.getElementById('prog').style.width=((i+1)/S.length*100)+'%';
   document.querySelector('.slide.active .swrap, .slide.active .dwrap')?.scrollTo(0,0);}}
 document.addEventListener('keydown',e=>{{
   if(e.key==='ArrowRight'||e.key==='PageDown'||e.key===' ')show(i+1);
   else if(e.key==='ArrowLeft'||e.key==='PageUp')show(i-1);
   else if(e.key==='Home')show(0);else if(e.key==='End')show(S.length-1);
   else if(e.key.toLowerCase()==='n')document.body.classList.toggle('shownotes');
   else if(e.key.toLowerCase()==='f'){{if(!document.fullscreenElement)document.documentElement.requestFullscreen();else document.exitFullscreen();}}
 }});
 show(0);
</script></body></html>"""

OUT.write_text(html)
n_content = sum(1 for s in slides if s["kind"] == "slide")
n_div = sum(1 for s in slides if s["kind"] == "divider")
print(f"wrote {OUT}")
print(f"sections: {len(cards)} total ({n_content} content slides + {n_div} dividers)")
